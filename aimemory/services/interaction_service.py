from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from aimemory.core.text import build_summary
from aimemory.core.utils import json_dumps, make_id, utcnow_iso
from aimemory.domains.interaction.models import SessionStatus
from aimemory.services.base import ServiceBase


class InteractionService(ServiceBase):
    def create_session(
        self,
        user_id: str,
        session_id: str | None = None,
        agent_id: str | None = None,
        title: str | None = None,
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = SessionStatus.ACTIVE,
    ) -> dict[str, Any]:
        session_id = session_id or make_id("session")
        now = utcnow_iso()
        ttl_value = ttl_seconds if ttl_seconds is not None else self.config.session_ttl_seconds
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_value)).isoformat() if ttl_value else None
        self.db.execute(
            """
            INSERT INTO sessions(id, user_id, agent_id, title, status, metadata, active_window, ttl_seconds, expires_at, last_accessed_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                user_id = excluded.user_id,
                agent_id = excluded.agent_id,
                title = excluded.title,
                status = excluded.status,
                metadata = excluded.metadata,
                ttl_seconds = excluded.ttl_seconds,
                expires_at = excluded.expires_at,
                last_accessed_at = excluded.last_accessed_at,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                user_id,
                agent_id,
                title,
                str(status),
                json_dumps(metadata or {}),
                json_dumps([]),
                ttl_value,
                expires_at,
                now,
                now,
                now,
            ),
        )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.db.fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return self._deserialize_row(row, ("metadata", "active_window"))

    def append_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        run_id: str | None = None,
        user_id: str | None = None,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        turn_id: str | None = None,
    ) -> dict[str, Any]:
        if self.get_session(session_id) is None:
            if not user_id:
                raise ValueError(f"Session `{session_id}` does not exist.")
            self.create_session(user_id=user_id, session_id=session_id)
        turn_id = turn_id or make_id("turn")
        now = utcnow_iso()
        self.db.execute(
            """
            INSERT INTO conversation_turns(id, session_id, run_id, role, content, name, metadata, tokens_in, tokens_out, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn_id,
                session_id,
                run_id,
                role,
                content,
                name,
                json_dumps(metadata or {}),
                tokens_in,
                tokens_out,
                now,
            ),
        )
        self.db.execute("UPDATE sessions SET last_accessed_at = ?, updated_at = ? WHERE id = ?", (now, now, session_id))
        return self._deserialize_row(self.db.fetch_one("SELECT * FROM conversation_turns WHERE id = ?", (turn_id,)))

    def list_turns(self, session_id: str, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        rows = self.db.fetch_all(
            """
            SELECT * FROM conversation_turns
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (session_id, limit, offset),
        )
        turns = self._deserialize_rows(rows)
        turns.reverse()
        return turns

    def upsert_snapshot(
        self,
        session_id: str,
        summary: str | None = None,
        plan: str | None = None,
        scratchpad: str | None = None,
        run_id: str | None = None,
        window_size: int = 20,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot_id = make_id("snapshot")
        now = utcnow_iso()
        self.db.execute(
            """
            INSERT INTO working_memory_snapshots(id, session_id, run_id, summary, plan, scratchpad, window_size, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                session_id,
                run_id,
                summary,
                plan,
                scratchpad,
                window_size,
                json_dumps(metadata or {}),
                now,
                now,
            ),
        )
        return self._deserialize_row(self.db.fetch_one("SELECT * FROM working_memory_snapshots WHERE id = ?", (snapshot_id,)))

    def set_tool_state(
        self,
        session_id: str,
        tool_name: str,
        state_key: str,
        state_value: Any,
        run_id: str | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        row = self.db.fetch_one(
            "SELECT * FROM tool_states WHERE session_id = ? AND run_id IS ? AND tool_name = ? AND state_key = ?",
            (session_id, run_id, tool_name, state_key),
        )
        state_id = row["id"] if row else make_id("toolstate")
        now = utcnow_iso()
        self.db.execute(
            """
            INSERT INTO tool_states(id, session_id, run_id, tool_name, state_key, state_value, expires_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, run_id, tool_name, state_key) DO UPDATE SET
                state_value = excluded.state_value,
                expires_at = excluded.expires_at,
                updated_at = excluded.updated_at
            """,
            (state_id, session_id, run_id, tool_name, state_key, json_dumps(state_value), expires_at, now),
        )
        return self._deserialize_row(self.db.fetch_one("SELECT * FROM tool_states WHERE id = ?", (state_id,)), ("state_value",))

    def set_variable(self, session_id: str, key: str, value: Any) -> dict[str, Any]:
        row = self.db.fetch_one("SELECT * FROM session_variables WHERE session_id = ? AND key = ?", (session_id, key))
        variable_id = row["id"] if row else make_id("svar")
        now = utcnow_iso()
        self.db.execute(
            """
            INSERT INTO session_variables(id, session_id, key, value, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id, key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (variable_id, session_id, key, json_dumps(value), now),
        )
        return self._deserialize_row(self.db.fetch_one("SELECT * FROM session_variables WHERE id = ?", (variable_id,)), ("value",))

    def get_context(self, session_id: str, limit: int = 12) -> dict[str, Any]:
        session = self.get_session(session_id)
        snapshots = self.db.fetch_all(
            "SELECT * FROM working_memory_snapshots WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        variables = self.db.fetch_all("SELECT * FROM session_variables WHERE session_id = ? ORDER BY updated_at DESC", (session_id,))
        tool_states = self.db.fetch_all("SELECT * FROM tool_states WHERE session_id = ? ORDER BY updated_at DESC", (session_id,))
        return {
            "session": session,
            "turns": self.list_turns(session_id=session_id, limit=limit),
            "snapshot": self._deserialize_row(snapshots[0], ("metadata",)) if snapshots else None,
            "variables": self._deserialize_rows(variables, ("value",)),
            "tool_states": self._deserialize_rows(tool_states, ("state_value",)),
        }

    def compress_session_context(
        self,
        session_id: str,
        *,
        preserve_recent_turns: int | None = None,
        min_turns: int | None = None,
        max_summary_chars: int = 420,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session `{session_id}` does not exist.")

        threshold = int(min_turns if min_turns is not None else getattr(self.config.memory_policy, "compression_turn_threshold", 14))
        preserve = int(
            preserve_recent_turns
            if preserve_recent_turns is not None
            else getattr(self.config.memory_policy, "compression_preserve_recent_turns", 6)
        )
        turns = self.list_turns(session_id, limit=1000, offset=0)
        if len(turns) < threshold or len(turns) <= preserve:
            return {
                "compressed": False,
                "session_id": session_id,
                "turn_count": len(turns),
                "reason": "not-enough-turns",
            }

        older_turns = turns[:-preserve]
        recent_turns = turns[-preserve:]
        older_lines = [f"{turn['role']}: {turn['content']}" for turn in older_turns]
        recent_lines = [f"{turn['role']}: {turn['content']}" for turn in recent_turns]
        summary = build_summary(older_lines, max_sentences=8, max_chars=max_summary_chars)
        assistant_lines = [turn["content"] for turn in recent_turns if turn.get("role") == "assistant"]
        plan = build_summary(assistant_lines or recent_lines, max_sentences=4, max_chars=240)
        scratchpad = build_summary(recent_lines, max_sentences=5, max_chars=260)

        snapshot_metadata = dict(metadata or {})
        snapshot_metadata.update(
            {
                "compression": {
                    "older_turn_count": len(older_turns),
                    "recent_turn_count": len(recent_turns),
                    "preserve_recent_turns": preserve,
                }
            }
        )
        snapshot = self.upsert_snapshot(
            session_id=session_id,
            run_id=recent_turns[-1].get("run_id") if recent_turns else None,
            summary=summary,
            plan=plan,
            scratchpad=scratchpad,
            window_size=preserve,
            metadata=snapshot_metadata,
        )
        self.set_variable(
            session_id,
            "compression_state",
            {
                "compressed_turn_count": len(older_turns),
                "preserve_recent_turns": preserve,
                "updated_at": snapshot["updated_at"],
            },
        )
        return {
            "compressed": True,
            "session_id": session_id,
            "turn_count": len(turns),
            "compressed_turn_count": len(older_turns),
            "snapshot": snapshot,
        }

    def session_health(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session `{session_id}` does not exist.")

        turns = self.list_turns(session_id, limit=1000, offset=0)
        snapshots = self.db.fetch_all(
            "SELECT * FROM working_memory_snapshots WHERE session_id = ? ORDER BY updated_at DESC",
            (session_id,),
        )
        session_memories = self.db.fetch_all(
            "SELECT * FROM memories WHERE session_id = ? AND scope = 'session' AND status = 'active' ORDER BY updated_at DESC",
            (session_id,),
        )
        latest_snapshot = self._deserialize_row(snapshots[0], ("metadata",)) if snapshots else None
        now = datetime.now(timezone.utc)
        last_snapshot_at = None
        snapshot_age_hours = None
        if latest_snapshot and latest_snapshot.get("updated_at"):
            last_snapshot_at = datetime.fromisoformat(latest_snapshot["updated_at"])
            if last_snapshot_at.tzinfo is None:
                last_snapshot_at = last_snapshot_at.replace(tzinfo=timezone.utc)
            snapshot_age_hours = max(0.0, (now - last_snapshot_at.astimezone(timezone.utc)).total_seconds() / 3600.0)

        compression_threshold = int(getattr(self.config.memory_policy, "compression_turn_threshold", 14))
        snapshot_stale_hours = int(getattr(self.config.memory_policy, "session_health_snapshot_stale_hours", 24))
        promotable_memories = [
            item
            for item in self._deserialize_rows(session_memories)
            if float(item.get("importance", 0.0)) >= 0.55
        ]

        recommendations: list[str] = []
        if len(turns) >= compression_threshold and (latest_snapshot is None or (snapshot_age_hours is not None and snapshot_age_hours >= snapshot_stale_hours)):
            recommendations.append("compact")
        if promotable_memories:
            recommendations.append("promote")
        if len(snapshots) > int(getattr(self.config.memory_policy, "snapshot_keep_recent", 3)):
            recommendations.append("prune_snapshots")

        return {
            "session_id": session_id,
            "turn_count": len(turns),
            "snapshot_count": len(snapshots),
            "session_memory_count": len(session_memories),
            "promotable_session_memory_count": len(promotable_memories),
            "latest_snapshot_at": latest_snapshot.get("updated_at") if latest_snapshot else None,
            "snapshot_age_hours": round(snapshot_age_hours, 6) if snapshot_age_hours is not None else None,
            "recommendations": recommendations,
        }

    def prune_snapshots(self, session_id: str, *, keep_recent: int | None = None) -> dict[str, Any]:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session `{session_id}` does not exist.")
        keep = max(1, int(keep_recent or getattr(self.config.memory_policy, "snapshot_keep_recent", 3)))
        snapshots = self.db.fetch_all(
            "SELECT * FROM working_memory_snapshots WHERE session_id = ? ORDER BY updated_at DESC",
            (session_id,),
        )
        deleted_ids: list[str] = []
        for snapshot in snapshots[keep:]:
            self.db.execute("DELETE FROM working_memory_snapshots WHERE id = ?", (snapshot["id"],))
            deleted_ids.append(snapshot["id"])
        return {
            "session_id": session_id,
            "kept": min(len(snapshots), keep),
            "deleted": len(deleted_ids),
            "deleted_ids": deleted_ids,
        }

    def clear_session(self, session_id: str) -> dict[str, Any]:
        self.db.execute("DELETE FROM conversation_turns WHERE session_id = ?", (session_id,))
        self.db.execute("DELETE FROM working_memory_snapshots WHERE session_id = ?", (session_id,))
        self.db.execute("DELETE FROM tool_states WHERE session_id = ?", (session_id,))
        self.db.execute("DELETE FROM session_variables WHERE session_id = ?", (session_id,))
        self.db.execute("UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?", (str(SessionStatus.CLOSED), utcnow_iso(), session_id))
        return {"message": "Session cleared", "session_id": session_id}
