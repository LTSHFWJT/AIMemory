from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aimemory import AIMemory, Scope
from aimemory.errors import InvalidScope
from aimemory.pipeline.lifecycle import now_ms


class NeverRetrieveGate:
    def should_retrieve(self, query: str, scope: Scope) -> bool:
        return False


class ReverseReranker:
    def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        ranked = []
        for index in range(len(docs) - 1, -1, -1):
            ranked.append((index, float(len(docs) - index)))
        return ranked[:top_k]


class StaticExtractor:
    def extract(self, messages: list[dict], scope: Scope) -> list[dict]:
        joined = " | ".join(str(message.get("content", "")) for message in messages if message.get("content"))
        return [
            {
                "text": f"Extractor memory for {scope.workspace_id}: {joined}",
                "kind": "summary",
                "metadata": {"message_count": len(messages)},
                "source_type": "message_batch",
            }
        ]


class MemoryDBRefactorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.scope = Scope(
            workspace_id="ws.alpha",
            project_id="proj.beta",
            user_id="user-1",
            agent_id="planner",
        )
        self.db = AIMemory.open(self.root / ".aimemory")

    def tearDown(self) -> None:
        self.db.close()
        self.tempdir.cleanup()

    def test_put_search_and_list(self) -> None:
        created = self.db.put(
            scope=self.scope,
            text="User prefers concise answers with conclusions first.",
            kind="preference",
        )
        listed = self.db.list(scope=self.scope)
        hits = self.db.search(scope=self.scope, query="answer style preference", top_k=3)

        self.assertEqual(len(listed), 1)
        self.assertEqual(created["head_id"], listed[0]["head_id"])
        self.assertTrue(hits)
        self.assertEqual(hits[0]["head_id"], created["head_id"])

    def test_supersede_preference_history(self) -> None:
        first = self.db.put(
            scope=self.scope,
            text="User wants short direct answers.",
            kind="preference",
            fact_key="style.answer",
        )
        second = self.db.put(
            scope=self.scope,
            text="User wants short direct answers and key bullets.",
            kind="preference",
            fact_key="style.answer",
        )
        history = self.db.history(scope=self.scope, head_id=first["head_id"])
        current = self.db.get(scope=self.scope, head_id=first["head_id"])

        self.assertEqual(first["head_id"], second["head_id"])
        self.assertNotEqual(first["version_id"], second["version_id"])
        self.assertEqual(len(history["versions"]), 2)
        self.assertEqual(current["version_id"], second["version_id"])
        self.assertEqual(current["text"], "User wants short direct answers and key bullets.")

    def test_working_memory_uses_lmdb(self) -> None:
        scoped = self.db.scoped(self.scope)
        scoped.working_append("user", "Need a release checklist.")
        scoped.working_append("assistant", "Drafting checklist.")
        snapshot = scoped.working_snapshot()

        self.assertEqual(len(snapshot), 2)
        self.assertEqual(snapshot[0]["content"], "Drafting checklist.")

    def test_delete_and_restore_affect_search(self) -> None:
        created = self.db.put(
            scope=self.scope,
            text="Project decision: use SQLite as the source of truth.",
            kind="fact",
        )
        deleted = self.db.delete(scope=self.scope, head_id=created["head_id"])
        after_delete = self.db.search(scope=self.scope, query="source of truth", top_k=3)
        restored = self.db.restore(scope=self.scope, head_id=created["head_id"])
        after_restore = self.db.search(scope=self.scope, query="source of truth", top_k=3)

        self.assertEqual(deleted["state"], "deleted")
        self.assertEqual(after_delete, [])
        self.assertEqual(restored["state"], "active")
        self.assertTrue(after_restore)

    def test_feedback_preserves_scope_and_versions_record(self) -> None:
        created = self.db.put(
            scope=self.scope,
            text="User wants concise release updates.",
            kind="preference",
            fact_key="style.release_updates",
        )
        updated = self.db.feedback(
            scope=self.scope,
            head_id=created["head_id"],
            text="User wants concise release updates with a one-line conclusion first.",
        )
        current = self.db.get(scope=self.scope, head_id=created["head_id"])

        self.assertEqual(updated["head_id"], created["head_id"])
        self.assertEqual(updated["scope_key"], self.scope.key)
        self.assertEqual(current["version_id"], updated["version_id"])
        self.assertEqual(current["workspace_id"], self.scope.workspace_id)

    def test_scoped_wrapper_rejects_cross_scope_access(self) -> None:
        other = self.db.put(
            scope=Scope(workspace_id="ws.other", project_id="proj.beta", user_id="user-2", agent_id="planner"),
            text="Other workspace memory.",
            kind="fact",
        )
        scoped = self.db.scoped(self.scope)

        with self.assertRaises(InvalidScope):
            scoped.get(other["head_id"])

        with self.assertRaises(InvalidScope):
            self.db.get(scope=self.scope, head_id=other["head_id"])

    def test_access_flush_honors_threshold(self) -> None:
        self.db.close()
        self.db = AIMemory({"root_dir": self.root / ".threshold", "flush_access_every": 3, "auto_flush": True})
        created = self.db.put(
            scope=self.scope,
            text="Use SQLite for durable metadata.",
            kind="fact",
        )

        self.db.search(scope=self.scope, query="durable metadata", top_k=1)
        self.assertEqual(self.db.get(scope=self.scope, head_id=created["head_id"])["access_count"], 0)

        self.db.search(scope=self.scope, query="durable metadata", top_k=1)
        self.db.search(scope=self.scope, query="durable metadata", top_k=1)
        self.assertEqual(self.db.get(scope=self.scope, head_id=created["head_id"])["access_count"], 3)

    def test_query_cache_invalidates_on_write(self) -> None:
        first = self.db.put(
            scope=self.scope,
            text="Storage decision: SQLite handles durable state.",
            kind="fact",
        )
        initial = self.db.search(scope=self.scope, query="durable state", top_k=10)
        second = self.db.put(
            scope=self.scope,
            text="Storage decision: LMDB handles hot state.",
            kind="fact",
        )
        refreshed = self.db.search(scope=self.scope, query="state", top_k=10)

        self.assertEqual(len(initial), 1)
        self.assertEqual({initial[0]["head_id"]}, {first["head_id"]})
        self.assertEqual({hit["head_id"] for hit in refreshed}, {first["head_id"], second["head_id"]})

    def test_recover_on_open_flushes_pending_jobs_and_access(self) -> None:
        self.db.close()
        path = self.root / ".recovery"
        db = AIMemory({"root_dir": path, "auto_flush": False, "recover_on_open": False})
        created = db.put(
            scope=self.scope,
            text="Recovery should replay pending vector jobs.",
            kind="fact",
        )
        db.search(scope=self.scope, query="pending vector jobs", top_k=1)
        self.assertGreater(db.stats()["pending_jobs"], 0)
        self.assertEqual(db.get(scope=self.scope, head_id=created["head_id"])["access_count"], 0)
        db.close()

        reopened = AIMemory({"root_dir": path, "auto_flush": False, "recover_on_open": True})
        try:
            self.assertEqual(reopened.stats()["pending_jobs"], 0)
            self.assertEqual(reopened.get(scope=self.scope, head_id=created["head_id"])["access_count"], 1)
        finally:
            reopened.close()
        self.db = AIMemory.open(self.root / ".aimemory")

    def test_working_memory_search_prefers_hot_path_for_short_queries(self) -> None:
        scoped = self.db.scoped(self.scope)
        scoped.working_append("user", "Need release checklist and rollback steps.")
        hits = scoped.search("rollback", top_k=3)

        self.assertTrue(hits)
        self.assertEqual(hits[0]["layer"], "working")
        self.assertIn("rollback", hits[0]["text"].lower())

    def test_custom_retrieval_gate_can_skip_longterm_lookup(self) -> None:
        self.db.close()
        self.db = AIMemory({"root_dir": self.root / ".gate"}, retrieval_gate=NeverRetrieveGate())
        self.db.put(
            scope=self.scope,
            text="Long-term fact that should be skipped by the gate.",
            kind="fact",
        )
        hot_hits = self.db.search(scope=self.scope, query="long-term fact", top_k=3)
        self.assertTrue(hot_hits)
        self.assertEqual(hot_hits[0]["layer"], "working")

        self.db.working_append(scope=self.scope, role="user", content="Working note: long-term fact shortcut.")
        hits = self.db.search(scope=self.scope, query="long-term fact", top_k=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["layer"], "working")

    def test_custom_reranker_can_reorder_hits(self) -> None:
        self.db.close()
        self.db = AIMemory({"root_dir": self.root / ".rerank"}, reranker=ReverseReranker())
        first = self.db.put(
            scope=self.scope,
            text="Storage stack includes SQLite and LMDB.",
            kind="fact",
        )
        second = self.db.put(
            scope=self.scope,
            text="Storage stack includes SQLite, LMDB, and LanceDB.",
            kind="fact",
        )
        hits = self.db.search(scope=self.scope, query="storage stack", top_k=2)

        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["head_id"], first["head_id"])
        self.assertEqual(hits[1]["head_id"], second["head_id"])

    def test_lifecycle_promotes_frequent_important_memory_to_core(self) -> None:
        self.db.close()
        self.db = AIMemory(
            {
                "root_dir": self.root / ".lifecycle-core",
                "auto_flush": False,
                "lifecycle_core_promote_access_count": 3,
            }
        )
        created = self.db.put(
            scope=self.scope,
            text="Architecture decision: SQLite remains the durable source of truth.",
            kind="fact",
            importance=0.95,
            confidence=0.95,
        )

        for _ in range(3):
            self.db.search(scope=self.scope, query="durable source of truth", top_k=1)
        lifecycle = self.db.flush()
        current = self.db.get(scope=self.scope, head_id=created["head_id"])
        history = self.db.history(scope=self.scope, head_id=created["head_id"])

        self.assertEqual(current["tier"], "core")
        self.assertEqual(lifecycle["lifecycle_changed"], 1)
        self.assertIn("tier_changed", [event["event_type"] for event in history["events"]])

    def test_lifecycle_demotes_stale_low_signal_memory_to_cold(self) -> None:
        self.db.close()
        self.db = AIMemory(
            {
                "root_dir": self.root / ".lifecycle-cold",
                "auto_flush": False,
                "lifecycle_cold_after_ms": 10,
            }
        )
        created = self.db.put(
            scope=self.scope,
            text="Temporary note: revisit experiment naming later.",
            kind="summary",
            importance=0.1,
            confidence=0.2,
        )
        stale_at = now_ms() - (90 * 24 * 60 * 60 * 1000)
        with self.db.catalog.transaction():
            self.db.catalog._conn.execute(
                "UPDATE memory_heads SET updated_at = ?, last_accessed_at = ? WHERE head_id = ?",
                (stale_at, stale_at, created["head_id"]),
            )

        lifecycle = self.db.run_lifecycle()
        current = self.db.get(scope=self.scope, head_id=created["head_id"])

        self.assertEqual(current["tier"], "cold")
        self.assertEqual(lifecycle["changed"], 1)
        self.assertGreaterEqual(lifecycle["jobs_processed"], 1)

    def test_ingest_records_and_jsonl_extend_the_scope(self) -> None:
        scoped = self.db.scoped(self.scope)
        records = scoped.ingest_records(
            [
                {"text": "SQLite stores durable metadata.", "kind": "fact"},
                {"text": "LMDB stores hot working state.", "kind": "fact"},
            ]
        )
        jsonl_path = self.root / "batch.jsonl"
        jsonl_path.write_text(
            "\n".join(
                [
                    '{"text":"LanceDB stores vector indexes.","kind":"fact"}',
                    '{"text":"User prefers concise status updates.","kind":"preference","fact_key":"style.status"}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        imported = scoped.ingest_jsonl(jsonl_path)
        listed = scoped.list(limit=10)
        hits = scoped.search("vector indexes", top_k=5)

        self.assertEqual(len(records), 2)
        self.assertEqual(len(imported), 2)
        self.assertEqual(len(listed), 4)
        self.assertTrue(any(hit["head_id"] == imported[0]["head_id"] for hit in hits))

    def test_put_many_is_atomic_when_a_later_item_fails(self) -> None:
        with self.assertRaises(TypeError):
            self.db.put_many(
                scope=self.scope,
                items=[
                    {"text": "First batch item should be rolled back.", "kind": "fact"},
                    {"text": "Second batch item breaks serialization.", "kind": "fact", "metadata": {"bad": {1, 2, 3}}},
                ],
            )

        self.assertEqual(self.db.list(scope=self.scope), [])
        self.assertEqual(self.db.stats()["heads"], 0)

    def test_export_jsonl_can_be_imported_into_another_scope(self) -> None:
        self.db.put(
            scope=self.scope,
            text="Exported fact: SQLite is durable.",
            kind="fact",
        )
        self.db.put(
            scope=self.scope,
            text="Exported preference: answer with conclusions first.",
            kind="preference",
            fact_key="style.conclusion_first",
        )
        export_path = self.root / "exports" / "memory-export.jsonl"
        export_info = self.db.export_jsonl(scope=self.scope, path=export_path)

        imported_db = AIMemory.open(self.root / ".imported")
        target_scope = self.scope.bind(workspace_id="ws.imported", user_id="user-9")
        try:
            imported = imported_db.import_jsonl(path=export_path, scope=target_scope)
            imported_records = imported_db.list(scope=target_scope, limit=10)

            self.assertEqual(export_info["count"], 2)
            self.assertEqual(len(imported), 2)
            self.assertEqual(len(imported_records), 2)
            self.assertEqual(imported_db.list(scope=self.scope), [])
            self.assertEqual({record["workspace_id"] for record in imported_records}, {"ws.imported"})
        finally:
            imported_db.close()

    def test_ingest_messages_uses_injected_extractor(self) -> None:
        self.db.close()
        self.db = AIMemory({"root_dir": self.root / ".extractor"}, extractor=StaticExtractor())
        records = self.db.ingest_messages(
            scope=self.scope,
            messages=[
                {"role": "user", "content": "Need concise rollout notes."},
                {"role": "assistant", "content": "Will keep the answer short."},
            ],
        )
        listed = self.db.list(scope=self.scope)

        self.assertEqual(len(records), 1)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["metadata"]["message_count"], 2)
        self.assertIn("concise rollout notes", listed[0]["text"].lower())


if __name__ == "__main__":
    unittest.main()
