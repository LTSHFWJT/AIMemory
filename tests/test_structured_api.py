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
        latest = loaded["current_snapshot"]
        file_paths = {item["relative_path"] for item in latest["files"]}
        self.assertIn("SKILL.md", file_paths)
        self.assertIn("references/style-guide.md", file_paths)
        self.assertIn("scripts/render.py", file_paths)
        self.assertIn("assets/template.txt", file_paths)
        self.assertTrue(latest["skill_markdown"].startswith("---"))
        self.assertTrue(loaded["execution_context"]["summary"])
        self.assertIn("Execution Context", loaded["execution_context_text"])
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

        latest = updated["current_snapshot"]
        file_paths = {item["relative_path"] for item in latest["files"]}
        self.assertIn("references/base.md", file_paths)
        self.assertIn("references/risk.md", file_paths)
        self.assertIn("scripts/check.py", file_paths)
        self.assertIsNotNone(updated["current_snapshot"])
        self.assertTrue(updated["execution_context"]["summary"])

        search = self.memory.api.skill.search(
            "回滚步骤 风险提示",
            owner_agent_id="agent.alpha",
            subject_type="agent",
            subject_id="agent.alpha",
        )
        self.assertTrue(search["results"])
        self.assertEqual(search["results"][0]["skill_id"], skill["id"])

    def test_structured_chunking_persists_section_context(self) -> None:
        document = self.memory.api.knowledge.add(
            "发布操作手册",
            """
            # 准备
            1. 检查配置文件和数据库连接。
            2. 记录当前版本号并确认备份可用。

            # 回滚
            1. 恢复数据库快照。
            2. 重新启动服务并验证健康检查。
            """,
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
            chunk_size=90,
            chunk_overlap=20,
        )
        self.assertTrue(document["chunks"])
        document_sections = [chunk["metadata"].get("section_titles") or [] for chunk in document["chunks"]]
        self.assertTrue(any("准备" in sections for sections in document_sections))
        self.assertTrue(any("回滚" in sections for sections in document_sections))

        indexed_titles = [
            row["title"]
            for row in self.memory.db.fetch_all(
                "SELECT title FROM knowledge_chunk_index WHERE document_id = ? ORDER BY updated_at ASC",
                (document["id"],),
            )
        ]
        self.assertTrue(any("准备" in title for title in indexed_titles))
        self.assertTrue(any("回滚" in title for title in indexed_titles))

        skill = self.memory.api.skill.add(
            "release_sections",
            "带章节的发布参考资料。",
            owner_agent_id="agent.alpha",
            subject_type="agent",
            subject_id="agent.alpha",
            references={
                "references/release.md": """
                # 准备
                发布前先跑 health-check 并核对版本号。

                # 回滚
                失败后恢复快照，并重新校验接口状态。
                """,
            },
        )
        skill_reference_search = self.memory.api.skill.search_references(
            "回滚 快照 接口状态",
            owner_agent_id="agent.alpha",
            subject_type="agent",
            subject_id="agent.alpha",
            skill_id=skill["id"],
        )
        self.assertTrue(skill_reference_search["results"])
        self.assertIn("回滚", skill_reference_search["results"][0]["title"])

    def test_algorithmic_long_text_compression_endpoints(self) -> None:
        compressed = self.memory.api.recall.compress_text(
            """
            # 发布流程

            1. 先执行预检查脚本，确认配置文件完整。
            2. 再执行发布命令，并记录版本号 v2.4.1。
            3. 如果失败，必须按照回滚步骤恢复数据库。

            约束：
            - CPU 使用率不得超过 70%
            - 发布窗口限制在 30 分钟内
            """,
            domain_hint="skill_reference",
            query="发布 回滚 版本 约束",
            budget_chars=180,
        )
        self.assertTrue(compressed["summary"])
        self.assertTrue(compressed["highlights"])
        self.assertTrue(compressed["steps"])
        self.assertTrue(compressed["constraints"])
        self.assertTrue(compressed["risks"])
        self.assertTrue(compressed["selected_unit_ids"])

        document = self.memory.api.knowledge.add(
            "发布规范",
            """
            发布前必须完成预检查，并输出版本号 v3.2.0。
            数据迁移期间 CPU 使用率不得超过 65%。
            如失败，必须执行标准回滚流程。
            """,
            owner_agent_id="agent.alpha",
            subject_type="human",
            subject_id="user-1",
        )
        document_compression = self.memory.api.knowledge.compress(
            document["id"],
            query="版本号 回滚 CPU",
            budget_chars=180,
        )
        self.assertEqual(document_compression["document_id"], document["id"])
        self.assertTrue(document_compression["summary"])
        self.assertTrue(document_compression["constraints"])

        skill = self.memory.api.skill.add(
            "release_guard",
            "执行发布前检查并在失败时回滚。",
            owner_agent_id="agent.alpha",
            subject_type="agent",
            subject_id="agent.alpha",
            references={
                "references/release.md": """
                发布步骤：
                1. 执行 health-check
                2. 记录版本号 v5.0.0
                3. 如果失败，立即回滚

                限制：
                - 发布窗口 20 分钟
                - 错误率不得超过 1%
                """,
            },
        )
        skill_compression = self.memory.api.skill.compress_references(
            skill["id"],
            query="回滚 版本号 错误率",
            budget_chars=200,
        )
        self.assertEqual(skill_compression["skill_id"], skill["id"])
        self.assertTrue(skill_compression["summary"])
        self.assertTrue(skill_compression["steps"])
        self.assertTrue(skill_compression["constraints"])
        refreshed = self.memory.api.skill.refresh_execution_context(skill["id"])
        self.assertTrue(refreshed["persisted"])
        loaded_skill = self.memory.api.skill.get(skill["id"])
        self.assertTrue(loaded_skill["execution_context"]["summary"])

    def test_long_text_compression_keeps_sequence_and_section_context(self) -> None:
        compressed = self.memory.api.recall.compress_text(
            """
            # 背景
            系统需要在今晚完成发布，涉及数据库迁移、接口验证和监控检查。

            # 步骤
            1. 先执行 precheck，确认配置、凭证、磁盘空间和 migration plan 正确。
            2. 再执行 deploy --batch=bluegreen，并记录版本号 v4.8.2。
            3. 发布完成后执行 smoke test，并观察 5 分钟错误率。

            # 约束
            - CPU 使用率不得超过 70%
            - 错误率不得超过 1%
            - 发布时间窗口限制在 30 分钟内

            # 风险与回滚
            如果 smoke test 失败，必须立即回滚数据库和应用快照。
            回滚后需要再次验证订单接口、支付接口和登录链路。
            注意：不要在高峰流量期间执行回滚。
            """,
            query="发布 回滚 错误率 版本 约束",
            domain_hint="skill_reference",
            budget_chars=240,
        )
        joined = "\n".join(compressed["highlights"])
        self.assertIn("precheck", joined)
        self.assertTrue(any(item.startswith("[步骤]") or item.startswith("[约束]") or item.startswith("[风险与回滚]") for item in compressed["highlights"]))
        self.assertTrue(any("回滚" in item for item in compressed["risks"]))
        self.assertTrue(compressed["steps"][0].startswith("先执行 precheck"))

    def test_multiline_list_item_is_kept_as_single_step_and_constraints_are_detected(self) -> None:
        compressed = self.memory.api.recall.compress_text(
            """
            # Steps
            1. Prepare release manifest
               include rollback ids and migration checksum
            2. Deploy app
            3. Verify checkout flow

            # Constraints
            - CPU <= 70%
            - error rate <= 1%
            """,
            query="deploy rollback constraints",
            domain_hint="skill_reference",
            budget_chars=160,
        )
        self.assertTrue(any("include rollback ids and migration checksum" in item for item in compressed["steps"]))
        self.assertTrue(any("CPU <= 70%" in item for item in compressed["constraints"]))
        self.assertFalse(any(item == "[Steps] include rollback ids and migration checksum" for item in compressed["highlights"]))

    def test_same_skill_name_is_reusable_across_agents(self) -> None:
        first = self.memory.api.skill.add(
            "context_compactor",
            "agent alpha 的压缩技能。",
            owner_agent_id="agent.alpha",
            references={"references/alpha.md": "alpha agent 偏好保留步骤和约束。"},
        )
        second = self.memory.api.skill.add(
            "context_compactor",
            "agent beta 的压缩技能。",
            owner_agent_id="agent.beta",
            references={"references/beta.md": "beta agent 偏好保留风险和回退。"},
        )
        self.assertNotEqual(first["id"], second["id"])
        alpha_results = self.memory.api.skill.list(owner_agent_id="agent.alpha")["results"]
        beta_results = self.memory.api.skill.list(owner_agent_id="agent.beta")["results"]
        self.assertEqual(alpha_results[0]["id"], first["id"])
        self.assertEqual(beta_results[0]["id"], second["id"])


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
