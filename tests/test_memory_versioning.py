from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from aimemory import AIMemory
from aimemory.memory_intelligence.models import FactCandidate, MemoryAction, MemoryActionType, MemoryScopeContext, NeighborMemory
from aimemory.memory_intelligence.pipeline import MemoryIntelligencePipeline
from aimemory.memory_intelligence.policies import MemoryPolicy
from aimemory.providers.defaults import AdaptiveMemoryPlanner


class _KernelBackedMemoryService:
    def __init__(self, kernel: AIMemory):
        self.kernel = kernel

    def get(self, memory_id: str):
        return self.kernel.get(memory_id)

    def remember(self, **kwargs):
        return self.kernel.memory_store(**kwargs)

    def update(self, memory_id: str, **kwargs):
        return self.kernel.update(memory_id, **kwargs)

    def supersede(self, memory_id: str, **kwargs):
        return self.kernel.supersede_memory(memory_id, **kwargs)

    def link(self, source_memory_id: str, target_memory_ids, **kwargs):
        return self.kernel.link_memory(source_memory_id, target_memory_ids, **kwargs)

    def delete(self, memory_id: str):
        return self.kernel.delete(memory_id)


class MemoryVersioningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.memory = AIMemory({"root_dir": self.tempdir.name})

    def tearDown(self) -> None:
        self.memory.close()
        self.tempdir.cleanup()

    def _scope_kwargs(self) -> dict[str, str]:
        return {
            "owner_agent_id": "agent.planner",
            "subject_type": "human",
            "subject_id": "user-1",
        }

    def test_structured_api_supersede_creates_version_chain_and_audit_history(self) -> None:
        base = self.memory.api.long_term.add("发布窗口是周二 10:00。", **self._scope_kwargs())
        replaced = self.memory.api.long_term.supersede(
            base["id"],
            text="发布窗口改为周三 14:00，并通知执行代理。",
            reason_code="schedule_change",
        )

        self.assertEqual(replaced["version"], 2)
        self.assertEqual(replaced["supersedes_memory_id"], base["id"])

        stale = self.memory.api.long_term.get(base["id"])
        self.assertEqual(stale["status"], "superseded")
        self.assertEqual(stale["superseded_by_memory_id"], replaced["id"])

        stale_events = [item["event_type"] for item in self.memory.api.long_term.history(base["id"])]
        self.assertIn("SUPERSEDED", stale_events)

        fresh_history = self.memory.api.long_term.history(replaced["id"])
        self.assertEqual(fresh_history[-1]["event_type"], "SUPERSEDE")
        self.assertEqual(fresh_history[-1]["reason_code"], "schedule_change")
        self.assertEqual(fresh_history[-1]["version"], 2)
        self.assertEqual(fresh_history[-1]["source_table"], "long_term_memories")
        self.assertEqual(fresh_history[-1]["payload"]["supersedes_memory_id"], base["id"])

        self.assertEqual(
            self.memory.db.fetch_one(
                """
                SELECT COUNT(*) AS count
                FROM memory_links
                WHERE source_memory_id = ? AND target_memory_id = ? AND link_type = 'supersedes'
                """,
                (replaced["id"], base["id"]),
            )["count"],
            1,
        )

    def test_manual_link_survives_reindexing_and_is_audited(self) -> None:
        upstream = self.memory.api.long_term.add("执行代理负责确认发布时间窗。", **self._scope_kwargs())
        downstream = self.memory.api.long_term.add("回滚负责人是值班 SRE。", **self._scope_kwargs())

        linked = self.memory.api.long_term.link(
            upstream["id"],
            downstream["id"],
            link_type="depends_on",
            confidence=0.91,
            reason_code="workflow_dependency",
        )
        self.assertEqual(linked["target_memory_ids"], [downstream["id"]])

        updated = self.memory.api.long_term.update(
            upstream["id"],
            text="执行代理负责确认发布时间窗，并同步回滚负责人。",
            mode="merge",
            reason_code="merge_refresh",
        )
        self.assertEqual(updated["_event"], "MERGE")

        row = self.memory.db.fetch_one(
            """
            SELECT *
            FROM memory_links
            WHERE source_memory_id = ? AND target_memory_id = ? AND link_type = 'depends_on'
            """,
            (upstream["id"], downstream["id"]),
        )
        self.assertIsNotNone(row)
        self.assertAlmostEqual(float(row["confidence"]), 0.91, places=6)
        self.assertEqual(row["source_domain"], "memory")
        self.assertEqual(row["target_domain"], "memory")

        history = self.memory.api.long_term.history(upstream["id"])
        self.assertIn("LINK", [item["event_type"] for item in history])
        self.assertIn("MERGE", [item["event_type"] for item in history])

    def test_adaptive_planner_emits_supersede_and_context_actions(self) -> None:
        planner = AdaptiveMemoryPlanner()
        policy = MemoryPolicy(conflict_threshold=0.35, contradiction_threshold=0.35, merge_threshold=0.82, contextualize_threshold=0.35, duplicate_threshold=0.95, relation_threshold=0.2)
        context = MemoryScopeContext(owner_agent_id="agent.planner", subject_type="human", subject_id="user-1")

        supersede_candidate = FactCandidate(
            text="发布窗口改为周三 14:00。",
            memory_type="semantic",
            semantic_category="entities",
            fact_key="entities:发布窗口",
            topic_key="entities:发布窗口",
            confidence=0.84,
            importance=0.8,
        )
        supersede_neighbor = NeighborMemory(
            id="mem-old",
            text="发布窗口是周二 10:00。",
            score=0.7,
            memory_type="semantic",
            importance=0.7,
            semantic_category="entities",
            metadata={"targetable": True, "fact_key": "entities:发布窗口", "topic_key": "entities:发布窗口"},
        )
        supersede_actions = planner.plan(supersede_candidate, [supersede_neighbor], context=context, policy=policy)
        self.assertEqual(supersede_actions[0].action_type, MemoryActionType.SUPERSEDE)

        contextualize_candidate = FactCandidate(
            text="晚上更喜欢喝茶。",
            memory_type="preference",
            semantic_category="preferences",
            fact_key="preferences:饮品偏好",
            topic_key="preferences:饮品偏好",
            context_label="evening",
            confidence=0.76,
            importance=0.7,
            metadata={"keywords": ["茶", "饮品"], "contexts": ["evening"]},
        )
        contextualize_neighbor = NeighborMemory(
            id="mem-pref",
            text="平时喜欢喝咖啡。",
            score=0.62,
            memory_type="preference",
            importance=0.65,
            semantic_category="preferences",
            metadata={
                "targetable": True,
                "fact_key": "preferences:饮品偏好",
                "topic_key": "preferences:饮品偏好",
                "keywords": ["咖啡", "饮品"],
                "contexts": ["morning"],
            },
        )
        contextualize_actions = planner.plan(contextualize_candidate, [contextualize_neighbor], context=context, policy=policy)
        self.assertEqual(contextualize_actions[0].action_type, MemoryActionType.CONTEXTUALIZE)

    def test_pipeline_apply_uses_supersede_and_link_persistence_paths(self) -> None:
        base = self.memory.api.long_term.add("发布窗口是周二 10:00。", **self._scope_kwargs())
        related = self.memory.api.long_term.add("回滚负责人是值班 SRE。", **self._scope_kwargs())

        pipeline = MemoryIntelligencePipeline.__new__(MemoryIntelligencePipeline)
        pipeline.memory_service = _KernelBackedMemoryService(self.memory)

        context = MemoryScopeContext(
            user_id="user-1",
            agent_id="agent.planner",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
        )

        supersede_result = pipeline._apply_action(
            MemoryAction(
                MemoryActionType.SUPERSEDE,
                candidate=FactCandidate(
                    text="发布窗口改为周三 14:00，并通知执行代理。",
                    memory_type="semantic",
                    confidence=0.91,
                    importance=0.85,
                ),
                reason="planner-supersede",
                target_id=base["id"],
                previous_text=base["text"],
                confidence=0.91,
                evidence={"planner": "unit"},
            ),
            context=context,
            metadata=None,
            long_term=True,
            source="conversation",
        )
        self.assertEqual(supersede_result["event"], "SUPERSEDE")
        self.assertEqual(supersede_result["supersedes_memory_id"], base["id"])

        linked_result = pipeline._apply_action(
            MemoryAction(
                MemoryActionType.LINK,
                candidate=FactCandidate(
                    text="执行代理需要同步回滚负责人和新发布时间窗。",
                    memory_type="semantic",
                    confidence=0.77,
                    importance=0.74,
                ),
                reason="planner-link",
                confidence=0.77,
                link_target_ids=[supersede_result["id"], related["id"]],
                link_type="related",
                evidence={"planner": "unit"},
            ),
            context=context,
            metadata=None,
            long_term=True,
            source="conversation",
        )
        self.assertEqual(linked_result["event"], "LINK")
        self.assertEqual(set(linked_result["related_ids"]), {supersede_result["id"], related["id"]})

        count = self.memory.db.fetch_one(
            "SELECT COUNT(*) AS count FROM memory_links WHERE source_memory_id = ?",
            (linked_result["id"],),
        )["count"]
        self.assertEqual(count, 2)

        history = self.memory.history(linked_result["id"])
        self.assertEqual(history[-1]["event_type"], "LINK")
        self.assertEqual(history[-1]["reason_code"], "planner-link")

    def test_pipeline_apply_support_and_contradict_paths(self) -> None:
        base = self.memory.api.long_term.add(
            "用户偏好咖啡。",
            metadata={
                "semantic_category": "preferences",
                "memory_category": "preferences",
                "fact_key": "preferences:饮品偏好",
                "topic_key": "preferences:饮品偏好",
                "summary_l0": "饮品偏好: 咖啡",
                "summary_l1": "## Preference\n- 咖啡",
            },
            **self._scope_kwargs(),
        )

        pipeline = MemoryIntelligencePipeline.__new__(MemoryIntelligencePipeline)
        pipeline.memory_service = _KernelBackedMemoryService(self.memory)

        context = MemoryScopeContext(
            user_id="user-1",
            agent_id="agent.planner",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
        )

        support_result = pipeline._apply_action(
            MemoryAction(
                MemoryActionType.SUPPORT,
                candidate=FactCandidate(
                    text="用户仍然喜欢咖啡。",
                    memory_type="preference",
                    semantic_category="preferences",
                    fact_key="preferences:饮品偏好",
                    topic_key="preferences:饮品偏好",
                    confidence=0.81,
                    importance=0.74,
                    metadata={"semantic_category": "preferences", "memory_category": "preferences"},
                ),
                reason="planner-support",
                target_id=base["id"],
                previous_text=base["text"],
                confidence=0.81,
                context_label="general",
                evidence={"planner": "unit"},
            ),
            context=context,
            metadata=None,
            long_term=True,
            source="conversation",
        )
        self.assertEqual(support_result["event"], "SUPPORT")

        supported = self.memory.get(base["id"])
        support_info = supported["metadata"]["support_info"]
        self.assertEqual(support_info["total_observations"], 1)

        contradict_result = pipeline._apply_action(
            MemoryAction(
                MemoryActionType.CONTRADICT,
                candidate=FactCandidate(
                    text="用户晚上改喝茶。",
                    memory_type="preference",
                    semantic_category="preferences",
                    fact_key="preferences:饮品偏好",
                    topic_key="preferences:饮品偏好",
                    context_label="evening",
                    confidence=0.83,
                    importance=0.76,
                    metadata={"semantic_category": "preferences", "memory_category": "preferences"},
                ),
                reason="planner-contradict",
                target_id=base["id"],
                previous_text=base["text"],
                confidence=0.83,
                context_label="evening",
                evidence={"planner": "unit"},
            ),
            context=context,
            metadata=None,
            long_term=True,
            source="conversation",
        )
        self.assertEqual(contradict_result["event"], "CONTRADICT")

        link_row = self.memory.db.fetch_one(
            """
            SELECT *
            FROM memory_links
            WHERE source_memory_id = ? AND target_memory_id = ? AND link_type = 'contradicts'
            """,
            (contradict_result["id"], base["id"]),
        )
        self.assertIsNotNone(link_row)

        contradicted = self.memory.get(base["id"])
        contradiction_info = contradicted["metadata"]["support_info"]
        self.assertGreaterEqual(contradiction_info["total_observations"], 2)

    def test_pipeline_add_respects_append_only_strategy(self) -> None:
        existing = self.memory.api.long_term.add(
            "2026-03-20 发布窗口改为周二 10:00。",
            metadata={"semantic_category": "events", "memory_category": "events"},
            **self._scope_kwargs(),
        )

        pipeline = MemoryIntelligencePipeline.__new__(MemoryIntelligencePipeline)
        pipeline.memory_service = _KernelBackedMemoryService(self.memory)

        context = MemoryScopeContext(
            user_id="user-1",
            agent_id="agent.planner",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
        )

        created = pipeline._apply_action(
            MemoryAction(
                MemoryActionType.ADD,
                candidate=FactCandidate(
                    text="2026-03-21 发布窗口改为周三 14:00。",
                    memory_type="episodic",
                    semantic_category="events",
                    confidence=0.8,
                    importance=0.72,
                    metadata={"semantic_category": "events", "memory_category": "events"},
                ),
                reason="append-only-create",
                confidence=0.8,
            ),
            context=context,
            metadata=None,
            long_term=True,
            source="conversation",
        )
        self.assertEqual(created["event"], "ADD")
        self.assertNotEqual(created["id"], existing["id"])
        count = self.memory.db.fetch_one("SELECT COUNT(*) AS count FROM long_term_memories WHERE status = 'active'")["count"]
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
