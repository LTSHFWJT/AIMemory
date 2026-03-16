from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from aimemory import AIMemory


class AgentDomainAPITest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.memory = AIMemory(
            {
                "root_dir": self.tempdir.name,
                "memory_policy": {
                    "long_term_char_threshold": 40,
                    "long_term_compression_budget_chars": 60,
                    "short_term_char_threshold": 20,
                    "short_term_compression_budget_chars": 50,
                    "archive_char_threshold": 20,
                    "archive_compression_budget_chars": 60,
                    "compression_turn_threshold": 1,
                    "compression_preserve_recent_turns": 0,
                },
            }
        )

    def tearDown(self) -> None:
        self.memory.close()
        self.tempdir.cleanup()

    def test_domain_crud_and_scope_isolation(self) -> None:
        human = self.memory.api.long_term.add(
            "用户偏好简洁分点回答，并且希望所有输出都尽量先给结论。",
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
        )
        agent = self.memory.api.long_term.add(
            "agent.beta 在协作时偏好先拿完整上下文，再做执行。",
            owner_agent_id="agent.alpha",
            subject_type="agent",
            subject_id="agent.beta",
        )
        self.assertTrue(human["id"])
        self.assertTrue(agent["id"])

        human_list = self.memory.api.long_term.list(
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
        )
        agent_list = self.memory.api.long_term.list(
            owner_agent_id="agent.alpha",
            subject_type="agent",
            subject_id="agent.beta",
        )
        self.assertEqual(human_list["count"], 1)
        self.assertEqual(agent_list["count"], 1)
        self.assertEqual(human_list["results"][0]["id"], human["id"])
        self.assertEqual(agent_list["results"][0]["id"], agent["id"])
        long_term_meta = self.memory.db.fetch_one("SELECT content_id FROM long_term_memories WHERE id = ?", (human["id"],))
        self.assertIsNotNone(long_term_meta)
        self.assertRegex(long_term_meta["content_id"], r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
        self.assertEqual(
            self.memory.memory_content_store.get_text("long_term", long_term_meta["content_id"]),
            "用户偏好简洁分点回答，并且希望所有输出都尽量先给结论。",
        )
        memory_index_row = self.memory.db.fetch_one("SELECT text FROM memory_index WHERE record_id = ?", (human["id"],))
        self.assertIsNotNone(memory_index_row)
        self.assertIn("用户偏好简洁分点回答", memory_index_row["text"])
        self.assertIsNone(
            self.memory.db.fetch_one("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memories'")
        )

        updated = self.memory.api.long_term.update(human["id"], text="用户偏好先给结论，再给分点说明。")
        self.assertEqual(updated["id"], human["id"])
        self.assertTrue(
            self.memory.api.long_term.search(
                "先给结论",
                owner_agent_id="agent.alpha",
                subject_type="human",
                subject_id="user-1",
            )["results"]
        )

        session = self.memory.api.session.create(
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
            title="demo",
        )
        short_term = self.memory.api.short_term.add(
            "这轮会话需要完成架构评审，并且要保留插件化与轻量化约束。",
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
            session_id=session["id"],
        )
        self.assertTrue(short_term["id"])
        short_term_meta = self.memory.db.fetch_one("SELECT content_id FROM short_term_memories WHERE id = ?", (short_term["id"],))
        self.assertIsNotNone(short_term_meta)
        self.assertRegex(short_term_meta["content_id"], r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
        self.assertEqual(
            self.memory.memory_content_store.get_text("short_term", short_term_meta["content_id"]),
            "这轮会话需要完成架构评审，并且要保留插件化与轻量化约束。",
        )
        compressed = self.memory.api.short_term.compress(
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
            session_id=session["id"],
        )
        self.assertTrue(compressed["triggered"])
        self.assertTrue(compressed["snapshot"]["id"])

        deleted = self.memory.api.long_term.delete(agent["id"])
        self.assertEqual(deleted["status"], "deleted")

    def test_global_knowledge_archive_skill_and_mcp(self) -> None:
        document = self.memory.api.knowledge.add(
            title="平台接入规范",
            text="AIMemory 面向多主体、多智能体协同平台，提供本地优先记忆存储。",
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
        )
        global_document = self.memory.api.knowledge.add(
            title="全局知识",
            text="所有 agent 都可以访问全局知识库中的这条规则。",
            global_scope=True,
        )
        self.assertTrue(document["id"])
        self.assertTrue(global_document["id"])

        listed_docs = self.memory.api.knowledge.list(
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
        )
        self.assertGreaterEqual(len(listed_docs["results"]), 2)
        self.assertTrue(
            self.memory.api.knowledge.search(
                "全局知识",
                owner_agent_id="agent.alpha",
                subject_type="human",
                subject_id="user-1",
            )["results"]
        )

        skill = self.memory.api.skill.add(
            name="context_compactor",
            description="压缩长上下文并保留关键步骤。",
            owner_agent_id="agent.alpha",
            subject_type="agent",
            subject_id="agent.beta",
            tools=["search"],
            topics=["compression"],
        )
        skill_metadata = self.memory.api.skill.list(owner_agent_id="agent.alpha")
        self.assertEqual(skill_metadata["results"][0]["id"], skill["id"])

        updated_skill = self.memory.api.skill.update(
            skill["id"],
            description="压缩长上下文、提取关键步骤并降低 token 成本。",
            tools=["search", "summarize"],
        )
        self.assertEqual(updated_skill["id"], skill["id"])
        self.assertGreaterEqual(len(updated_skill["versions"]), 2)

        archive = self.memory.api.archive.add(
            summary="归档：平台需要本地优先、多层记忆、插件化数据库能力。",
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
        )
        self.assertTrue(archive["id"])
        archive_meta = self.memory.db.fetch_one("SELECT content_id FROM archive_memories WHERE id = ?", (archive["id"],))
        self.assertIsNotNone(archive_meta)
        self.assertRegex(archive_meta["content_id"], r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
        archive_payload = self.memory.memory_content_store.get_json("archive", archive_meta["content_id"], {})
        self.assertEqual(archive_payload["summary"], "归档：平台需要本地优先、多层记忆、插件化数据库能力。")
        self.assertIsNone(
            self.memory.db.fetch_one("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'archive_units'")
        )
        self.assertTrue(
            self.memory.api.archive.search(
                "插件化数据库",
                owner_agent_id="agent.alpha",
                subject_type="human",
                subject_id="user-1",
            )["results"]
        )
        self.assertTrue(
            self.memory.api.archive.compress(
                owner_agent_id="agent.alpha",
                subject_type="human",
                subject_id="user-1",
            )["triggered"]
        )

        adapter = self.memory.create_mcp_adapter(
            scope={"owner_agent_id": "agent.alpha", "subject_type": "human", "subject_id": "user-1"}
        )
        manifest = adapter.call_tool("aimemory_manifest", {})
        self.assertEqual(manifest["storage"]["relational_backend"], "sqlite")
        self.assertEqual(manifest["storage"]["index_backend"], "lancedb")
        self.assertEqual(manifest["storage"]["graph_backend"], "disabled")
        mcp_list = adapter.call_tool("long_term_memory_list", {"limit": 10})
        self.assertTrue(isinstance(mcp_list["results"], list))

        deleted = self.memory.api.skill.delete(skill["id"])
        self.assertTrue(deleted["deleted"])

    def test_fts_retrieval_recovers_older_interaction_and_execution_records(self) -> None:
        session = self.memory.api.session.create(
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
            title="fts-demo",
        )
        interaction_phrase = "稀有交互短语：全链路配额折叠策略"
        self.memory.api.session.append(
            session["id"],
            "user",
            interaction_phrase,
            auto_capture=False,
            auto_compress=False,
        )
        for index in range(14):
            self.memory.api.session.append(
                session["id"],
                "user",
                f"普通交互上下文 {index}",
                auto_capture=False,
                auto_compress=False,
            )

        interaction_result = self.memory.api.recall.query(
            interaction_phrase,
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
            session_id=session["id"],
            domains=["interaction"],
            limit=3,
        )
        self.assertTrue(any(interaction_phrase in item.get("text", "") for item in interaction_result["results"]))

        execution_phrase = "稀有执行目标：回滚编排口令"
        self.memory.api.execution.start_run(
            user_id="user-1",
            goal=execution_phrase,
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
        )
        for index in range(84):
            self.memory.api.execution.start_run(
                user_id="user-1",
                goal=f"普通执行目标 {index}",
                owner_agent_id="agent.alpha",
                subject_type="human",
                subject_id="user-1",
            )

        execution_result = self.memory.api.execution.search(
            execution_phrase,
            user_id="user-1",
            owner_agent_id="agent.alpha",
            session_id=None,
            limit=3,
        )
        self.assertTrue(any(execution_phrase in item.get("text", "") for item in execution_result["results"]))
        self.assertGreaterEqual(
            self.memory.db.fetch_one(
                "SELECT COUNT(*) AS count FROM text_search_index WHERE collection = 'interaction_turn'"
            )["count"],
            15,
        )
        self.assertGreaterEqual(
            self.memory.db.fetch_one(
                "SELECT COUNT(*) AS count FROM text_search_index WHERE collection = 'execution_run'"
            )["count"],
            85,
        )


if __name__ == "__main__":
    unittest.main()
