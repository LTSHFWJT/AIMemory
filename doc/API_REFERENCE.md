# AIMemory API Reference

本文档提供 `AIMemory` 项目的总体 API 索引，适合作为“查表式”参考。

- 详细 Facade 说明见 `doc/facade-api.md`
- Service / Worker 说明见 `doc/service-worker-api.md`

## 1. 顶层导出

`aimemory/__init__.py` 当前导出：

| 名称 | 类型 | 说明 |
| --- | --- | --- |
| `AIMemory` | Class | 同步主入口 |
| `AsyncAIMemory` | Class | 异步包装入口 |
| `ScopedAIMemory` | Class | 带默认作用域的门面 |
| `AIMemoryMCPAdapter` | Class | MCP 工具适配器 |
| `AIMemoryConfig` | Dataclass | 主配置 |
| `ProviderLiteConfig` | Dataclass | LiteLLM 风格 provider 配置 |
| `EmbeddingLiteConfig` | Dataclass | 嵌入模型配置 |
| `CollaborationScope` | Dataclass | 多智能体协作作用域模型 |
| `register_relational_backend` | Function | 注册关系型数据库插件 |
| `register_vector_backend` | Function | 注册向量数据库插件 |
| `register_graph_backend` | Function | 注册图数据库插件 |

## 2. 配置对象

### 2.1 `AIMemoryConfig`

核心字段：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `root_dir` | `.aimemory` | 根目录 |
| `sqlite_path` | 自动推导 | SQLite 文件路径 |
| `object_store_path` | 自动推导 | 对象存储目录 |
| `relational_backend` | `sqlite` | 关系型后端插件名 |
| `default_user_id` | `default` | 默认用户 |
| `platform_id` | `None` | 平台维度 |
| `workspace_id` | `None` | 工作区维度 |
| `team_id` | `None` | 团队维度 |
| `project_id` | `None` | 项目维度 |
| `index_backend` | `sqlite` | 向量后端名 |
| `graph_backend` | `sqlite` | 图后端名 |
| `enable_lancedb` | `False` | 启用 LanceDB |
| `enable_faiss` | `False` | 启用 FAISS |
| `enable_kuzu` | `False` | 启用 Kuzu |
| `providers` | `ProviderLiteConfig()` | LiteLLM 风格 provider 配置 |
| `embeddings` | `EmbeddingLiteConfig()` | 嵌入配置 |
| `memory_policy` | `MemoryPolicy()` | 记忆策略配置 |

### 2.2 `ProviderLiteConfig`

面向上层 Agent 的模型调用配置透出：

| 字段 | 说明 |
| --- | --- |
| `provider` | provider 名，如 `openai` |
| `model` | 模型名 |
| `api_base` | 接口地址 |
| `api_key_env` | API Key 环境变量名 |
| `organization` | 组织 ID |
| `headers` | 自定义请求头 |
| `extra` | 透传扩展参数 |

### 2.3 `EmbeddingLiteConfig`

默认配置：

| 字段 | 默认值 |
| --- | --- |
| `provider` | `sentence-transformers` |
| `model` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| `dimensions` | `384` |
| `normalize` | `True` |
| `batch_size` | `32` |

## 3. 作用域模型

`CollaborationScope` / scoped 机制是当前项目最关键的抽象之一。

### 3.1 作用域字段

| 字段 | 说明 |
| --- | --- |
| `user_id` | 用户 ID |
| `agent_id` | 当前 agent ID |
| `owner_agent_id` | 记忆所有者 agent |
| `subject_type` | `human` / `agent` |
| `subject_id` | 主体 ID |
| `interaction_type` | `human_agent` / `agent_agent` |
| `platform_id` | 平台 ID |
| `workspace_id` | 工作区 ID |
| `team_id` | 团队 ID |
| `project_id` | 项目 ID |
| `namespace_key` | 自动推导或手动指定的命名空间键 |

### 3.2 作用域生效范围

这些字段会影响：

- 记忆写入
- 统一查询
- 归档召回
- 对象存储路径前缀
- MCP 默认作用域

## 4. 顶层 Facade API 索引

### 4.0 面向 Agent 的域级 API

| 方法 | 说明 |
| --- | --- |
| `store_long_term_memory(...)` | 写入长期记忆并按阈值触发长期压缩 |
| `get_long_term_memory(memory_id)` | 获取长期记忆 |
| `list_long_term_memories(**kwargs)` | 列出指定 agent 与主体之间的完整长期记忆 |
| `search_long_term_memories(query, **kwargs)` | 通过关键字快速检索长期记忆 |
| `update_long_term_memory(memory_id, **kwargs)` | 更新长期记忆 |
| `delete_long_term_memory(memory_id)` | 删除长期记忆 |
| `compress_long_term_memories(**kwargs)` | 压缩长期记忆 |
| `store_short_term_memory(...)` | 写入短期记忆并按阈值触发短期压缩 |
| `list_short_term_memories(**kwargs)` | 列出完整短期记忆 |
| `search_short_term_memories(query, **kwargs)` | 通过关键字快速检索短期记忆 |
| `compress_short_term_memories(**kwargs)` | 压缩短期记忆；有会话时写入 snapshot |
| `save_knowledge_document(...)` | 写入知识库文档，支持 `global_scope=True` |
| `list_knowledge_documents(**kwargs)` | 列出知识库文档，支持全局知识库 |
| `search_knowledge_documents(query, **kwargs)` | 检索知识库文档 |
| `update_knowledge_document(document_id, **kwargs)` | 更新知识库文档 |
| `delete_knowledge_document(document_id)` | 删除知识库文档 |
| `get_skill_content(skill_id)` | 获取完整 skill 内容 |
| `list_skill_metadata(**kwargs)` | 列出 skill metadata |
| `search_skill_keywords(query, **kwargs)` | 通过关键字检索 skill |
| `update_skill(skill_id, **kwargs)` | 更新 skill，并可追加新版本 |
| `delete_skill(skill_id)` | 删除 skill |
| `save_archive_memory(...)` | 手动新增归档记忆，支持全局归档 |
| `list_archive_memories(**kwargs)` | 列出归档记忆 |
| `search_archive_memories(query, **kwargs)` | 检索归档记忆 |
| `update_archive_memory(archive_unit_id, **kwargs)` | 更新归档记忆 |
| `delete_archive_memory(archive_unit_id)` | 删除归档记忆 |
| `compress_archive_memories(**kwargs)` | 压缩归档记忆并生成低成本摘要 |
| `register_domain_compressor(domain, compressor)` | 注册外部域级压缩器 |
| `compress_domain_records(domain, records, **kwargs)` | 手动调用统一压缩入口 |

### 4.1 记忆相关

| 方法 | 说明 |
| --- | --- |
| `add(messages, **kwargs)` | 从消息列表做自动提取并写入记忆 |
| `remember_long_term(text, **kwargs)` | 写长期记忆 |
| `remember_short_term(text, **kwargs)` | 写短期记忆 |
| `memory_store(text, **kwargs)` | 通用存储入口 |
| `memory_search(query, **kwargs)` | 搜索记忆 |
| `memory_list(**kwargs)` | 列出记忆 |
| `memory_get(memory_id)` | 获取单条记忆 |
| `memory_forget(...)` | 删除单条或按查询删除 |
| `update(memory_id, **kwargs)` | 更新记忆 |
| `delete(memory_id)` | 删除记忆 |
| `history(memory_id)` | 查看记忆事件历史 |

### 4.2 会话与交互

| 方法 | 说明 |
| --- | --- |
| `create_session(**kwargs)` | 创建会话 |
| `get_session(session_id)` | 获取会话 |
| `append_turn(session_id, role, content, **kwargs)` | 追加对话轮次 |
| `compress_session_context(session_id, **kwargs)` | 压缩会话 |
| `promote_session_memories(session_id, **kwargs)` | 晋升短期记忆 |
| `get_snapshot(snapshot_id)` | 获取 snapshot |
| `session_health(session_id)` | 查看会话健康状态 |
| `prune_session_snapshots(session_id)` | 清理旧 snapshot |
| `govern_session(session_id, **kwargs)` | 组合治理入口 |

### 4.3 知识库

| 方法 | 说明 |
| --- | --- |
| `ingest_document(title, text, **kwargs)` | 写入文档 |
| `ingest_knowledge(title, text, **kwargs)` | `ingest_document` 别名 |
| `get_document(document_id)` | 获取文档 |
| `search_knowledge(query, **kwargs)` | 搜索知识库 |
| `search_knowledge(query, include_global=True, **kwargs)` | 搜索知识库并兼容全局知识库 |

### 4.4 技能

| 方法 | 说明 |
| --- | --- |
| `save_skill(name, description, **kwargs)` | 保存技能 |
| `register_skill(name, description, **kwargs)` | `save_skill` 别名 |
| `get_skill(skill_id)` | 获取技能 |
| `list_skills(status=None)` | 列出技能 |
| `search_skills(query, **kwargs)` | 搜索技能 |

### 4.5 归档

| 方法 | 说明 |
| --- | --- |
| `archive_memory(memory_id, **kwargs)` | 归档单条记忆 |
| `archive_session(session_id, **kwargs)` | 归档会话 |
| `get_archive_unit(archive_unit_id)` | 获取归档单元 |
| `search_archive(query, **kwargs)` | 搜索归档摘要 |
| `search_archive(query, include_global=True, **kwargs)` | 搜索归档并兼容全局归档 |

### 4.6 执行过程

| 方法 | 说明 |
| --- | --- |
| `start_run(user_id=None, goal="", **kwargs)` | 创建执行 run |
| `search_execution(query, **kwargs)` | 搜索执行记录 |

### 4.7 统一召回与系统能力

| 方法 | 说明 |
| --- | --- |
| `query(query, **kwargs)` | 跨域统一查询 |
| `explain_recall(query, **kwargs)` | 输出召回解释 |
| `project(limit=None)` | 重建 / 投影索引 |
| `describe_capabilities()` | 输出能力清单 |
| `storage_layout(**scope_kwargs)` | 输出当前作用域下的存储布局 |
| `scoped(**scope_kwargs)` | 创建 scoped facade |
| `create_mcp_adapter(scope=None)` | 创建 MCP 适配器 |
| `litellm_config()` | 输出 LiteLLM 风格配置 |

## 5. `ScopedAIMemory`

`ScopedAIMemory` 是 `AIMemory` 的作用域封装。

### 5.1 典型用途

- 团队多智能体平台
- 固定 workspace/team/project 下的大量重复读写
- 希望减少每次调用传参噪音

### 5.2 常用方法

`ScopedAIMemory` 主要复用 `AIMemory` 的高频方法：

- `create_session`
- `append_turn`
- `remember_long_term`
- `remember_short_term`
- `memory_search`
- `query`
- `ingest_document`
- `save_skill`
- `archive_session`
- `search_archive`
- `compress_session_context`
- `storage_layout`
- `create_mcp_adapter`

## 6. MCP Adapter

### 6.1 `AIMemoryMCPAdapter`

主要方法：

| 方法 | 说明 |
| --- | --- |
| `tool_specs()` | 导出工具描述 |
| `call_tool(name, arguments)` | 本地调用工具 |
| `manifest()` | 导出 manifest |
| `litellm_config()` | 导出 provider 配置 |
| `scoped(**scope_overrides)` | 创建带默认作用域的子 adapter |
| `bind_fastmcp(server=None)` | 绑定到 `FastMCP` |

### 6.2 当前内置 MCP 工具

| 工具名 | 说明 |
| --- | --- |
| `aimemory_manifest` | 返回能力、LiteLLM 配置与存储布局 |
| `agent_context_query` | 跨域统一查询 |
| `long_term_memory_*` | 长期记忆增删改查与压缩 |
| `short_term_memory_*` | 短期记忆增删改查与压缩 |
| `archive_memory_*` | 归档记忆增删改查与压缩 |
| `knowledge_document_*` | 知识库文档增删改查 |
| `skill_*` | 技能增删改查 |
| `session_create` | 创建会话 |
| `session_append_turn` | 追加对话轮次 |
| `session_compress` | 压缩会话 |
| `session_archive` | 归档会话 |

### 6.3 MCP 作用域入参

工具既支持平铺字段，也支持嵌套 `context_scope`：

```python
{
  "query": "最近偏好",
  "context_scope": {
    "workspace_id": "ws.alpha",
    "team_id": "team.memory",
    "owner_agent_id": "agent.planner",
    "subject_type": "agent",
    "subject_id": "agent.executor"
  }
}
```

## 7. 后端插件 API

顶层注册方法：

| 方法 | 说明 |
| --- | --- |
| `register_vector_backend(name, factory)` | 注册自定义向量后端 |
| `register_graph_backend(name, factory)` | 注册自定义图后端 |

当前内置后端：

| 类别 | 默认 | 可选 |
| --- | --- | --- |
| 关系型 | SQLite | — |
| 向量 | sqlite 语义缓存回退 | LanceDB / FAISS |
| 图 | sqlite 图回退 | Kuzu |

## 8. `describe_capabilities()`

该接口返回四大类能力：

| 分类 | 说明 |
| --- | --- |
| `core` | 本地、轻量、全域、多智能体、MCP |
| `embeddings` | 当前嵌入 runtime 能力 |
| `vector_index` | 当前向量后端能力 |
| `graph_store` | 当前图后端能力 |
| `algorithms` | 去重、蒸馏、检索、压缩能力 |
| `mcp` | MCP 工具和 LiteLLM 配置透出能力 |

## 9. `storage_layout()`

这个接口会返回当前作用域下不同存储域的布局说明：

- `long_term_memory`
- `short_term_memory`
- `knowledge`
- `skill`
- `archive`

每个域会描述：

- 使用哪些表
- 对象存储前缀
- 当前策略说明

## 10. 推荐查阅顺序

如果你第一次接触这个项目，建议这样看：

1. `README.md`
2. `doc/QUICKSTART.md`
3. `doc/facade-api.md`
4. `doc/service-worker-api.md`
