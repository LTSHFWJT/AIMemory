from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from aimemory import AIMemory, list_platform_llm_plugins, register_platform_llm_plugin, unregister_platform_llm_plugin


class _PluginPlatformLLM:
    def __init__(self, *, provider: str, model: str):
        self.provider = provider
        self.model = model

    def compress(self, *, task_type, records, budget_chars, scope, metadata=None):
        return {
            "summary": f"{task_type} via plugin",
            "highlights": ["plugin registered", "platform compression"],
            "steps": ["keep current plan"],
            "constraints": ["stay lightweight"],
            "facts": [str(item.get("text") or "")[:32] for item in list(records)[:2]],
            "provider": self.provider,
            "model": self.model,
            "metadata": {"scope": dict(scope), **dict(metadata or {})},
        }


class _InjectedPlatformLLM(_PluginPlatformLLM):
    pass


class PlatformLLMPluginTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.plugin_name = "test.platform.mock"

        def factory(config: dict[str, object]) -> _PluginPlatformLLM:
            return _PluginPlatformLLM(
                provider=str(config.get("provider") or "plugin-provider"),
                model=str(config.get("model") or "plugin-model"),
            )

        register_platform_llm_plugin(self.plugin_name, factory)
        self.memory: AIMemory | None = None

    def tearDown(self) -> None:
        if self.memory is not None:
            self.memory.close()
        unregister_platform_llm_plugin(self.plugin_name)
        self.tempdir.cleanup()

    def _seed_scope(self) -> dict[str, str]:
        return {
            "owner_agent_id": "agent.planner",
            "subject_type": "human",
            "subject_id": "user-1",
        }

    def test_platform_llm_plugin_from_config_drives_context_build(self) -> None:
        self.assertIn(self.plugin_name, list_platform_llm_plugins())
        self.memory = AIMemory(
            {
                "root_dir": self.tempdir.name,
                "memory_policy": {
                    "compression_budget_chars": 220,
                },
                "platform_llm_plugin": {
                    "name": self.plugin_name,
                    "provider": "plugin-configured",
                    "model": "plugin-compressor",
                },
            }
        )
        self.memory.api.long_term.add("平台插件压缩应该走注册表，而不是 MCP。", **self._seed_scope())

        context = self.memory.api.context.build(
            "平台插件压缩",
            include_domains=["memory"],
            use_platform_llm=True,
            budget_chars=220,
            **self._seed_scope(),
        )

        self.assertEqual(context["job"]["status"], "completed")
        self.assertEqual(context["artifact"]["provider"], "plugin-configured")
        self.assertEqual(context["artifact"]["model"], "plugin-compressor")
        self.assertEqual(context["compression"]["summary"], "context_build via plugin")

    def test_bind_platform_llm_supports_runtime_plugin_switch(self) -> None:
        self.memory = AIMemory({"root_dir": self.tempdir.name})
        self.memory.bind_platform_llm(plugin_name=self.plugin_name, settings={"provider": "bound-provider", "model": "bound-model"})
        self.memory.api.long_term.add("运行时绑定插件后也应可用于高级上下文压缩。", **self._seed_scope())

        context = self.memory.api.context.build(
            "运行时绑定",
            include_domains=["memory"],
            use_platform_llm=True,
            budget_chars=220,
            **self._seed_scope(),
        )

        self.assertEqual(context["artifact"]["provider"], "bound-provider")
        self.assertEqual(context["artifact"]["model"], "bound-model")

        self.memory.bind_platform_llm(_InjectedPlatformLLM(provider="direct-provider", model="direct-model"))
        context = self.memory.api.context.build(
            "直接注入覆盖插件",
            include_domains=["memory"],
            use_platform_llm=True,
            budget_chars=220,
            **self._seed_scope(),
        )

        self.assertEqual(context["artifact"]["provider"], "direct-provider")
        self.assertEqual(context["artifact"]["model"], "direct-model")


if __name__ == "__main__":
    unittest.main()
