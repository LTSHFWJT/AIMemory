from __future__ import annotations

from typing import Any, Iterable

from aimemory.core.utils import json_dumps, json_loads, make_id, utcnow_iso
from aimemory.domains.object.models import StoredObject


class ServiceBase:
    def __init__(self, db, projection, config, object_store=None):
        self.db = db
        self.projection = projection
        self.config = config
        self.object_store = object_store

    def _deserialize_row(self, row: dict[str, Any] | None, json_fields: Iterable[str] = ("metadata",)) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        for field in json_fields:
            if field in item:
                item[field] = json_loads(item.get(field), {})
        return item

    def _deserialize_rows(self, rows: list[dict[str, Any]], json_fields: Iterable[str] = ("metadata",)) -> list[dict[str, Any]]:
        return [self._deserialize_row(row, json_fields) for row in rows if row is not None]

    def _persist_object(self, stored: StoredObject, mime_type: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        now = utcnow_iso()
        existing = self.db.fetch_one("SELECT * FROM objects WHERE object_key = ?", (stored.object_key,))
        object_id = existing["id"] if existing else make_id("obj")
        payload = json_dumps(metadata or {})
        self.db.execute(
            """
            INSERT INTO objects(id, object_key, object_type, mime_type, size_bytes, checksum, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(object_key) DO UPDATE SET
                object_type = excluded.object_type,
                mime_type = excluded.mime_type,
                size_bytes = excluded.size_bytes,
                checksum = excluded.checksum,
                metadata = excluded.metadata
            """,
            (
                object_id,
                stored.object_key,
                stored.object_type,
                mime_type,
                stored.size_bytes,
                stored.checksum,
                payload,
                now,
            ),
        )
        return self._deserialize_row(self.db.fetch_one("SELECT * FROM objects WHERE id = ?", (object_id,)))
