from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from aimemory import AIMemory
from aimemory.algorithms.distill import AdaptiveDistiller
from aimemory.algorithms.dedupe import semantic_similarity
from aimemory.algorithms.segmentation import segment_text
from aimemory.core.router import DEFAULT_RETRIEVAL_DOMAINS, RetrievalRouter
from aimemory.core.text import extract_keywords, split_sentences
from aimemory.core.utils import json_dumps, make_id, utcnow_iso
from aimemory.memory_intelligence.models import FactCandidate, MemoryScopeContext
from aimemory.memory_intelligence.policies import MemoryPolicy
from aimemory.memory_intelligence.pipeline import MemoryIntelligencePipeline
from aimemory.providers.defaults import infer_query_profile


class AlgorithmicRetrievalTest(unittest.TestCase):
    def test_router_uses_fixed_domain_set_without_query_inference(self) -> None:
        router = RetrievalRouter()
        self.assertEqual(
            router.route("执行失败后如何回滚数据库并恢复会话上下文", session_id="sess-1"),
            list(DEFAULT_RETRIEVAL_DOMAINS),
        )
        profile = infer_query_profile(
            "执行失败后如何回滚数据库并恢复会话上下文",
            context=MemoryScopeContext(session_id="sess-1"),
            policy=MemoryPolicy(),
        )
        self.assertEqual(profile["handoff_domains"], [])
        self.assertFalse(profile["needs_interaction"])
        self.assertFalse(profile["needs_execution"])
        self.assertFalse(profile["needs_archive"])
        self.assertEqual(profile["preferred_scope"], "session")

    def test_extract_keywords_prefers_stable_terms_over_ascii_ngrams(self) -> None:
        keywords = extract_keywords(
            "interface governance interface compatibility rollback strategy compatibility"
        )
        self.assertIn("interface", keywords)
        self.assertIn("compatibility", keywords)
        self.assertNotIn("int", keywords)
        self.assertNotIn("omp", keywords)

    def test_split_sentences_handles_cjk_punctuation_without_whitespace(self) -> None:
        parts = split_sentences("发布前执行预检查。发布前再次校验凭证。失败后立即回滚。")
        self.assertEqual(
            parts,
            [
                "发布前执行预检查。",
                "发布前再次校验凭证。",
                "失败后立即回滚。",
            ],
        )

    def test_semantic_similarity_separates_near_duplicates_from_unrelated_text(self) -> None:
        left = "发布失败后需要恢复数据库快照，并重新校验接口状态。"
        right = "如果发布失败，必须恢复数据库快照，再次校验接口状态。"
        unrelated = "发布完成后整理周报，并同步会议纪要。"
        self.assertGreater(semantic_similarity(left, right), semantic_similarity(left, unrelated))

    def test_segment_text_groups_cohesive_sentences_into_semantic_spans(self) -> None:
        units = segment_text(
            """
            # 发布说明
            发布前执行 precheck，并确认 migration plan 正确。发布前再次校验凭证和磁盘空间。
            如果 smoke test 失败，立即回滚数据库快照并恢复应用版本。
            """
        )
        sentence_units = [unit for unit in units if unit.level == "sentence"]
        self.assertEqual(len(sentence_units), 2)
        self.assertIn("migration plan", sentence_units[0].text)
        self.assertIn("回滚数据库快照", sentence_units[1].text)

    def test_pipeline_candidate_similarity_does_not_require_keywords(self) -> None:
        pipeline = MemoryIntelligencePipeline.__new__(MemoryIntelligencePipeline)
        left = FactCandidate(
            text="发布失败后需要恢复数据库快照，并重新校验接口状态。",
            memory_type="semantic",
            confidence=0.8,
            importance=0.7,
            metadata={},
        )
        right = FactCandidate(
            text="如果发布失败，必须恢复数据库快照，再次校验接口状态。",
            memory_type="semantic",
            confidence=0.78,
            importance=0.69,
            metadata={},
        )
        similarity = pipeline._candidate_similarity(left, right)
        self.assertGreaterEqual(similarity, 0.75)
        merged = pipeline._merge_candidates(left, right)
        self.assertNotIn("keywords", merged.metadata)

    def test_distill_slot_scores_prefer_structure_and_numeric_density(self) -> None:
        items = AdaptiveDistiller(MemoryPolicy()).distill_units(
            segment_text(
                """
                1. prepare release manifest
                2. deploy build 42
                3. verify checkout flow

                - CPU <= 70%
                - 30 minute window
                """
            ),
            domain_hint="skill_reference",
            limit=20,
        )
        by_text = {item.text: item for item in items if item.level == "list_item"}
        self.assertGreater(by_text["prepare release manifest"].actionability_score, by_text["CPU <= 70%"].actionability_score)
        self.assertGreater(by_text["CPU <= 70%"].constraint_score, by_text["deploy build 42"].constraint_score)
        self.assertLess(by_text["deploy build 42"].constraint_score, 0.35)

    def test_distill_risk_score_uses_terminal_contrast_over_keyword_markers(self) -> None:
        items = AdaptiveDistiller(MemoryPolicy()).distill_units(
            segment_text(
                """
                1. prepare release manifest
                2. deploy build 42
                3. rebuild previous image, reopen gateway, resync queue.
                """
            ),
            domain_hint="skill_reference",
            limit=20,
        )
        by_text = {item.text: item for item in items if item.level == "list_item"}
        self.assertGreater(
            by_text["rebuild previous image, reopen gateway, resync queue."].risk_score,
            by_text["deploy build 42"].risk_score,
        )
        self.assertGreaterEqual(by_text["rebuild previous image, reopen gateway, resync queue."].risk_score, 0.3)

    def test_interaction_and_execution_search_use_semantic_indexes(self) -> None:
        with TemporaryDirectory() as tempdir:
            memory = AIMemory({"root_dir": tempdir})
            try:
                session = memory.api.session.create(
                    owner_agent_id="agent.alpha",
                    subject_type="human",
                    subject_id="user-1",
                    title="semantic-search",
                )
                phrase = "稀有交互短语：全链路配额折叠策略"
                memory.api.session.append(
                    session["id"],
                    "user",
                    phrase,
                    auto_capture=False,
                    auto_compress=False,
                )
                interaction_result = memory.api.recall.query(
                    phrase,
                    owner_agent_id="agent.alpha",
                    subject_type="human",
                    subject_id="user-1",
                    session_id=session["id"],
                    domains=["interaction"],
                    limit=3,
                )
                self.assertTrue(interaction_result["results"])
                self.assertGreater(
                    memory.db.fetch_one(
                        "SELECT COUNT(*) AS count FROM semantic_index_cache WHERE collection = 'interaction_turn'"
                    )["count"],
                    0,
                )
                interaction_vector_hits = memory.vector_index.search("interaction_turn", phrase, limit=3)
                self.assertTrue(
                    any(str(item.get("id") or item.get("record_id")) == interaction_result["results"][0]["id"] for item in interaction_vector_hits)
                )

                run = memory.api.execution.start_run(
                    user_id="user-1",
                    goal="稀有执行目标：回滚编排口令",
                    owner_agent_id="agent.alpha",
                    subject_type="human",
                    subject_id="user-1",
                )
                observation_id = make_id("obs")
                created_at = utcnow_iso()
                memory.db.execute(
                    """
                    INSERT INTO observations(id, run_id, task_id, session_id, kind, content, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation_id,
                        run["id"],
                        None,
                        run.get("session_id"),
                        "note",
                        "执行观察：需要恢复数据库快照并重新校验接口状态。",
                        json_dumps({}),
                        created_at,
                    ),
                )
                observation = memory.db.fetch_one("SELECT * FROM observations WHERE id = ?", (observation_id,))
                self.assertIsNotNone(observation)
                memory._index_execution_observation(dict(observation or {}), run=run)
                execution_result = memory.api.execution.search(
                    "稀有执行目标：回滚编排口令",
                    user_id="user-1",
                    owner_agent_id="agent.alpha",
                    limit=3,
                )
                self.assertTrue(execution_result["results"])
                self.assertGreater(
                    memory.db.fetch_one(
                        "SELECT COUNT(*) AS count FROM semantic_index_cache WHERE collection = 'execution_run'"
                    )["count"],
                    0,
                )
                self.assertGreater(
                    memory.db.fetch_one(
                        "SELECT COUNT(*) AS count FROM semantic_index_cache WHERE collection = 'execution_observation'"
                    )["count"],
                    0,
                )
                execution_vector_hits = memory.vector_index.search("execution_run", "稀有执行目标：回滚编排口令", limit=3)
                self.assertTrue(
                    any(str(item.get("id") or item.get("record_id")) == execution_result["results"][0]["id"] for item in execution_vector_hits)
                )
            finally:
                memory.close()


if __name__ == "__main__":
    unittest.main()
