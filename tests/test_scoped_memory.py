from __future__ import annotations

import tempfile
import unittest

from aimemory import AIMemory


class ScopedMemoryTests(unittest.TestCase):
    def test_team_namespace_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with AIMemory({"root_dir": temp_dir}) as memory:
                scope_common = {
                    "team_id": "team.alpha",
                    "owner_agent_id": "agent.planner",
                    "subject_type": "agent",
                    "subject_id": "agent.executor",
                    "interaction_type": "agent_agent",
                }
                workspace_one = memory.scoped(workspace_id="ws.one", **scope_common)
                workspace_two = memory.scoped(workspace_id="ws.two", **scope_common)

                workspace_one.api.long_term.add("workspace one secret execution pattern")
                workspace_two.api.long_term.add("workspace two secret execution pattern")

                result_one = workspace_one.api.recall.query("secret execution pattern", domains=["memory"], limit=10)
                result_two = workspace_two.api.recall.query("secret execution pattern", domains=["memory"], limit=10)

                texts_one = [item.get("text", "") for item in result_one["results"]]
                texts_two = [item.get("text", "") for item in result_two["results"]]

                self.assertTrue(any("workspace one" in text for text in texts_one))
                self.assertFalse(any("workspace two" in text for text in texts_one))
                self.assertTrue(any("workspace two" in text for text in texts_two))
                self.assertFalse(any("workspace one" in text for text in texts_two))

    def test_scoped_layout_and_session_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with AIMemory({"root_dir": temp_dir, "workspace_id": "ws.alpha", "team_id": "team.alpha"}) as memory:
                scoped = memory.scoped(
                    owner_agent_id="agent.planner",
                    subject_type="human",
                    subject_id="user-1",
                    interaction_type="human_agent",
                    project_id="project-x",
                )
                session = scoped.api.session.create(user_id="user-1", title="demo")
                turn = scoped.api.session.append(session["id"], "user", "我喜欢用简洁 bullet 输出。")
                layout = scoped.storage_layout()

                self.assertIsNotNone(session.get("namespace_key"))
                self.assertEqual(turn["session_id"], session["id"])
                self.assertIn("long_term_memory", layout["domains"])
                self.assertIn("knowledge", layout["domains"])
                self.assertIn("archive", layout["domains"])
                self.assertIn("interaction/", layout["domains"]["short_term_memory"]["object_prefix"])

    def test_mcp_adapter_default_scope_and_context_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with AIMemory({"root_dir": temp_dir}) as memory:
                adapter = memory.create_mcp_adapter(
                    scope={
                        "workspace_id": "ws.alpha",
                        "team_id": "team.alpha",
                        "owner_agent_id": "agent.planner",
                    }
                )

                session = adapter.call_tool(
                    "session_create",
                    {
                        "user_id": "user-1",
                        "title": "mcp-demo",
                        "context_scope": {
                            "subject_type": "human",
                            "subject_id": "user-1",
                            "interaction_type": "human_agent",
                        },
                    },
                )
                adapter.call_tool(
                    "long_term_memory_add",
                    {
                        "text": "user-1 prefers concise markdown bullets",
                        "session_id": session["id"],
                        "context_scope": {
                            "user_id": "user-1",
                            "subject_type": "human",
                            "subject_id": "user-1",
                            "interaction_type": "human_agent",
                        },
                    },
                )

                result = adapter.call_tool(
                    "recall_query",
                    {
                        "query": "concise markdown bullets",
                        "domains": ["memory"],
                        "context_scope": {
                            "user_id": "user-1",
                            "subject_type": "human",
                            "subject_id": "user-1",
                            "interaction_type": "human_agent",
                        },
                    },
                )

                manifest = adapter.manifest()
                self.assertEqual(manifest["default_scope"]["workspace_id"], "ws.alpha")
                self.assertTrue(any("concise markdown bullets" in item.get("text", "") for item in result["results"]))


if __name__ == "__main__":
    unittest.main()
