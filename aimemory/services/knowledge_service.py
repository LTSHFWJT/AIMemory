from __future__ import annotations

import hashlib
from typing import Any

from aimemory.core.text import chunk_text, extract_keywords
from aimemory.core.utils import json_dumps, make_id, utcnow_iso
from aimemory.domains.knowledge.models import KnowledgeSourceType
from aimemory.services.base import ServiceBase


class KnowledgeService(ServiceBase):
    def create_source(
        self,
        name: str,
        source_type: str = KnowledgeSourceType.MANUAL,
        uri: str | None = None,
        metadata: dict[str, Any] | None = None,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        source_id = source_id or make_id("source")
        now = utcnow_iso()
        self.db.execute(
            """
            INSERT INTO knowledge_sources(id, name, source_type, uri, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                source_type = excluded.source_type,
                uri = excluded.uri,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at
            """,
            (source_id, name, str(source_type), uri, json_dumps(metadata or {}), now, now),
        )
        return self._deserialize_row(self.db.fetch_one("SELECT * FROM knowledge_sources WHERE id = ?", (source_id,)))

    def ingest_text(
        self,
        title: str,
        text: str,
        user_id: str | None = None,
        source_id: str | None = None,
        source_name: str = "manual",
        version_label: str = "v1",
        metadata: dict[str, Any] | None = None,
        chunk_size: int = 500,
        overlap: int = 80,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        source = self._resolve_source(source_id=source_id, source_name=source_name)
        document_id = document_id or make_id("doc")
        job_id = make_id("ingest")
        now = utcnow_iso()

        self.db.execute(
            """
            INSERT INTO ingestion_jobs(id, source_id, document_id, status, message, metadata, created_at, updated_at)
            VALUES (?, ?, ?, 'running', ?, ?, ?, ?)
            """,
            (job_id, source["id"], document_id, "ingesting", json_dumps(metadata or {}), now, now),
        )
        self.db.execute(
            """
            INSERT INTO documents(id, source_id, title, user_id, external_id, status, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source_id = excluded.source_id,
                title = excluded.title,
                user_id = excluded.user_id,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at
            """,
            (document_id, source["id"], title, user_id, None, json_dumps(metadata or {}), now, now),
        )

        stored = self.object_store.put_text(text, object_type="knowledge", suffix=".txt")
        object_row = self._persist_object(stored, mime_type="text/plain", metadata={"document_id": document_id})
        version_id = make_id("docver")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.db.execute(
            """
            INSERT INTO document_versions(id, document_id, version_label, object_id, checksum, size_bytes, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (version_id, document_id, version_label, object_row["id"], checksum, len(text.encode("utf-8")), json_dumps(metadata or {}), now),
        )

        for index, chunk in enumerate(chunk_text(text, chunk_size=chunk_size, overlap=overlap)):
            chunk_id = make_id("chunk")
            chunk_metadata = {"chunk_index": index, **(metadata or {})}
            self.db.execute(
                """
                INSERT INTO document_chunks(id, document_id, version_id, chunk_index, content, tokens, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (chunk_id, document_id, version_id, index, chunk, len(chunk), json_dumps(chunk_metadata), now),
            )
            citation_id = make_id("cite")
            self.db.execute(
                """
                INSERT INTO citations(id, document_id, version_id, chunk_id, label, location, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (citation_id, document_id, version_id, chunk_id, f"{title}#{index + 1}", f"chunk:{index}", json_dumps(chunk_metadata), now),
            )
            self.projection.enqueue(
                topic="knowledge.index",
                entity_type="knowledge_chunk",
                entity_id=chunk_id,
                action="upsert",
                payload={
                    "record_id": chunk_id,
                    "document_id": document_id,
                    "source_id": source["id"],
                    "title": title,
                    "text": chunk,
                    "keywords": extract_keywords(chunk),
                    "metadata": chunk_metadata,
                    "updated_at": now,
                },
            )

        self.db.execute(
            "UPDATE ingestion_jobs SET status = 'completed', message = ?, updated_at = ? WHERE id = ?",
            ("completed", utcnow_iso(), job_id),
        )
        if self.config.auto_project:
            self.projection.project_pending()
        return self.get_document(document_id)

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        document = self._deserialize_row(self.db.fetch_one("SELECT * FROM documents WHERE id = ?", (document_id,)))
        if document is None:
            return None
        versions = self._deserialize_rows(self.db.fetch_all("SELECT * FROM document_versions WHERE document_id = ? ORDER BY created_at DESC", (document_id,)))
        chunk_count = self.db.fetch_one("SELECT COUNT(*) AS count FROM document_chunks WHERE document_id = ?", (document_id,))
        document["versions"] = versions
        document["chunk_count"] = int(chunk_count["count"]) if chunk_count else 0
        return document

    def list_documents(self, source_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
        filters = ["1 = 1"]
        params: list[Any] = []
        if source_id:
            filters.append("source_id = ?")
            params.append(source_id)
        if user_id:
            filters.append("user_id = ?")
            params.append(user_id)
        rows = self.db.fetch_all(
            f"SELECT * FROM documents WHERE {' AND '.join(filters)} ORDER BY updated_at DESC",
            tuple(params),
        )
        return {"results": self._deserialize_rows(rows)}

    def get_document_text(self, document_id: str) -> str:
        row = self.db.fetch_one(
            """
            SELECT o.object_key
            FROM document_versions dv
            JOIN objects o ON o.id = dv.object_id
            WHERE dv.document_id = ?
            ORDER BY dv.created_at DESC
            LIMIT 1
            """,
            (document_id,),
        )
        if row is None:
            raise ValueError(f"Document `{document_id}` does not exist.")
        return self.object_store.get_text(row["object_key"])

    def _resolve_source(self, source_id: str | None, source_name: str) -> dict[str, Any]:
        if source_id:
            source = self.db.fetch_one("SELECT * FROM knowledge_sources WHERE id = ?", (source_id,))
            if source:
                return self._deserialize_row(source)
        rows = self.db.fetch_all("SELECT * FROM knowledge_sources WHERE name = ? ORDER BY created_at ASC LIMIT 1", (source_name,))
        if rows:
            return self._deserialize_row(rows[0])
        return self.create_source(name=source_name)
