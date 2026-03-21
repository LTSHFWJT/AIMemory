from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from aimemory import AIMemory, Scope, SearchQuery, SearchResult
from aimemory.errors import InvalidScope
from aimemory.pipeline.lifecycle import derive_fact_key, now_ms


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


class CountingEmbedder:
    def __init__(self, dimension: int = 32):
        self.dimension = dimension
        self.model_name = f"counting-{dimension}"
        self.calls = 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls += len(texts)
        return [[0.0] * self.dimension for _ in texts]


class FakeVectorBuilder:
    def __init__(self, capture: dict[str, object]):
        self.capture = capture

    def where(self, expression: str, prefilter: bool = False) -> "FakeVectorBuilder":
        self.capture["where"] = expression
        self.capture["prefilter"] = prefilter
        return self

    def limit(self, limit: int) -> "FakeVectorBuilder":
        self.capture["limit"] = limit
        return self

    def to_list(self) -> list[dict]:
        return []


class FakeVectorTable:
    def __init__(self, capture: dict[str, object]):
        self.capture = capture

    def search(self, vector: list[float]) -> FakeVectorBuilder:
        self.capture["vector"] = vector
        return FakeVectorBuilder(self.capture)


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

    def _wait_until(self, predicate, *, timeout_s: float = 2.0, interval_s: float = 0.02) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(interval_s)
        return predicate()

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

    def test_query_returns_typed_search_result(self) -> None:
        created = self.db.put(
            scope=self.scope,
            text="Release preference: keep status updates concise.",
            kind="preference",
        )

        result = self.db.query(
            scope=self.scope,
            search=SearchQuery(query="status update preference", top_k=3),
        )

        self.assertIsInstance(result, SearchResult)
        self.assertTrue(result.used_working_memory)
        self.assertTrue(result.used_longterm_memory)
        self.assertTrue(result.hits)
        self.assertEqual(result.hits[0].head_id, created["head_id"])

    def test_query_cache_preserves_structured_result_metadata(self) -> None:
        result = self.db.query(
            scope=self.scope,
            search=SearchQuery(query="unmatched retrieval phrase", top_k=3),
        )

        self.assertFalse(result.hits)
        self.assertFalse(result.used_working_memory)
        self.assertFalse(result.used_longterm_memory)

        self.db.reader._search_working_memory = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("working path should not rerun"))
        self.db.reader._search_longterm = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("longterm path should not rerun"))

        cached = self.db.query(
            scope=self.scope,
            search=SearchQuery(query="unmatched retrieval phrase", top_k=3),
        )

        self.assertFalse(cached.hits)
        self.assertFalse(cached.used_working_memory)
        self.assertFalse(cached.used_longterm_memory)

    def test_runtime_manifest_is_written_on_open(self) -> None:
        manifest_path = self.root / ".aimemory" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["format"], "aimemory.store.v1")
        self.assertEqual(manifest["storage"]["catalog"], "sqlite")
        self.assertEqual(manifest["storage"]["hotstore"], "lmdb")
        self.assertEqual(manifest["storage"]["vector"], "lancedb")
        self.assertEqual(manifest["vector_dim"], self.db.config.vector_dim)

    def test_vector_store_pushes_supported_filters_to_lancedb(self) -> None:
        capture: dict[str, object] = {}
        original_table = self.db.vector_store._table
        self.db.vector_store._table = FakeVectorTable(capture)
        try:
            self.db.vector_store.search(
                scope_key=self.scope.key,
                vector=[0.0] * self.db.config.vector_dim,
                limit=7,
                filters={
                    "kind": {"in": ["fact", "preference"]},
                    "tier": {"eq": "core"},
                    "importance": {"gte": 0.8},
                    "layer": {"eq": "longterm"},
                },
            )
        finally:
            self.db.vector_store._table = original_table

        where = str(capture["where"])
        self.assertIn(f"scope_key = '{self.scope.key}'", where)
        self.assertIn("kind IN ('fact', 'preference')", where)
        self.assertIn("tier = 'core'", where)
        self.assertIn("importance >= 0.8", where)
        self.assertNotIn("layer", where)
        self.assertEqual(capture["limit"], 7)
        self.assertTrue(capture["prefilter"])

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
        self.assertEqual(history["head_state"], "active")
        self.assertEqual(history["versions"][0]["state"], "superseded")
        self.assertEqual(history["versions"][1]["state"], "active")
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

    def test_archive_and_restore_archive_affect_listing_and_search(self) -> None:
        created = self.db.put(
            scope=self.scope,
            text="Archive target: durable architecture note.",
            kind="fact",
        )

        archived = self.db.archive(scope=self.scope, head_id=created["head_id"])
        listed_default = self.db.list(scope=self.scope, limit=10)
        listed_archived = self.db.list(scope=self.scope, filters={"state": {"eq": "archived"}}, limit=10)
        hits_archived = self.db.search(scope=self.scope, query="durable architecture note", top_k=3)

        self.assertEqual(archived["state"], "archived")
        self.assertEqual(listed_default, [])
        self.assertEqual(len(listed_archived), 1)
        self.assertEqual(listed_archived[0]["head_id"], created["head_id"])
        self.assertEqual(hits_archived, [])

        restored = self.db.restore_archive(scope=self.scope, head_id=created["head_id"])
        hits_restored = self.db.search(scope=self.scope, query="durable architecture note", top_k=3)
        history = self.db.history(scope=self.scope, head_id=created["head_id"])

        self.assertEqual(restored["state"], "active")
        self.assertTrue(hits_restored)
        self.assertIn("archived", [event["event_type"] for event in history["events"]])
        self.assertIn("archive_restored", [event["event_type"] for event in history["events"]])

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

    def test_access_flush_honors_time_window(self) -> None:
        self.db.close()
        self.db = AIMemory(
            {
                "root_dir": self.root / ".interval",
                "worker_mode": "library_only",
                "flush_access_every": 100,
                "flush_access_interval_ms": 60,
                "auto_flush": True,
            }
        )
        created = self.db.put(
            scope=self.scope,
            text="Use LMDB to absorb short-lived access deltas.",
            kind="fact",
        )

        self.db.search(scope=self.scope, query="access deltas", top_k=1)
        self.assertEqual(self.db.get(scope=self.scope, head_id=created["head_id"])["access_count"], 0)

        time.sleep(0.09)
        self.db.search(scope=self.scope, query="access deltas", top_k=1)
        self.assertEqual(self.db.get(scope=self.scope, head_id=created["head_id"])["access_count"], 2)

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

    def test_embedded_worker_processes_pending_jobs_and_access_without_manual_flush(self) -> None:
        self.db.close()
        self.db = AIMemory(
            {
                "root_dir": self.root / ".embedded-worker",
                "worker_mode": "embedded",
                "auto_flush": False,
                "worker_poll_interval_ms": 25,
                "worker_lease_ttl_ms": 200,
                "flush_access_interval_ms": 50,
            }
        )
        created = self.db.put(
            scope=self.scope,
            text="Embedded worker should drain pending vector jobs in the background.",
            kind="fact",
        )

        self.assertGreater(self.db.stats()["pending_jobs"], 0)
        self.assertTrue(self._wait_until(lambda: self.db.stats()["pending_jobs"] == 0))

        self.db.search(scope=self.scope, query="background vector jobs", top_k=1)
        self.assertEqual(self.db.get(scope=self.scope, head_id=created["head_id"])["access_count"], 0)
        self.assertTrue(self._wait_until(lambda: self.db.get(scope=self.scope, head_id=created["head_id"])["access_count"] == 1))

        status = self.db.worker_status()
        self.assertTrue(status["alive"])
        self.assertTrue(status["leader"])

    def test_embedded_workers_share_a_single_lease_and_handover_on_close(self) -> None:
        self.db.close()
        shared_root = self.root / ".shared-embedded"
        db1 = AIMemory(
            {
                "root_dir": shared_root,
                "worker_mode": "embedded",
                "auto_flush": False,
                "worker_poll_interval_ms": 25,
                "worker_lease_ttl_ms": 120,
            }
        )
        db2 = AIMemory(
            {
                "root_dir": shared_root,
                "worker_mode": "embedded",
                "auto_flush": False,
                "worker_poll_interval_ms": 25,
                "worker_lease_ttl_ms": 120,
            }
        )
        try:
            self.assertTrue(
                self._wait_until(
                    lambda: sum(1 for status in (db1.worker_status(), db2.worker_status()) if status["leader"]) == 1
                )
            )
            first_status = (db1.worker_status(), db2.worker_status())
            self.assertEqual(sum(1 for status in first_status if status["leader"]), 1)

            leader = db1 if first_status[0]["leader"] else db2
            follower = db2 if leader is db1 else db1
            leader.close()

            self.assertTrue(self._wait_until(lambda: follower.worker_status()["leader"]))
        finally:
            try:
                db1.close()
            except Exception:
                pass
            try:
                db2.close()
            except Exception:
                pass
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

    def test_semantic_dedupe_reuses_existing_head_after_flush(self) -> None:
        first = self.db.put(
            scope=self.scope,
            text="Architecture note: SQLite remains the durable source of truth.",
            kind="fact",
            vector=[0.35] * self.db.config.vector_dim,
        )
        second = self.db.put(
            scope=self.scope,
            text="Architecture note: SQLite stays the durable system of record.",
            kind="fact",
            vector=[0.35] * self.db.config.vector_dim,
        )
        listed = self.db.list(scope=self.scope, limit=10)
        history = self.db.history(scope=self.scope, head_id=first["head_id"])

        self.assertEqual(second["head_id"], first["head_id"])
        self.assertEqual(len(listed), 1)
        self.assertTrue(
            any(
                event["event_type"] == "deduplicated" and event["payload"].get("mode") == "semantic"
                for event in history["events"]
            )
        )

    def test_semantic_dedupe_applies_within_put_many_batch(self) -> None:
        self.db.close()
        self.db = AIMemory({"root_dir": self.root / ".semantic-batch", "auto_flush": False})
        records = self.db.put_many(
            scope=self.scope,
            items=[
                {
                    "text": "Release checklist draft for the deployment train.",
                    "kind": "fact",
                    "vector": [0.12] * self.db.config.vector_dim,
                },
                {
                    "text": "Deployment train release checklist draft.",
                    "kind": "fact",
                    "vector": [0.12] * self.db.config.vector_dim,
                },
            ],
        )

        self.assertEqual(records[0]["head_id"], records[1]["head_id"])
        self.assertEqual(self.db.stats()["heads"], 1)
        self.assertEqual(len(self.db.list(scope=self.scope)), 1)

    def test_semantic_dedupe_does_not_merge_different_versioned_fact_keys(self) -> None:
        first = self.db.put(
            scope=self.scope,
            text="User prefers concise answers.",
            kind="preference",
            fact_key="style.concise",
            vector=[0.48] * self.db.config.vector_dim,
        )
        second = self.db.put(
            scope=self.scope,
            text="User prefers concise responses.",
            kind="preference",
            fact_key="style.responses",
            vector=[0.48] * self.db.config.vector_dim,
        )

        self.assertNotEqual(first["head_id"], second["head_id"])
        self.assertEqual(len(self.db.list(scope=self.scope, limit=10)), 2)

    def test_procedure_is_append_only_by_default(self) -> None:
        first = self.db.put(
            scope=self.scope,
            text="Release procedure: run smoke tests, then deploy.",
            kind="procedure",
            fact_key="proc.release",
            vector=[0.21] * self.db.config.vector_dim,
        )
        second = self.db.put(
            scope=self.scope,
            text="Release procedure: run smoke tests, deploy, then verify metrics.",
            kind="procedure",
            fact_key="proc.release",
            vector=[0.22] * self.db.config.vector_dim,
        )

        self.assertNotEqual(first["head_id"], second["head_id"])
        self.assertEqual(len(self.db.list(scope=self.scope, limit=10)), 2)

    def test_procedure_can_supersede_by_fact_key(self) -> None:
        self.db.close()
        self.db = AIMemory(
            {
                "root_dir": self.root / ".procedure-versioned",
                "procedure_version_mode": "supersede_by_fact_key",
            }
        )
        first = self.db.put(
            scope=self.scope,
            text="Incident procedure: identify blast radius, then contain.",
            kind="procedure",
            fact_key="proc.incident",
        )
        second = self.db.put(
            scope=self.scope,
            text="Incident procedure: identify blast radius, contain, then communicate.",
            kind="procedure",
            fact_key="proc.incident",
        )
        history = self.db.history(scope=self.scope, head_id=first["head_id"])
        current = self.db.get(scope=self.scope, head_id=first["head_id"])

        self.assertEqual(first["head_id"], second["head_id"])
        self.assertEqual(len(history["versions"]), 2)
        self.assertEqual(history["versions"][0]["state"], "superseded")
        self.assertEqual(current["text"], "Incident procedure: identify blast radius, contain, then communicate.")

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

    def test_export_package_import_package_preserves_history_and_deleted_state(self) -> None:
        first = self.db.put(
            scope=self.scope,
            text="User prefers short answers.",
            kind="preference",
            fact_key="style.answer",
        )
        self.db.put(
            scope=self.scope,
            text="User prefers short answers with a one-line summary first.",
            kind="preference",
            fact_key="style.answer",
        )
        deleted = self.db.put(
            scope=self.scope,
            text="Temporary storage note scheduled for removal.",
            kind="fact",
        )
        self.db.delete(scope=self.scope, head_id=deleted["head_id"])
        archived = self.db.put(
            scope=self.scope,
            text="Archived storage note that should stay out of retrieval.",
            kind="fact",
        )
        self.db.archive(scope=self.scope, head_id=archived["head_id"])

        package_dir = self.root / "exports" / "history-package"
        export_info = self.db.export_package(scope=self.scope, path=package_dir)

        imported_db = AIMemory.open(self.root / ".package-import")
        target_scope = self.scope.bind(workspace_id="ws.package", user_id="user-7")
        try:
            import_info = imported_db.import_package(path=package_dir, scope=target_scope)
            current = imported_db.get(scope=target_scope, head_id=first["head_id"])
            deleted_record = imported_db.get(scope=target_scope, head_id=deleted["head_id"])
            archived_record = imported_db.get(scope=target_scope, head_id=archived["head_id"])
            history = imported_db.history(scope=target_scope, head_id=first["head_id"])
            hits = imported_db.search(scope=target_scope, query="one-line summary", top_k=3)
            package_manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            archived_hits = imported_db.search(scope=target_scope, query="Archived storage note", top_k=3)

            self.assertEqual(package_manifest["format"], "aimemory.export.v1")
            self.assertEqual(export_info["heads"], 3)
            self.assertEqual(export_info["versions"], 4)
            self.assertEqual(import_info["heads"], 3)
            self.assertEqual(import_info["versions"], 4)
            self.assertEqual(len(history["versions"]), 2)
            self.assertEqual(current["workspace_id"], "ws.package")
            self.assertEqual(deleted_record["workspace_id"], "ws.package")
            self.assertEqual(deleted_record["state"], "deleted")
            self.assertEqual(archived_record["state"], "archived")
            self.assertTrue(any(hit["head_id"] == first["head_id"] for hit in hits))
            self.assertFalse(any(hit["head_id"] == archived["head_id"] for hit in archived_hits))
        finally:
            imported_db.close()

    def test_retrieval_score_helper_applies_exact_fact_and_confidence_weights(self) -> None:
        now = now_ms()
        query = "User prefers concise answers"
        base_row = {
            "text": "User prefers concise answers for release reviews.",
            "vector_score": 0.45,
            "lexical_score": 0.40,
        }
        exact_head = {
            "kind": "preference",
            "fact_key": derive_fact_key("preference", query),
            "confidence": 0.95,
            "tier": "active",
            "updated_at": now,
            "access_count": 0,
            "workspace_id": self.scope.workspace_id,
            "project_id": self.scope.project_id,
            "user_id": self.scope.user_id,
            "agent_id": self.scope.agent_id,
            "session_id": self.scope.session_id,
            "run_id": self.scope.run_id,
            "namespace": self.scope.namespace,
            "metadata": {},
        }
        inexact_head = dict(exact_head)
        inexact_head["fact_key"] = "pref.other"
        inexact_head["confidence"] = 0.20

        score_exact, parts_exact = self.db.reader._score_longterm_candidate(
            scope=self.scope,
            query=query,
            row=base_row,
            head_record=exact_head,
            now=now,
        )
        score_inexact, parts_inexact = self.db.reader._score_longterm_candidate(
            scope=self.scope,
            query=query,
            row=base_row,
            head_record=inexact_head,
            now=now,
        )

        self.assertEqual(parts_exact["exact_fact_boost"], 1.0)
        self.assertEqual(parts_inexact["exact_fact_boost"], 0.0)
        self.assertGreater(parts_exact["confidence_multiplier"], parts_inexact["confidence_multiplier"])
        self.assertGreater(score_exact, score_inexact)

    def test_restore_archive_enqueues_rebuild_vector_job(self) -> None:
        self.db.close()
        self.db = AIMemory({"root_dir": self.root / ".archive-jobs", "auto_flush": False})
        created = self.db.put(
            scope=self.scope,
            text="Job test: archive and rebuild vector entry.",
            kind="fact",
        )
        self.db.flush()
        self.db.archive(scope=self.scope, head_id=created["head_id"])
        archived_jobs = self.db.catalog.list_recoverable_jobs(10)
        self.assertTrue(any(job["op_type"] == "delete_vector" for job in archived_jobs))

        self.db.flush()
        self.db.restore_archive(scope=self.scope, head_id=created["head_id"])
        restored_jobs = self.db.catalog.list_recoverable_jobs(10)
        self.assertTrue(any(job["op_type"] == "rebuild_vector" for job in restored_jobs))

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

    def test_search_filters_apply_to_longterm_fields(self) -> None:
        old = self.db.put(
            scope=self.scope,
            text="Filter target: old low-importance storage note.",
            kind="fact",
            importance=0.2,
        )
        fresh = self.db.put(
            scope=self.scope,
            text="Filter target: fresh high-importance storage note.",
            kind="fact",
            importance=0.95,
        )
        stale_at = now_ms() - (120 * 24 * 60 * 60 * 1000)
        with self.db.catalog.transaction():
            self.db.catalog._conn.execute(
                "UPDATE memory_heads SET created_at = ?, updated_at = ? WHERE head_id = ?",
                (stale_at, stale_at, old["head_id"]),
            )

        hits = self.db.search(
            scope=self.scope,
            query="storage note",
            top_k=10,
            filters={
                "created_at": {"gte": fresh["created_at"]},
                "importance": {"gte": 0.8},
                "layer": {"eq": "longterm"},
            },
        )

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["head_id"], fresh["head_id"])

    def test_provided_vector_skips_document_embedding_on_flush(self) -> None:
        self.db.close()
        embedder = CountingEmbedder()
        self.db = AIMemory({"root_dir": self.root / ".provided-vector", "auto_flush": False}, embedder=embedder)
        self.db.put(
            scope=self.scope,
            text="Provided vector memory entry.",
            kind="fact",
            vector=[0.25] * embedder.dimension,
        )

        self.db.flush()
        self.assertEqual(embedder.calls, 0)
        hits = self.db.search(scope=self.scope, query="Provided vector memory entry", top_k=3)

        self.assertTrue(hits)


if __name__ == "__main__":
    unittest.main()
