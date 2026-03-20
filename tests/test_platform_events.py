from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from aimemory import AIMemory


class PlatformEventsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.memory = AIMemory(
            {
                "root_dir": self.tempdir.name,
                "memory_policy": {
                    "compression_turn_threshold": 2,
                    "compression_preserve_recent_turns": 0,
                    "compression_budget_chars": 220,
                    "snapshot_keep_recent": 1,
                },
            }
        )

    def tearDown(self) -> None:
        self.memory.close()
        self.tempdir.cleanup()

    def _scope(self) -> dict[str, str]:
        return {
            "owner_agent_id": "agent.planner",
            "subject_type": "human",
            "subject_id": "user-1",
        }

    def test_default_platform_events_orchestrate_recall_reflect_and_handoff(self) -> None:
        session = self.memory.api.session.create(user_id="user-1", title="platform-events", **self._scope())
        run = self.memory.api.execution.start_run(user_id="user-1", goal="整理交接上下文并准备执行代理。", session_id=session["id"], **self._scope())
        first = self.memory.api.session.append(
            session["id"],
            "user",
            "请整理回滚步骤，并准备交接。",
            run_id=run["id"],
            auto_compress=False,
        )
        second = self.memory.api.session.append(
            session["id"],
            "assistant",
            "需要保留最小上下文、回滚步骤和未完成事项。",
            run_id=run["id"],
            auto_compress=False,
        )
        self.memory.api.long_term.add("回滚时优先恢复数据库快照。", **self._scope())

        turn_event = self.memory.events.on_turn_end(
            session_id=session["id"],
            turn_id=second["id"],
            run_id=run["id"],
            auto_context=True,
            use_platform_llm=False,
        )
        self.assertTrue(turn_event["handled"])
        self.assertTrue(turn_event["compression"]["compressed"])
        self.assertEqual(turn_event["recall_plan"]["query"], "需要保留最小上下文、回滚步骤和未完成事项。")
        self.assertEqual(turn_event["context"]["artifact"]["artifact_type"], "prompt_context")

        agent_event = self.memory.events.on_agent_end(
            session_id=session["id"],
            run_id=run["id"],
            use_platform_llm=False,
        )
        self.assertTrue(agent_event["handled"])
        self.assertEqual(agent_event["reflection"]["artifact"]["artifact_type"], "reflection_pack")
        self.assertEqual(agent_event["context"]["artifact"]["artifact_type"], "prompt_context")

        handoff_event = self.memory.events.on_handoff(
            source_agent_id="agent.planner",
            target_agent_id="agent.executor",
            source_session_id=session["id"],
            run_id=run["id"],
            include_context=True,
            use_platform_llm=False,
        )
        self.assertTrue(handoff_event["handled"])
        self.assertEqual(handoff_event["handoff"]["artifact"]["artifact_type"], "handoff_pack")
        self.assertEqual(handoff_event["handoff"]["target_agent_id"], "agent.executor")
        self.assertEqual(handoff_event["context"]["artifact"]["target_agent_id"], "agent.executor")

        close_event = self.memory.events.on_session_close(
            session["id"],
            run_id=run["id"],
            use_platform_llm=False,
        )
        self.assertTrue(close_event["handled"])
        self.assertEqual(close_event["status"], "closed")
        self.assertEqual(close_event["reflection"]["artifact"]["artifact_type"], "reflection_pack")
        self.assertEqual(self.memory.get_session(session["id"])["status"], "closed")
        self.assertLessEqual(int(close_event["prune"]["kept"]), 1)
        self.assertEqual(first["session_id"], session["id"])

    def test_mcp_tools_expose_versioning_and_platform_event_hooks(self) -> None:
        adapter = self.memory.create_mcp_adapter(scope=self._scope())
        tool_names = {tool["name"] for tool in adapter.manifest()["tools"]}
        self.assertIn("long_term_memory_supersede", tool_names)
        self.assertIn("long_term_memory_history", tool_names)
        self.assertIn("long_term_memory_link", tool_names)
        self.assertIn("platform_event_turn_end", tool_names)
        self.assertIn("platform_event_agent_end", tool_names)
        self.assertIn("platform_event_handoff", tool_names)
        self.assertIn("platform_event_session_close", tool_names)

        base = adapter.call_tool("long_term_memory_add", {"text": "发布窗口是周二 10:00。"})
        related = adapter.call_tool("long_term_memory_add", {"text": "回滚负责人是值班 SRE。"})
        superseded = adapter.call_tool(
            "long_term_memory_supersede",
            {
                "memory_id": base["id"],
                "text": "发布窗口改为周三 14:00。",
                "reason_code": "mcp_schedule_change",
            },
        )
        link = adapter.call_tool(
            "long_term_memory_link",
            {
                "memory_id": superseded["id"],
                "target_memory_ids": [related["id"]],
                "link_type": "depends_on",
                "confidence": 0.88,
            },
        )
        history = adapter.call_tool("long_term_memory_history", {"memory_id": superseded["id"]})

        self.assertEqual(superseded["supersedes_memory_id"], base["id"])
        self.assertEqual(link["target_memory_ids"], [related["id"]])
        self.assertTrue(any(item["reason_code"] == "mcp_schedule_change" for item in history))

        session = adapter.call_tool("session_create", {"user_id": "user-1", "title": "mcp-events"})
        run = self.memory.api.execution.start_run(user_id="user-1", goal="交接执行代理。", session_id=session["id"], **self._scope())
        turn = adapter.call_tool(
            "session_append_turn",
            {
                "session_id": session["id"],
                "role": "user",
                "content": "请生成交接上下文。",
            },
        )
        adapter.call_tool(
            "session_append_turn",
            {
                "session_id": session["id"],
                "role": "assistant",
                "content": "需要同时保留回滚信息。",
            },
        )

        turn_event = adapter.call_tool(
            "platform_event_turn_end",
            {
                "session_id": session["id"],
                "turn_id": turn["id"],
                "run_id": run["id"],
                "auto_context": True,
                "use_platform_llm": False,
            },
        )
        handoff_event = adapter.call_tool(
            "platform_event_handoff",
            {
                "source_session_id": session["id"],
                "run_id": run["id"],
                "source_agent_id": "agent.planner",
                "target_agent_id": "agent.executor",
                "use_platform_llm": False,
            },
        )
        close_event = adapter.call_tool(
            "platform_event_session_close",
            {
                "session_id": session["id"],
                "run_id": run["id"],
                "use_platform_llm": False,
            },
        )

        self.assertTrue(turn_event["handled"])
        self.assertEqual(turn_event["context"]["artifact"]["artifact_type"], "prompt_context")
        self.assertEqual(handoff_event["handoff"]["artifact"]["artifact_type"], "handoff_pack")
        self.assertEqual(close_event["status"], "closed")


if __name__ == "__main__":
    unittest.main()
