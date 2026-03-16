from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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
                self.assertEqual(layout["sqlite_path"], str(Path(temp_dir).resolve() / "aimemory.db"))
                self.assertEqual(layout["memory_dir"], str(Path(temp_dir).resolve() / "memory"))
                self.assertEqual(layout["competency_dir"], str(Path(temp_dir).resolve() / "competency"))

    def test_storage_paths_are_partitioned_by_memory_and_competency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            with AIMemory({"root_dir": temp_dir}) as memory:
                memory.api.long_term.add(
                    "长期记忆落在 memory 分区。",
                    owner_agent_id="agent.alpha",
                    subject_type="human",
                    subject_id="user-1",
                )
                memory.api.skill.add(
                    "layout_checker",
                    "验证能力文件和引用索引落在 competency 分区。",
                    owner_agent_id="agent.alpha",
                    subject_type="agent",
                    subject_id="agent.alpha",
                    references={"references/layout.md": "competency 分区用于 skill 和 knowledge 文件。"},
                )

                self.assertEqual(memory.config.sqlite_path, root / "aimemory.db")
                self.assertEqual(memory.config.memory_path, root / "memory")
                self.assertEqual(memory.config.competency_path, root / "competency")
                self.assertEqual(memory.config.lmdb_path, root / "memory" / "lmdb")
                self.assertEqual(memory.config.object_store_path, root / "competency" / "objects")
                self.assertEqual(memory.vector_index.memory_path, root / "memory" / "lancedb")
                self.assertEqual(memory.vector_index.competency_path, root / "competency" / "lancedb")
                self.assertIn("memory_index", memory.vector_index.memory_store._list_tables())
                self.assertIn("skill_index", memory.vector_index.competency_store._list_tables())
                self.assertIn("skill_reference_index", memory.vector_index.competency_store._list_tables())
                self.assertNotIn("skill_index", memory.vector_index.memory_store._list_tables())
                self.assertTrue((root / "memory").is_dir())
                self.assertTrue((root / "competency").is_dir())

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
                compressed = adapter.call_tool(
                    "text_compress",
                    {
                        "text": "发布前先做检查，再执行命令。如果失败，必须立即回滚。",
                        "query": "检查 回滚",
                        "domain_hint": "skill_reference",
                        "budget_chars": 120,
                    },
                )
                self.assertTrue(compressed["summary"])
                self.assertIn("text_compress", {tool["name"] for tool in manifest["tools"]})


if __name__ == "__main__":
    unittest.main()
