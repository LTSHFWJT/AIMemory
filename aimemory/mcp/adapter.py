from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from aimemory.core.scope import CollaborationScope, apply_scope_to_payload, scope_schema

if TYPE_CHECKING:
    from aimemory.core.facade import AIMemory


class AIMemoryMCPAdapter:
    def __init__(self, memory: "AIMemory", scope: CollaborationScope | dict[str, Any] | None = None):
        self.memory = memory
        raw_scope = CollaborationScope.from_value(scope).as_dict(include_none=True)
        self.scope = CollaborationScope.from_value(memory._resolve_scope(**raw_scope))

    def scoped(self, **scope_overrides: Any) -> "AIMemoryMCPAdapter":
        return AIMemoryMCPAdapter(self.memory, scope=self.scope.merge(scope_overrides))

    def litellm_config(self) -> dict[str, Any]:
        return self.memory.litellm_config()

    def _schema(self, properties: dict[str, Any] | None = None, *, required: list[str] | None = None) -> dict[str, Any]:
        scope_properties = dict(scope_schema()["properties"])
        return {
            "type": "object",
            "properties": {
                **scope_properties,
                **dict(properties or {}),
                "context_scope": scope_schema(),
            },
            "required": required or [],
        }

    def _tool(self, name: str, description: str, properties: dict[str, Any] | None = None, *, required: list[str] | None = None) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "inputSchema": self._schema(properties, required=required),
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
                "relational_backend": self.memory.config.relational_backend,
                "index_backend": self.memory._resolve_vector_backend_name(),
                "graph_backend": self.memory._resolve_graph_backend_name(),
                "layout": self.memory.storage_layout(**self.scope.as_metadata()),
            },
        }

    def tool_specs(self) -> list[dict[str, Any]]:
        memory_write = {
            "text": {"type": "string"},
            "session_id": {"type": "string"},
            "memory_type": {"type": "string"},
            "importance": {"type": "number"},
            "metadata": {"type": "object"},
        }
        memory_list = {
            "session_id": {"type": "string"},
            "limit": {"type": "integer", "default": 200},
            "offset": {"type": "integer", "default": 0},
            "include_generated": {"type": "boolean", "default": False},
            "include_inactive": {"type": "boolean", "default": False},
            "filters": {"type": "object"},
        }
        memory_search = {
            "query": {"type": "string"},
            "session_id": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
            "threshold": {"type": "number", "default": 0.0},
            "include_generated": {"type": "boolean", "default": True},
        }
        compression_input = {
            "session_id": {"type": "string"},
            "force": {"type": "boolean", "default": False},
            "limit": {"type": "integer", "default": 400},
        }
        knowledge_write = {
            "title": {"type": "string"},
            "text": {"type": "string"},
            "source_name": {"type": "string"},
            "source_type": {"type": "string"},
            "uri": {"type": "string"},
            "kb_namespace": {"type": "string"},
            "global_scope": {"type": "boolean", "default": False},
            "metadata": {"type": "object"},
        }
        knowledge_list = {
            "limit": {"type": "integer", "default": 100},
            "offset": {"type": "integer", "default": 0},
            "status": {"type": "string", "default": "active"},
            "include_global": {"type": "boolean", "default": True},
        }
        knowledge_search = {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
            "threshold": {"type": "number", "default": 0.0},
            "include_global": {"type": "boolean", "default": True},
        }
        archive_write = {
            "summary": {"type": "string"},
            "content": {"type": "string"},
            "source_type": {"type": "string"},
            "domain": {"type": "string"},
            "session_id": {"type": "string"},
            "global_scope": {"type": "boolean", "default": False},
            "metadata": {"type": "object"},
        }
        archive_list = {
            "session_id": {"type": "string"},
            "limit": {"type": "integer", "default": 100},
            "offset": {"type": "integer", "default": 0},
            "include_global": {"type": "boolean", "default": True},
            "include_generated": {"type": "boolean", "default": False},
        }
        archive_search = {
            "query": {"type": "string"},
            "session_id": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
            "threshold": {"type": "number", "default": 0.0},
            "include_global": {"type": "boolean", "default": True},
        }
        skill_write = {
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
            "status": {"type": "string"},
        }
        skill_list = {
            "limit": {"type": "integer", "default": 100},
            "offset": {"type": "integer", "default": 0},
            "status": {"type": "string", "default": "active"},
        }
        skill_search = {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
            "threshold": {"type": "number", "default": 0.0},
        }
        return [
            self._tool("aimemory_manifest", "返回 AIMemory 的能力、存储布局与 LiteLLM 兼容配置。"),
            self._tool(
                "agent_context_query",
                "跨长期记忆、短期记忆、知识库、技能和归档做统一查询。",
                {
                    "query": {"type": "string"},
                    "domains": {"type": "array", "items": {"type": "string"}},
                    "session_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 8},
                },
                required=["query"],
            ),
            self._tool("long_term_memory_add", "写入指定 agent 与交互主体之间的长期记忆。", memory_write, required=["text"]),
            self._tool("long_term_memory_get", "获取一条长期记忆。", {"memory_id": {"type": "string"}}, required=["memory_id"]),
            self._tool("long_term_memory_list", "列出指定 agent 与主体之间的完整长期记忆。", memory_list),
            self._tool("long_term_memory_search", "按关键字或短查询快速检索长期记忆。", memory_search, required=["query"]),
            self._tool(
                "long_term_memory_update",
                "更新长期记忆内容、权重或元数据。",
                {**memory_write, "memory_id": {"type": "string"}, "status": {"type": "string"}},
                required=["memory_id"],
            ),
            self._tool("long_term_memory_delete", "删除一条长期记忆。", {"memory_id": {"type": "string"}}, required=["memory_id"]),
            self._tool("long_term_memory_compress", "压缩指定 agent 与主体之间的长期记忆，降低 token 负担。", compression_input),
            self._tool("short_term_memory_add", "写入短期记忆。适合当前会话窗口中的重要上下文。", memory_write, required=["text"]),
            self._tool("short_term_memory_get", "获取一条短期记忆。", {"memory_id": {"type": "string"}}, required=["memory_id"]),
            self._tool("short_term_memory_list", "列出指定 agent 与主体之间的完整短期记忆。", memory_list),
            self._tool("short_term_memory_search", "按关键字快速检索短期记忆。", memory_search, required=["query"]),
            self._tool(
                "short_term_memory_update",
                "更新短期记忆内容、权重或元数据。",
                {**memory_write, "memory_id": {"type": "string"}, "status": {"type": "string"}},
                required=["memory_id"],
            ),
            self._tool("short_term_memory_delete", "删除一条短期记忆。", {"memory_id": {"type": "string"}}, required=["memory_id"]),
            self._tool("short_term_memory_compress", "压缩短期记忆；有会话时优先写入 working memory snapshot。", compression_input),
            self._tool("archive_memory_add", "新增归档记忆；支持全局归档。", archive_write, required=["summary"]),
            self._tool("archive_memory_get", "获取一条归档记忆。", {"archive_unit_id": {"type": "string"}}, required=["archive_unit_id"]),
            self._tool("archive_memory_list", "列出归档记忆；可选择包含全局归档。", archive_list),
            self._tool("archive_memory_search", "按关键字检索归档记忆。", archive_search, required=["query"]),
            self._tool(
                "archive_memory_update",
                "更新归档记忆内容或元数据。",
                {**archive_write, "archive_unit_id": {"type": "string"}},
                required=["archive_unit_id"],
            ),
            self._tool("archive_memory_delete", "删除一条归档记忆。", {"archive_unit_id": {"type": "string"}}, required=["archive_unit_id"]),
            self._tool("archive_memory_compress", "压缩一组归档记忆并生成低成本摘要。", {**archive_list, "force": {"type": "boolean", "default": False}}),
            self._tool("knowledge_document_add", "写入知识库文档；支持 agent 私有和全局知识库。", knowledge_write, required=["title", "text"]),
            self._tool("knowledge_document_get", "获取知识库文档完整内容。", {"document_id": {"type": "string"}}, required=["document_id"]),
            self._tool("knowledge_document_list", "列出知识库文档。", knowledge_list),
            self._tool("knowledge_document_search", "检索知识库文档与切块。", knowledge_search, required=["query"]),
            self._tool(
                "knowledge_document_update",
                "更新知识库文档标题、正文、作用域或元数据。",
                {**knowledge_write, "document_id": {"type": "string"}, "status": {"type": "string"}},
                required=["document_id"],
            ),
            self._tool("knowledge_document_delete", "删除一份知识库文档。", {"document_id": {"type": "string"}}, required=["document_id"]),
            self._tool("skill_add", "保存或新增一个 agent skill。", skill_write, required=["name", "description"]),
            self._tool("skill_get", "通过 skill ID 获取完整 skill 内容。", {"skill_id": {"type": "string"}}, required=["skill_id"]),
            self._tool("skill_list_metadata", "列出当前 agent 的所有 skill metadata。", skill_list),
            self._tool("skill_search", "按关键字检索 skill。", skill_search, required=["query"]),
            self._tool(
                "skill_update",
                "更新 skill 元信息，必要时写入新版本。",
                {**skill_write, "skill_id": {"type": "string"}},
                required=["skill_id"],
            ),
            self._tool("skill_delete", "删除一个 skill。", {"skill_id": {"type": "string"}}, required=["skill_id"]),
            self._tool(
                "session_create",
                "创建会话上下文。",
                {
                    "user_id": {"type": "string"},
                    "title": {"type": "string"},
                    "metadata": {"type": "object"},
                },
            ),
            self._tool(
                "session_append_turn",
                "追加一条人-agent 或 agent-agent 交互轮次。",
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
            self._tool(
                "session_compress",
                "压缩会话上下文。",
                {
                    "session_id": {"type": "string"},
                    "budget_chars": {"type": "integer", "default": 600},
                },
                required=["session_id"],
            ),
            self._tool(
                "session_archive",
                "归档整个会话。",
                {
                    "session_id": {"type": "string"},
                    "metadata": {"type": "object"},
                },
                required=["session_id"],
            ),
        ]

    def _handlers(self, payload: dict[str, Any]) -> dict[str, Callable[[], Any]]:
        return {
            "aimemory_manifest": lambda: self.manifest(),
            "agent_context_query": lambda: self.memory.query(**payload),
            "long_term_memory_add": lambda: self.memory.store_long_term_memory(**payload),
            "long_term_memory_get": lambda: self.memory.get_long_term_memory(payload["memory_id"]),
            "long_term_memory_list": lambda: self.memory.list_long_term_memories(**payload),
            "long_term_memory_search": lambda: self.memory.search_long_term_memories(**payload),
            "long_term_memory_update": lambda: self.memory.update_long_term_memory(payload["memory_id"], **{key: value for key, value in payload.items() if key != "memory_id"}),
            "long_term_memory_delete": lambda: self.memory.delete_long_term_memory(payload["memory_id"]),
            "long_term_memory_compress": lambda: self.memory.compress_long_term_memories(**payload),
            "short_term_memory_add": lambda: self.memory.store_short_term_memory(**payload),
            "short_term_memory_get": lambda: self.memory.get_short_term_memory(payload["memory_id"]),
            "short_term_memory_list": lambda: self.memory.list_short_term_memories(**payload),
            "short_term_memory_search": lambda: self.memory.search_short_term_memories(**payload),
            "short_term_memory_update": lambda: self.memory.update_short_term_memory(payload["memory_id"], **{key: value for key, value in payload.items() if key != "memory_id"}),
            "short_term_memory_delete": lambda: self.memory.delete_short_term_memory(payload["memory_id"]),
            "short_term_memory_compress": lambda: self.memory.compress_short_term_memories(**payload),
            "archive_memory_add": lambda: self.memory.save_archive_memory(**payload),
            "archive_memory_get": lambda: self.memory.get_archive_memory(payload["archive_unit_id"]),
            "archive_memory_list": lambda: self.memory.list_archive_memories(**payload),
            "archive_memory_search": lambda: self.memory.search_archive_memories(**payload),
            "archive_memory_update": lambda: self.memory.update_archive_memory(payload["archive_unit_id"], **{key: value for key, value in payload.items() if key != "archive_unit_id"}),
            "archive_memory_delete": lambda: self.memory.delete_archive_memory(payload["archive_unit_id"]),
            "archive_memory_compress": lambda: self.memory.compress_archive_memories(**payload),
            "knowledge_document_add": lambda: self.memory.save_knowledge_document(**payload),
            "knowledge_document_get": lambda: self.memory.get_knowledge_document(payload["document_id"]),
            "knowledge_document_list": lambda: self.memory.list_knowledge_documents(**payload),
            "knowledge_document_search": lambda: self.memory.search_knowledge_documents(**payload),
            "knowledge_document_update": lambda: self.memory.update_knowledge_document(payload["document_id"], **{key: value for key, value in payload.items() if key != "document_id"}),
            "knowledge_document_delete": lambda: self.memory.delete_knowledge_document(payload["document_id"]),
            "skill_add": lambda: self.memory.save_skill(**payload),
            "skill_get": lambda: self.memory.get_skill_content(payload["skill_id"]),
            "skill_list_metadata": lambda: self.memory.list_skill_metadata(**payload),
            "skill_search": lambda: self.memory.search_skill_keywords(**payload),
            "skill_update": lambda: self.memory.update_skill(payload["skill_id"], **{key: value for key, value in payload.items() if key != "skill_id"}),
            "skill_delete": lambda: self.memory.delete_skill(payload["skill_id"]),
            "session_create": lambda: self.memory.create_session(**payload),
            "session_append_turn": lambda: self.memory.append_turn(**payload),
            "session_compress": lambda: self.memory.compress_session_context(**payload),
            "session_archive": lambda: self.memory.archive_session(**payload),
            "memory_store_long_term": lambda: self.memory.store_long_term_memory(**payload),
            "memory_store_short_term": lambda: self.memory.store_short_term_memory(**payload),
            "memory_search": lambda: self.memory.memory_search(**payload),
            "knowledge_ingest": lambda: self.memory.save_knowledge_document(**payload),
            "skill_save": lambda: self.memory.save_skill(**payload),
        }

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        payload = apply_scope_to_payload(arguments, default_scope=self.scope)
        handlers = self._handlers(payload)
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
            tool_name = spec["name"]
            description = spec["description"]

            def make_handler(name: str):
                def handler(**kwargs):
                    return self.call_tool(name, kwargs)

                return handler

            fastmcp.tool(name=tool_name, description=description)(make_handler(tool_name))
        return fastmcp
