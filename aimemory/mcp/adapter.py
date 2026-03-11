from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aimemory.core.scope import CollaborationScope, apply_scope_to_payload, scope_schema

if TYPE_CHECKING:
    from aimemory.core.facade import AIMemory


class AIMemoryMCPAdapter:
    def __init__(self, memory: "AIMemory", scope: CollaborationScope | dict[str, Any] | None = None):
        self.memory = memory
        self.scope = CollaborationScope.from_value(scope)

    def scoped(self, **scope_overrides: Any) -> "AIMemoryMCPAdapter":
        return AIMemoryMCPAdapter(self.memory, scope=self.scope.merge(scope_overrides))

    def litellm_config(self) -> dict[str, Any]:
        return self.memory.litellm_config()

    def _schema(self, properties: dict[str, Any], *, required: list[str] | None = None) -> dict[str, Any]:
        scope_properties = dict(scope_schema()["properties"])
        return {
            "type": "object",
            "properties": {
                **scope_properties,
                **properties,
                "context_scope": scope_schema(),
            },
            "required": required or [],
        }

    def manifest(self) -> dict[str, Any]:
        return {
            "name": "aimemory",
            "transport": "in-process",
            "tools": self.tool_specs(),
            "litellm": self.litellm_config(),
            "embeddings": self.memory.config.embeddings.as_provider_kwargs(),
            "default_scope": self.scope.as_metadata(),
            "storage": {
                "root_dir": str(self.memory.config.root_dir),
                "sqlite_path": str(self.memory.config.sqlite_path),
                "index_backend": self.memory._resolve_vector_backend_name(),
                "graph_backend": self.memory._resolve_graph_backend_name(),
                "layout": self.memory.storage_layout(**self.scope.as_metadata()),
            },
        }

    def tool_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "agent_context_query",
                "description": "跨长期记忆、短期上下文、知识库、技能和归档进行统一查询。",
                "inputSchema": self._schema(
                    {
                        "query": {"type": "string"},
                        "domains": {"type": "array", "items": {"type": "string"}},
                        "session_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 8},
                    },
                    required=["query"],
                ),
            },
            {
                "name": "memory_store_long_term",
                "description": "将稳定、可复用的信息存入长期记忆。",
                "inputSchema": self._schema(
                    {
                        "text": {"type": "string"},
                        "session_id": {"type": "string"},
                        "memory_type": {"type": "string"},
                        "importance": {"type": "number"},
                        "metadata": {"type": "object"},
                    },
                    required=["text"],
                ),
            },
            {
                "name": "memory_store_short_term",
                "description": "将当前会话中的临时上下文存入短期记忆。",
                "inputSchema": self._schema(
                    {
                        "text": {"type": "string"},
                        "session_id": {"type": "string"},
                        "memory_type": {"type": "string"},
                        "importance": {"type": "number"},
                        "metadata": {"type": "object"},
                    },
                    required=["text", "session_id"],
                ),
            },
            {
                "name": "memory_search",
                "description": "搜索记忆层，优先返回压缩过和去重后的高价值结果。",
                "inputSchema": self._schema(
                    {
                        "query": {"type": "string"},
                        "session_id": {"type": "string"},
                        "scope": {"type": "string", "default": "all"},
                        "limit": {"type": "integer", "default": 8},
                    },
                    required=["query"],
                ),
            },
            {
                "name": "knowledge_ingest",
                "description": "向知识库写入文档并自动切块、压缩和索引。",
                "inputSchema": self._schema(
                    {
                        "title": {"type": "string"},
                        "text": {"type": "string"},
                        "source_name": {"type": "string"},
                        "source_type": {"type": "string"},
                        "uri": {"type": "string"},
                        "kb_namespace": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    required=["title", "text"],
                ),
            },
            {
                "name": "skill_save",
                "description": "保存或更新某个 agent 可复用的技能。",
                "inputSchema": self._schema(
                    {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "version": {"type": "string"},
                        "prompt_template": {"type": "string"},
                        "workflow": {},
                        "schema": {"type": "object"},
                        "tools": {"type": "array", "items": {"type": "string"}},
                        "tests": {"type": "array", "items": {}},
                        "topics": {"type": "array", "items": {"type": "string"}},
                        "metadata": {"type": "object"},
                    },
                    required=["name", "description"],
                ),
            },
            {
                "name": "session_create",
                "description": "创建面向指定主体的会话上下文。",
                "inputSchema": self._schema(
                    {
                        "user_id": {"type": "string"},
                        "title": {"type": "string"},
                        "metadata": {"type": "object"},
                    }
                ),
            },
            {
                "name": "session_append_turn",
                "description": "向当前会话追加一条主体感知的交互轮次。",
                "inputSchema": self._schema(
                    {
                        "session_id": {"type": "string"},
                        "role": {"type": "string"},
                        "content": {"type": "string"},
                        "speaker_participant_id": {"type": "string"},
                        "target_participant_id": {"type": "string"},
                        "speaker_type": {"type": "string"},
                        "speaker_external_id": {"type": "string"},
                        "target_type": {"type": "string"},
                        "target_external_id": {"type": "string"},
                        "turn_type": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    required=["session_id", "role", "content"],
                ),
            },
            {
                "name": "session_compress",
                "description": "压缩会话上下文，降低后续上下文拼接成本。",
                "inputSchema": self._schema(
                    {
                        "session_id": {"type": "string"},
                        "budget_chars": {"type": "integer", "default": 600},
                    },
                    required=["session_id"],
                ),
            },
            {
                "name": "session_archive",
                "description": "将会话归档为低成本摘要，并保留可检索线索。",
                "inputSchema": self._schema(
                    {
                        "session_id": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    required=["session_id"],
                ),
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        payload = apply_scope_to_payload(arguments, default_scope=self.scope)
        handlers = {
            "agent_context_query": lambda: self.memory.query(**payload),
            "memory_store_long_term": lambda: self.memory.remember_long_term(**payload),
            "memory_store_short_term": lambda: self.memory.remember_short_term(**payload),
            "memory_search": lambda: self.memory.memory_search(**payload),
            "knowledge_ingest": lambda: self.memory.ingest_document(**payload),
            "skill_save": lambda: self.memory.save_skill(**payload),
            "session_create": lambda: self.memory.create_session(**payload),
            "session_append_turn": lambda: self.memory.append_turn(**payload),
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
