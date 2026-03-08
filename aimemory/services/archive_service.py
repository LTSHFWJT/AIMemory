from __future__ import annotations

from typing import Any

from aimemory.core.text import build_summary
from aimemory.core.utils import json_dumps, json_loads, make_id, utcnow_iso
from aimemory.domains.archive.models import ArchiveDomain
from aimemory.domains.interaction.models import SessionStatus
from aimemory.services.base import ServiceBase


class ArchiveService(ServiceBase):
    def __init__(self, db, projection, config, object_store, interaction_service, memory_service):
        super().__init__(db=db, projection=projection, config=config, object_store=object_store)
        self.interaction_service = interaction_service
        self.memory_service = memory_service

    def archive_session(
        self,
        session_id: str,
        user_id: str | None = None,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = self.interaction_service.get_context(session_id)
        if not context["session"]:
            raise ValueError(f"Session `{session_id}` does not exist.")
        lines = [f"{turn['role']}: {turn['content']}" for turn in context["turns"]]
        generated_summary = summary or build_summary(lines, max_sentences=6, max_chars=500)
        highlights = build_summary(lines, max_sentences=3, max_chars=180)
        payload = {"session": context["session"], "context": context}
        stored = self.object_store.put_text(json_dumps(payload), object_type="archives", suffix=".json")
        object_row = self._persist_object(stored, mime_type="application/json", metadata={"session_id": session_id})

        archive_unit_id = make_id("archive")
        archive_summary_id = make_id("archivesum")
        now = utcnow_iso()
        self.db.execute(
            """
            INSERT INTO archive_units(id, domain, source_id, user_id, session_id, object_id, summary, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                archive_unit_id,
                str(ArchiveDomain.SESSION),
                session_id,
                user_id or context["session"]["user_id"],
                session_id,
                object_row["id"],
                generated_summary,
                json_dumps(metadata or {}),
                now,
            ),
        )
        self.db.execute(
            """
            INSERT INTO archive_summaries(id, archive_unit_id, summary, highlights, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (archive_summary_id, archive_unit_id, generated_summary, highlights, json_dumps(metadata or {}), now),
        )
        self.db.execute("UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?", (str(SessionStatus.ARCHIVED), now, session_id))
        self.projection.enqueue(
            topic="archive.index",
            entity_type="archive_summary",
            entity_id=archive_summary_id,
            action="upsert",
            payload={
                "record_id": archive_summary_id,
                "archive_unit_id": archive_unit_id,
                "domain": str(ArchiveDomain.SESSION),
                "user_id": user_id or context["session"]["user_id"],
                "session_id": session_id,
                "text": generated_summary,
                "metadata": metadata or {},
                "updated_at": now,
            },
        )
        if self.config.auto_project:
            self.projection.project_pending()
        return self.get_archive(archive_unit_id)

    def archive_memory(self, memory_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        memory = self.memory_service.get(memory_id)
        if memory is None:
            raise ValueError(f"Memory `{memory_id}` does not exist.")
        stored = self.object_store.put_text(json_dumps(memory), object_type="archives", suffix=".json")
        object_row = self._persist_object(stored, mime_type="application/json", metadata={"memory_id": memory_id})
        archive_unit_id = make_id("archive")
        archive_summary_id = make_id("archivesum")
        now = utcnow_iso()
        self.db.execute(
            """
            INSERT INTO archive_units(id, domain, source_id, user_id, session_id, object_id, summary, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                archive_unit_id,
                str(ArchiveDomain.MEMORY),
                memory_id,
                memory.get("user_id"),
                memory.get("session_id"),
                object_row["id"],
                memory.get("summary") or memory.get("text"),
                json_dumps(metadata or {}),
                now,
            ),
        )
        self.db.execute(
            """
            INSERT INTO archive_summaries(id, archive_unit_id, summary, highlights, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (archive_summary_id, archive_unit_id, memory.get("summary") or memory.get("text"), memory.get("text", "")[:180], json_dumps(metadata or {}), now),
        )
        self.projection.enqueue(
            topic="archive.index",
            entity_type="archive_summary",
            entity_id=archive_summary_id,
            action="upsert",
            payload={
                "record_id": archive_summary_id,
                "archive_unit_id": archive_unit_id,
                "domain": str(ArchiveDomain.MEMORY),
                "user_id": memory.get("user_id"),
                "session_id": memory.get("session_id"),
                "text": memory.get("summary") or memory.get("text"),
                "metadata": metadata or {},
                "updated_at": now,
            },
        )
        self.db.execute("UPDATE memories SET archived_at = ?, status = 'archived', updated_at = ? WHERE id = ?", (now, now, memory_id))
        if self.config.auto_project:
            self.projection.project_pending()
        return self.get_archive(archive_unit_id)

    def get_archive(self, archive_unit_id: str) -> dict[str, Any] | None:
        unit = self._deserialize_row(self.db.fetch_one("SELECT * FROM archive_units WHERE id = ?", (archive_unit_id,)))
        if unit is None:
            return None
        summary = self._deserialize_row(self.db.fetch_one("SELECT * FROM archive_summaries WHERE archive_unit_id = ?", (archive_unit_id,)))
        unit["summary_record"] = summary
        return unit

    def restore_archive(self, archive_unit_id: str) -> dict[str, Any]:
        archive = self.get_archive(archive_unit_id)
        if archive is None:
            raise ValueError(f"Archive `{archive_unit_id}` does not exist.")
        row = self.db.fetch_one("SELECT object_key FROM objects WHERE id = ?", (archive["object_id"],))
        if row is None:
            raise ValueError(f"Archive `{archive_unit_id}` object payload is missing.")
        return json_loads(self.object_store.get_text(row["object_key"]), {})
