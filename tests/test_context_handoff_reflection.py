from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from aimemory import AIMemory


class _FakePlatformLLM:
    provider = "platform-mock"
    model = "mock-compressor"

    def compress(self, *, task_type, records, budget_chars, scope, metadata=None):
        return {
            "summary": f"{task_type} 平台压缩摘要",
            "highlights": ["关键上下文", "保持轻量"],
            "steps": ["继续执行当前计划"],
            "constraints": ["不要扩大修改范围"],
            "facts": ["当前任务需要交付可调用 API"],
            "provider": self.provider,
            "model": self.model,
            "metadata": {"scope": scope, **dict(metadata or {})},
        }


class ContextHandoffReflectionTest(unittest.TestCase):
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
                    "compression_turn_threshold": 3,
                    "compression_preserve_recent_turns": 0,
                    "compression_budget_chars": 220,
                },
            }
        )

    def tearDown(self) -> None:
        self.memory.close()
        self.tempdir.cleanup()

    def _seed_session(self) -> tuple[dict, dict]:
        session = self.memory.api.session.create(
            user_id="user-1",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
            title="release-plan",
        )
        run = self.memory.api.execution.start_run(
            user_id="user-1",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
            session_id=session["id"],
            goal="安排部署窗口、确认回滚，并准备交接给执行代理。",
        )
        self.memory.api.session.append(
            session["id"],
            "user",
            "本轮先确定部署窗口，再准备交接给执行代理。",
            auto_compress=False,
        )
        self.memory.api.session.append(
            session["id"],
            "assistant",
            "需要明确回滚步骤，并保留最小上下文给下游代理。",
            auto_compress=False,
        )
        self.memory.api.session.append(
            session["id"],
            "user",
            "约束是保持轻量，不引入新的重型依赖。",
            auto_compress=False,
        )
        self.memory.api.long_term.add(
            "用户偏好先给结论，再给执行步骤。",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
        )
        self.memory.api.knowledge.add(
            "发布回滚规范",
            "失败时先恢复数据库快照，再重启服务并验证健康检查。",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
        )
        return session, run

    def test_context_handoff_and_reflection_are_persisted(self) -> None:
        session, run = self._seed_session()
        snapshot = self.memory.api.session.compress(session["id"], budget_chars=180)
        self.assertTrue(snapshot["compressed"])

        context = self.memory.api.context.build(
            "部署窗口 回滚 交接",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
            session_id=session["id"],
            run_id=run["id"],
            include_domains=["memory", "interaction", "knowledge"],
            use_platform_llm=False,
            budget_chars=220,
        )
        self.assertEqual(context["job"]["status"], "completed")
        self.assertEqual(context["artifact"]["artifact_type"], "prompt_context")
        self.assertTrue(context["artifact"]["source_refs"])
        self.assertIn("Context Brief", context["artifact"]["content"])

        handoff = self.memory.api.handoff.build(
            "agent.executor",
            source_run_id=run["id"],
            source_session_id=session["id"],
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
            use_platform_llm=False,
            budget_chars=240,
        )
        self.assertEqual(handoff["target_agent_id"], "agent.executor")
        self.assertEqual(handoff["artifact"]["artifact_type"], "handoff_pack")
        self.assertTrue(isinstance(handoff["open_tasks"], list))
        self.assertEqual(self.memory.api.handoff.get(handoff["id"])["id"], handoff["id"])

        reflection = self.memory.api.reflection.session(
            session["id"],
            run_id=run["id"],
            mode="derived+invariant",
            use_platform_llm=False,
            budget_chars=220,
        )
        self.assertEqual(reflection["artifact"]["artifact_type"], "reflection_pack")
        self.assertEqual({item["reflection_type"] for item in reflection["reflections"]}, {"derived", "invariant"})
        self.assertEqual(self.memory.api.context.get(context["artifact"]["id"])["id"], context["artifact"]["id"])
        self.assertTrue(self.memory.api.handoff.list(target_agent_id="agent.executor")["results"])
        self.assertTrue(self.memory.api.reflection.list(session_id=session["id"])["results"])

    def test_platform_llm_can_drive_context_compression(self) -> None:
        self.memory.close()
        self.memory = AIMemory(
            {
                "root_dir": self.tempdir.name,
                "memory_policy": {
                    "compression_budget_chars": 220,
                    "compression_turn_threshold": 3,
                },
            },
            platform_llm=_FakePlatformLLM(),
        )
        self.memory.api.long_term.add(
            "平台压缩需要返回结构化摘要。",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
        )

        context = self.memory.api.context.build(
            "结构化摘要",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
            include_domains=["memory"],
            use_platform_llm=True,
            budget_chars=220,
        )

        self.assertEqual(context["job"]["status"], "completed")
        self.assertEqual(context["artifact"]["provider"], "platform-mock")
        self.assertEqual(context["artifact"]["model"], "mock-compressor")
        self.assertEqual(context["compression"]["summary"], "context_build 平台压缩摘要")

    def test_recall_plan_and_query_can_target_contextual_domains(self) -> None:
        session, run = self._seed_session()
        self.memory.api.session.compress(session["id"], budget_chars=180)
        self.memory.api.handoff.build(
            "agent.executor",
            source_run_id=run["id"],
            source_session_id=session["id"],
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
            use_platform_llm=False,
            budget_chars=240,
        )
        self.memory.api.reflection.session(
            session["id"],
            run_id=run["id"],
            mode="derived+invariant",
            use_platform_llm=False,
            budget_chars=220,
        )
        self.memory.api.context.build(
            "交接上下文与回滚摘要",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
            session_id=session["id"],
            run_id=run["id"],
            use_platform_llm=False,
            budget_chars=220,
        )

        plan = self.memory.api.recall.plan(
            "给执行代理的交接上下文和反思摘要",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
            session_id=session["id"],
            run_id=run["id"],
        )
        self.assertIn("handoff", plan["selected_domains"])
        self.assertIn("context", plan["selected_domains"])
        self.assertIn("reflection", plan["selected_domains"])

        context_search = self.memory.api.context.search(
            "回滚 摘要",
            owner_agent_id="agent.planner",
            session_id=session["id"],
            run_id=run["id"],
        )
        handoff_search = self.memory.api.handoff.search(
            "执行代理 交接 回滚",
            owner_agent_id="agent.planner",
            source_session_id=session["id"],
            source_run_id=run["id"],
        )
        reflection_search = self.memory.api.reflection.search(
            "轻量 经验 回滚",
            owner_agent_id="agent.planner",
            session_id=session["id"],
            run_id=run["id"],
        )
        unified = self.memory.api.recall.query(
            "执行代理 交接 回滚 反思",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
            session_id=session["id"],
            run_id=run["id"],
            domains=["handoff", "context", "reflection"],
            limit=8,
        )

        self.assertTrue(context_search["results"])
        self.assertTrue(handoff_search["results"])
        self.assertTrue(reflection_search["results"])
        self.assertTrue(unified["results"])
        self.assertIn(unified["results"][0]["domain"], {"handoff", "context", "reflection"})
        self.assertEqual(unified["plan"]["query"], "执行代理 交接 回滚 反思")

    def test_mcp_tools_expose_context_handoff_and_reflection(self) -> None:
        adapter = self.memory.create_mcp_adapter(
            scope={"owner_agent_id": "agent.planner", "subject_type": "human", "subject_id": "user-1"}
        )
        session = adapter.call_tool("session_create", {"user_id": "user-1", "title": "mcp-phase1"})
        adapter.call_tool(
            "session_append_turn",
            {
                "session_id": session["id"],
                "role": "user",
                "content": "请整理一版最小交接上下文，并保留回滚信息。",
            },
        )
        self.memory.api.long_term.add(
            "回滚时优先恢复快照，再检查健康状态。",
            owner_agent_id="agent.planner",
            subject_type="human",
            subject_id="user-1",
        )

        manifest_tools = {tool["name"] for tool in adapter.manifest()["tools"]}
        self.assertIn("recall_plan", manifest_tools)
        self.assertIn("context_build", manifest_tools)
        self.assertIn("handoff_build", manifest_tools)
        self.assertIn("reflection_session", manifest_tools)
        self.assertIn("context_search", manifest_tools)
        self.assertIn("handoff_search", manifest_tools)
        self.assertIn("reflection_search", manifest_tools)

        plan = adapter.call_tool(
            "recall_plan",
            {
                "query": "交接上下文",
                "session_id": session["id"],
            },
        )
        context = adapter.call_tool(
            "context_build",
            {
                "query": "回滚 交接",
                "session_id": session["id"],
                "include_domains": ["memory", "interaction"],
                "use_platform_llm": False,
            },
        )
        handoff = adapter.call_tool(
            "handoff_build",
            {
                "target_agent_id": "agent.executor",
                "source_session_id": session["id"],
                "use_platform_llm": False,
            },
        )
        reflection = adapter.call_tool(
            "reflection_session",
            {
                "session_id": session["id"],
                "mode": "derived+invariant",
                "use_platform_llm": False,
            },
        )
        context_hits = adapter.call_tool(
            "context_search",
            {
                "query": "回滚 交接",
                "session_id": session["id"],
            },
        )
        handoff_hits = adapter.call_tool(
            "handoff_search",
            {
                "query": "执行代理 交接",
                "source_session_id": session["id"],
            },
        )
        reflection_hits = adapter.call_tool(
            "reflection_search",
            {
                "query": "回滚 经验",
                "session_id": session["id"],
            },
        )

        self.assertIn("context", plan["selected_domains"])
        self.assertEqual(context["artifact"]["artifact_type"], "prompt_context")
        self.assertEqual(handoff["artifact"]["artifact_type"], "handoff_pack")
        self.assertTrue(reflection["reflections"])
        self.assertTrue(context_hits["results"])
        self.assertTrue(handoff_hits["results"])
        self.assertTrue(reflection_hits["results"])


if __name__ == "__main__":
    unittest.main()
