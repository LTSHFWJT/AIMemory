from __future__ import annotations

import asyncio
import unittest
from tempfile import TemporaryDirectory

from aimemory import AIMemory, AsyncAIMemory


class StructuredAPITest(unittest.TestCase):
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

    def test_grouped_api_matches_memory_domains(self) -> None:
        long_term = self.memory.api.long_term.add(
            "用户偏好先给结论，再给执行步骤。",
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
        )
        document = self.memory.api.knowledge.add(
            "接口治理原则",
            "在保留功能的前提下，优先收敛对外 API。",
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
        )
        skill = self.memory.api.skill.add(
            "api_compactor",
            "收敛接口并统一调用方式。",
            owner_agent_id="agent.alpha",
            subject_type="agent",
            subject_id="agent.alpha",
            topics=["api", "compatibility"],
        )
        archive = self.memory.api.archive.add(
            "归档：长期保留 API 收敛设计原则。",
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
        )

        self.assertEqual(
            long_term["id"],
            self.memory.api.long_term.list(
                owner_agent_id="agent.alpha",
                subject_type="human",
                subject_id="user-1",
            )["results"][0]["id"],
        )
        self.assertEqual(document["id"], self.memory.api.knowledge.get(document["id"])["id"])
        self.assertEqual(skill["id"], self.memory.api.skill.list(owner_agent_id="agent.alpha")["results"][0]["id"])
        self.assertEqual(archive["id"], self.memory.api.archive.get(archive["id"])["id"])

        recall = self.memory.api.recall.query(
            "接口收敛",
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
            domains=["memory", "knowledge", "archive"],
            limit=8,
        )
        self.assertTrue(recall["results"])
        self.assertIn("api", dir(self.memory))
        self.assertNotIn("store_long_term_memory", dir(self.memory))

    def test_scoped_grouped_api_keeps_scope(self) -> None:
        scoped = self.memory.scoped(
            workspace_id="ws.alpha",
            team_id="team.alpha",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
            interaction_type="human_agent",
        )

        session = scoped.api.session.create(user_id="user-1", title="grouped-api")
        short_term = scoped.api.short_term.add("这轮任务聚焦接口归并与统一整理。", session_id=session["id"])
        search = scoped.api.short_term.search("接口归并", session_id=session["id"])

        self.assertTrue(session["namespace_key"].startswith("workspace=ws.alpha"))
        self.assertEqual(short_term["owner_agent_id"], "agent.planner")
        self.assertEqual(search["results"][0]["id"], short_term["id"])

    def test_skill_package_files_are_persisted_and_reference_text_is_searchable(self) -> None:
        skill = self.memory.api.skill.add(
            "doc_writer",
            "生成和维护技术文档。",
            owner_agent_id="agent.alpha",
            subject_type="agent",
            subject_id="agent.alpha",
            prompt_template="先整理大纲，再输出正文。",
            references={
                "references/style-guide.md": "标题遵循 RFC 风格，示例必须给出输入输出。",
            },
            scripts={
                "scripts/render.py": "print('render docs')\n",
            },
            assets={
                "assets/template.txt": "## Template\n\n- Summary\n",
            },
        )

        loaded = self.memory.api.skill.get(skill["id"])
        latest = loaded["versions"][0]
        file_paths = {item["relative_path"] for item in latest["files"]}
        self.assertIn("SKILL.md", file_paths)
        self.assertIn("references/style-guide.md", file_paths)
        self.assertIn("scripts/render.py", file_paths)
        self.assertIn("assets/template.txt", file_paths)
        self.assertTrue(latest["skill_markdown"].startswith("---"))
        self.assertEqual(
            next(item["content"] for item in latest["references"] if item["relative_path"] == "references/style-guide.md"),
            "标题遵循 RFC 风格，示例必须给出输入输出。",
        )

        search = self.memory.api.skill.search(
            "RFC 风格 示例 输入输出",
            owner_agent_id="agent.alpha",
            subject_type="agent",
            subject_id="agent.alpha",
        )
        self.assertTrue(search["results"])
        self.assertEqual(search["results"][0]["skill_id"], skill["id"])

        reference_search = self.memory.api.skill.search_references(
            "RFC 风格 示例 输入输出",
            owner_agent_id="agent.alpha",
            subject_type="agent",
            subject_id="agent.alpha",
            skill_id=skill["id"],
        )
        self.assertTrue(reference_search["results"])
        self.assertEqual(reference_search["results"][0]["skill_id"], skill["id"])
        self.assertEqual(reference_search["results"][0]["relative_path"], "references/style-guide.md")

        self.assertGreaterEqual(
            self.memory.db.fetch_one("SELECT COUNT(*) AS count FROM skill_files WHERE skill_id = ?", (skill["id"],))["count"],
            4,
        )
        self.assertGreaterEqual(
            self.memory.db.fetch_one(
                "SELECT COUNT(*) AS count FROM skill_reference_index WHERE skill_id = ?",
                (skill["id"],),
            )["count"],
            1,
        )

    def test_skill_update_preserves_existing_package_files(self) -> None:
        skill = self.memory.api.skill.add(
            "release_helper",
            "管理发布说明。",
            owner_agent_id="agent.alpha",
            subject_type="agent",
            subject_id="agent.alpha",
            references={"references/base.md": "保留 changelog 历史摘要。"},
            scripts={"scripts/check.py": "print('check')\n"},
        )

        updated = self.memory.api.skill.update(
            skill["id"],
            description="管理发布说明并补充风险提示。",
            references={"references/risk.md": "发布前必须补充回滚步骤。"},
        )

        latest = updated["versions"][0]
        file_paths = {item["relative_path"] for item in latest["files"]}
        self.assertIn("references/base.md", file_paths)
        self.assertIn("references/risk.md", file_paths)
        self.assertIn("scripts/check.py", file_paths)
        self.assertGreaterEqual(len(updated["versions"]), 2)

        search = self.memory.api.skill.search(
            "回滚步骤 风险提示",
            owner_agent_id="agent.alpha",
            subject_type="agent",
            subject_id="agent.alpha",
        )
        self.assertTrue(search["results"])
        self.assertEqual(search["results"][0]["skill_id"], skill["id"])


class AsyncStructuredAPITest(unittest.TestCase):
    def test_async_grouped_api(self) -> None:
        async def scenario() -> None:
            with TemporaryDirectory() as tempdir:
                memory = AsyncAIMemory({"root_dir": tempdir})
                long_term = await memory.api.long_term.add(
                    "异步入口也应使用同一组收敛后的域 API。",
                    owner_agent_id="agent.async",
                    subject_type="human",
                    subject_id="user-1",
                )
                listed = await memory.api.long_term.list(
                    owner_agent_id="agent.async",
                    subject_type="human",
                    subject_id="user-1",
                )
                self.assertEqual(long_term["id"], listed["results"][0]["id"])
                self.assertIn("api", dir(memory))
                await memory.close()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
