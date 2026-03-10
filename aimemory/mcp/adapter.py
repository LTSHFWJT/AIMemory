from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aimemory.core.facade import AIMemory


class AIMemoryMCPAdapter:
    def __init__(self, memory: "AIMemory"):
        self.memory = memory

    def litellm_config(self) -> dict[str, Any]:
        return self.memory.litellm_config()

    def manifest(self) -> dict[str, Any]:
        return {
            "name": "aimemory",
            "transport": "in-process",
            "tools": self.tool_specs(),
            "litellm": self.litellm_config(),
            "embeddings": self.memory.config.embeddings.as_provider_kwargs(),
            "storage": {
                "root_dir": str(self.memory.config.root_dir),
                "sqlite_path": str(self.memory.config.sqlite_path),
                "index_backend": self.memory._resolve_vector_backend_name(),
                "graph_backend": self.memory._resolve_graph_backend_name(),
            },
        }

    def tool_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "agent_context_query",
                "description": "跨长期记忆、短期上下文、知识库、技能和归档进行统一查询。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "user_id": {"type": "string"},
                        "session_id": {"type": "string"},
                        "domains": {"type": "array", "items": {"type": "string"}},
                        "limit": {"type": "integer", "default": 8},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "memory_store_long_term",
                "description": "将稳定、可复用的信息存入长期记忆。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "user_id": {"type": "string"},
                        "session_id": {"type": "string"},
                        "memory_type": {"type": "string"},
                        "importance": {"type": "number"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "memory_store_short_term",
                "description": "将当前会话中的临时上下文存入短期记忆。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "user_id": {"type": "string"},
                        "session_id": {"type": "string"},
                        "memory_type": {"type": "string"},
                        "importance": {"type": "number"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["text", "session_id"],
                },
            },
            {
                "name": "memory_search",
                "description": "搜索记忆层，优先返回压缩过和去重后的高价值结果。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "user_id": {"type": "string"},
                        "session_id": {"type": "string"},
                        "scope": {"type": "string", "default": "all"},
                        "limit": {"type": "integer", "default": 8},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "knowledge_ingest",
                "description": "向知识库写入文档并自动切块、压缩和索引。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "text": {"type": "string"},
                        "source_name": {"type": "string"},
                        "source_type": {"type": "string", "default": "inline"},
                        "user_id": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["title", "text"],
                },
            },
            {
                "name": "skill_save",
                "description": "保存技能定义、版本、工具绑定和测试样例。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "prompt_template": {"type": "string"},
                        "workflow": {},
                        "tools": {"type": "array", "items": {"type": "string"}},
                        "topics": {"type": "array", "items": {"type": "string"}},
                        "metadata": {"type": "object"},
                    },
                    "required": ["name", "description"],
                },
            },
            {
                "name": "session_compress",
                "description": "压缩会话上下文，降低后续上下文拼接成本。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "budget_chars": {"type": "integer", "default": 600},
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "session_archive",
                "description": "将会话归档为低成本摘要，并保留可检索线索。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["session_id"],
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        payload = dict(arguments or {})
        handlers = {
            "agent_context_query": lambda: self.memory.query(**payload),
            "memory_store_long_term": lambda: self.memory.remember_long_term(**payload),
            "memory_store_short_term": lambda: self.memory.remember_short_term(**payload),
            "memory_search": lambda: self.memory.memory_search(**payload),
            "knowledge_ingest": lambda: self.memory.ingest_document(**payload),
            "skill_save": lambda: self.memory.save_skill(**payload),
            "session_compress": lambda: self.memory.compress_session_context(**payload),
            "session_archive": lambda: self.memory.archive_session(**payload),
        }
        if name not in handlers:
            raise ValueError(f"Unknown MCP tool `{name}`")
        return handlers[name]()

    def bind_fastmcp(self, server=None):
        try:
            from mcp.server.fastmcp import FastMCP  # type: ignore
        except ImportError as exc:
            raise RuntimeError("`mcp` package is not installed.") from exc

        fastmcp = server or FastMCP("aimemory")
        for spec in self.tool_specs():
            name = spec["name"]
            description = spec["description"]

            def make_handler(tool_name: str):
                def handler(**kwargs):
                    return self.call_tool(tool_name, kwargs)

                return handler

            fastmcp.tool(name=name, description=description)(make_handler(name))
        return fastmcp
