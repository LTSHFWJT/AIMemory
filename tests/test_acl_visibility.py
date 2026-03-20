from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from aimemory import AIMemory


class ACLVisibilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.memory = AIMemory({"root_dir": self.tempdir.name})
        self.shared_scope = {
            "workspace_id": "ws.alpha",
            "team_id": "team.alpha",
            "namespace_key": "shared.alpha",
            "subject_type": "human",
            "subject_id": "user-1",
            "interaction_type": "human_agent",
        }

    def tearDown(self) -> None:
        self.memory.close()
        self.tempdir.cleanup()

    def _agent(self, agent_id: str, **scope_overrides):
        scope = {**self.shared_scope, **scope_overrides}
        return self.memory.scoped(owner_agent_id=agent_id, agent_id=agent_id, **scope)

    def test_private_memory_can_be_granted_and_revoked_via_acl(self) -> None:
        planner = self._agent("agent.planner")
        reviewer = self._agent("agent.reviewer")

        memory = planner.api.long_term.add("仅 planner 默认可见的长期记忆。")

        with self.assertRaises(ValueError):
            reviewer.api.long_term.get(memory["id"])

        rule = planner.api.acl.grant(
            resource_type="memory",
            resource_scope="long_term",
            principal_type="agent",
            principal_id="agent.reviewer",
            permission="read",
            metadata={"reason": "review access"},
        )
        self.assertEqual(rule["principal_id"], "agent.reviewer")
        self.assertTrue(planner.api.acl.list()["results"])

        visible = reviewer.api.long_term.get(memory["id"])
        self.assertEqual(visible["id"], memory["id"])
        self.assertTrue(any(item["id"] == memory["id"] for item in reviewer.api.long_term.search("planner 默认可见")["results"]))

        revoked = planner.api.acl.revoke(rule_id=rule["id"])
        self.assertTrue(revoked["deleted"])
        with self.assertRaises(ValueError):
            reviewer.api.long_term.get(memory["id"])

    def test_shared_workspace_visibility_allows_same_workspace_but_blocks_other_workspace(self) -> None:
        planner = self._agent("agent.planner")
        same_workspace = self._agent("agent.executor")
        other_workspace = self._agent("agent.executor", workspace_id="ws.beta")

        memory = planner.api.long_term.add("同工作空间协同代理都应可见的记忆。")
        self.memory.db.execute(
            "UPDATE long_term_memories SET visibility = ? WHERE id = ?",
            ("shared_workspace", memory["id"]),
        )

        visible = same_workspace.api.long_term.get(memory["id"])
        self.assertEqual(visible["id"], memory["id"])

        with self.assertRaises(ValueError):
            other_workspace.api.long_term.get(memory["id"])

    def test_direct_memory_mutation_requires_write_acl_not_just_read_access(self) -> None:
        planner = self._agent("agent.planner")
        reviewer = self._agent("agent.reviewer")
        memory = planner.api.long_term.add("只有 owner 可以直接修改的记忆。")

        with self.assertRaises(PermissionError):
            self.memory.update(
                memory["id"],
                text="reviewer 试图直接修改。",
                owner_agent_id="agent.reviewer",
                agent_id="agent.reviewer",
                **self.shared_scope,
            )

        planner.api.acl.grant(
            resource_type="memory",
            resource_scope="long_term",
            principal_type="agent",
            principal_id="agent.reviewer",
            permission="read",
        )
        self.assertEqual(reviewer.api.long_term.get(memory["id"])["id"], memory["id"])
        with self.assertRaises(PermissionError):
            self.memory.update(
                memory["id"],
                text="仅读权限不能修改。",
                owner_agent_id="agent.reviewer",
                agent_id="agent.reviewer",
                **self.shared_scope,
            )

        planner.api.acl.grant(
            resource_type="memory",
            resource_scope="long_term",
            principal_type="agent",
            principal_id="agent.reviewer",
            permission="write",
        )
        updated = self.memory.update(
            memory["id"],
            text="写权限下允许直接更新。",
            owner_agent_id="agent.reviewer",
            agent_id="agent.reviewer",
            **self.shared_scope,
        )
        self.assertEqual(updated["text"], "写权限下允许直接更新。")

    def test_knowledge_update_and_session_manage_require_acl(self) -> None:
        planner = self._agent("agent.planner")
        reviewer = self._agent("agent.reviewer")

        document = planner.api.knowledge.add(
            "变更规范",
            "只有具备写权限的 agent 才能修改知识文档。",
        )
        session = planner.api.session.create(user_id="user-1", title="manage-demo")
        planner.api.session.append(session["id"], "user", "先生成一个 snapshot。", auto_compress=False)
        planner.api.session.append(session["id"], "assistant", "继续补充上下文。", auto_compress=False)
        planner.api.session.append(session["id"], "user", "这样才能测试 prune。", auto_compress=False)
        planner.api.session.compress(session["id"], budget_chars=120)

        with self.assertRaises(PermissionError):
            reviewer.api.knowledge.update(document["id"], title="reviewer 修改标题")
        with self.assertRaises(PermissionError):
            reviewer.api.session.prune(session["id"])

        planner.api.acl.grant(
            resource_type="knowledge",
            resource_scope="document",
            principal_type="agent",
            principal_id="agent.reviewer",
            permission="write",
        )
        planner.api.acl.grant(
            resource_type="session",
            resource_scope="session",
            principal_type="agent",
            principal_id="agent.reviewer",
            permission="manage",
        )

        updated = reviewer.api.knowledge.update(document["id"], title="reviewer 已获授权")
        self.assertEqual(updated["title"], "reviewer 已获授权")
        pruned = reviewer.api.session.prune(session["id"])
        self.assertIn("removed", pruned)

    def test_handoff_and_context_are_only_visible_to_target_agent(self) -> None:
        planner = self._agent("agent.planner")
        target = self._agent("agent.executor")
        observer = self._agent("agent.observer")

        session = planner.api.session.create(user_id="user-1", title="handoff-demo")
        planner.api.session.append(session["id"], "user", "需要整理部署窗口、回滚步骤和执行约束。", auto_compress=False)
        planner.api.session.append(session["id"], "assistant", "交接给执行代理时要保持上下文轻量。", auto_compress=False)
        planner.api.long_term.add("用户希望先给结论，再给执行步骤。")

        handoff = planner.api.handoff.build(
            "agent.executor",
            source_session_id=session["id"],
            source_agent_id="agent.planner",
            use_platform_llm=False,
            budget_chars=220,
        )

        self.assertEqual(target.api.handoff.get(handoff["id"])["id"], handoff["id"])
        self.assertEqual(target.api.context.get(handoff["artifact"]["id"])["id"], handoff["artifact"]["id"])
        self.assertTrue(any(item["id"] == handoff["id"] for item in target.api.handoff.list()["results"]))

        self.assertIsNone(observer.api.handoff.get(handoff["id"]))
        self.assertIsNone(observer.api.context.get(handoff["artifact"]["id"]))
        self.assertFalse(observer.api.handoff.list()["results"])

    def test_mcp_manifest_and_tools_include_acl_operations(self) -> None:
        adapter = self.memory.create_mcp_adapter(scope={"owner_agent_id": "agent.planner", "agent_id": "agent.planner", **self.shared_scope})
        tool_names = {tool["name"] for tool in adapter.manifest()["tools"]}

        self.assertIn("acl_grant", tool_names)
        self.assertIn("acl_list", tool_names)
        self.assertIn("acl_revoke", tool_names)

        granted = adapter.call_tool(
            "acl_grant",
            {
                "principal_type": "agent",
                "principal_id": "agent.reviewer",
                "resource_type": "memory",
                "resource_scope": "long_term",
            },
        )
        self.assertEqual(granted["principal_id"], "agent.reviewer")
        listed = adapter.call_tool("acl_list", {})
        self.assertTrue(any(item["id"] == granted["id"] for item in listed["results"]))


if __name__ == "__main__":
    unittest.main()
