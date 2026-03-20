# AIMemory API Reference

本文档描述当前仓库中对外推荐的公共调用面，重点覆盖多人多智能体协同平台需要直接依赖的对象。

## 1. 公共对象

### `AIMemory`

同步主入口。

```python
from aimemory import AIMemory

memory = AIMemory(
    {"root_dir": ".aimemory"},
    platform_llm=None,
    platform_events=None,
)
```

常用成员：

| 成员 | 说明 |
| --- | --- |
| `api` | 结构化 API 根入口 |
| `events` | 平台事件适配器 |
| `scoped(**scope_kwargs)` | 创建固定作用域句柄 |
| `bind_platform_llm(...)` | 运行时绑定平台 LLM 或平台 LLM 插件 |
| `create_mcp_adapter(scope=None)` | 创建 MCP 适配器，属于可选工具面 |
| `describe_capabilities()` | 返回当前能力、存储和插件信息 |
| `storage_layout(**scope_kwargs)` | 返回存储布局 |
| `compress_text(...)` | 本地算法文本压缩 |
| `compress_document(...)` | 单文档本地压缩 |
| `close()` | 关闭实例 |

### `ScopedAIMemory`

适合把一组 scope 固定下来，给一个 agent、一个工作区或一个协作任务复用。

```python
scoped = memory.scoped(
    workspace_id="ws.alpha",
    team_id="team.alpha",
    owner_agent_id="agent.planner",
    subject_type="agent",
    subject_id="agent.executor",
    interaction_type="agent_agent",
)
```

常用成员：

| 成员 | 说明 |
| --- | --- |
| `api` | 自动继承 scope 的结构化 API |
| `using(**scope_overrides)` | 派生新的 scoped 句柄 |
| `scope_dict()` | 返回当前解析后的 scope |
| `storage_layout()` | 查看 scoped 存储布局 |
| `create_mcp_adapter()` | 创建带默认 scope 的 MCP adapter |

### `AsyncAIMemory`

异步包装器。底层仍复用同步内核，通过 `asyncio.to_thread(...)` 调用。

```python
from aimemory import AsyncAIMemory

memory = AsyncAIMemory({"root_dir": ".aimemory-async"})
await memory.api.long_term.add("异步也使用同一组 API。")
await memory.close()
```

### `AIMemoryMCPAdapter`

可选工具面。

对外提供：

- `manifest()`
- `tool_specs()`
- `call_tool(name, arguments=None)`
- `bind_fastmcp(server=None)`

### 平台插件注册函数

```python
from aimemory import (
    register_platform_llm_plugin,
    unregister_platform_llm_plugin,
    list_platform_llm_plugins,
    create_platform_llm_plugin,
)
```

用途：

- 为平台自己的 LLM 压缩器注册工厂
- 通过配置或运行时绑定方式解析插件
- 不要求 LangChain，不要求 MCP

## 2. 配置对象

### `AIMemoryConfig`

常用字段：

| 字段 | 说明 |
| --- | --- |
| `root_dir` | 根目录 |
| `sqlite_path` | SQLite 数据库路径 |
| `lancedb_path` | LanceDB 根路径 |
| `object_store_path` | 对象存储目录 |
| `platform_id / workspace_id / team_id / project_id` | 默认平台 scope |
| `default_user_id` | 默认用户 |
| `storage_profile` | 当前存储策略名称 |
| `knowledge_raw_store_policy` | 知识正文外置策略 |
| `memory_inline_char_limit` | memory 文本内联阈值 |
| `providers` | LLM provider 配置 |
| `embeddings` | embedding 配置 |
| `platform_llm_plugin` | 平台 LLM 插件配置 |
| `memory_policy` | 记忆、召回、压缩策略 |

### `PlatformLLMPluginConfig`

平台 LLM 插件配置模型：

```python
{
    "name": "platform.llm",
    "settings": {"endpoint": "https://..."},
    "enabled": True,
}
```

也支持简写：

```python
{
    "name": "platform.llm",
    "endpoint": "https://...",
}
```

未知字段会自动并入 `settings`。

## 3. Scope 模型

所有结构化 API 都支持同一组作用域字段：

| 字段 | 作用 |
| --- | --- |
| `user_id` | 当前用户标识 |
| `agent_id` | 当前调用 agent |
| `owner_agent_id` | 资源拥有者 agent |
| `subject_type` | `human` 或 `agent` |
| `subject_id` | 主体标识 |
| `interaction_type` | 推荐 `human_agent` 或 `agent_agent` |
| `platform_id` | 平台标识 |
| `workspace_id` | 工作区标识 |
| `team_id` | 团队标识 |
| `project_id` | 项目标识 |
| `namespace_key` | 手工命名空间；不传则自动推导 |

`namespace_key` 的自动推导来自 `CollaborationScope.resolved_namespace_key()`。

## 4. Structured API 命名空间

### `api.long_term`

| 方法 | 说明 |
| --- | --- |
| `add(text, **kwargs)` | 写长期记忆 |
| `get(memory_id, **kwargs)` | 获取单条记忆 |
| `list(**kwargs)` | 列表 |
| `search(query, **kwargs)` | 搜索 |
| `update(memory_id, **kwargs)` | 更新 |
| `supersede(memory_id, **kwargs)` | 建立版本替代关系 |
| `history(memory_id, **kwargs)` | 审计历史 |
| `link(memory_id, target_memory_ids, **kwargs)` | 建立 memory link |
| `delete(memory_id, **kwargs)` | 删除 |
| `compress(**kwargs)` | 域级本地压缩 |

### `api.short_term`

方法与 `long_term` 对齐，建议同时传：

- `session_id`
- `run_id`

### `api.knowledge`

| 方法 | 说明 |
| --- | --- |
| `add(title, text, **kwargs)` | 新建知识文档 |
| `get(document_id)` | 获取完整文档 |
| `list(**kwargs)` | 列表 |
| `search(query, **kwargs)` | 搜索文档与切块 |
| `update(document_id, **kwargs)` | 更新 |
| `delete(document_id)` | 删除 |
| `compress(document_id, **kwargs)` | 单文档本地压缩 |

### `api.skill`

| 方法 | 说明 |
| --- | --- |
| `add(name, description, **kwargs)` | 创建或更新 skill |
| `get(skill_id)` | 读取 skill 内容 |
| `list(**kwargs)` | 列表 |
| `search(query, **kwargs)` | 搜 skill 主体 |
| `search_references(query, **kwargs)` | 搜索 reference 切块 |
| `refresh_execution_context(skill_id, **kwargs)` | 刷新 execution context |
| `compress_references(skill_id, **kwargs)` | 本地压缩 reference bundle |
| `update(skill_id, **kwargs)` | 更新 |
| `delete(skill_id)` | 删除 |

### `api.archive`

| 方法 | 说明 |
| --- | --- |
| `add(summary, **kwargs)` | 新建归档 |
| `get(archive_unit_id)` | 读取归档 |
| `list(**kwargs)` | 列表 |
| `search(query, **kwargs)` | 搜索 |
| `update(archive_unit_id, **kwargs)` | 更新 |
| `delete(archive_unit_id)` | 删除 |
| `compress(**kwargs)` | 域级本地压缩 |

### `api.session`

| 方法 | 说明 |
| --- | --- |
| `create(**kwargs)` | 创建会话 |
| `get(session_id)` | 获取会话 |
| `append(session_id, role, content, **kwargs)` | 追加 turn，并可自动抽取记忆和压缩 |
| `compress(session_id, **kwargs)` | 本地压缩 session context |
| `promote(session_id, **kwargs)` | 短期记忆晋升长期 |
| `health(session_id)` | 返回 session 健康信息 |
| `prune(session_id)` | 清理历史 snapshot |
| `archive(session_id, **kwargs)` | 归档会话 |
| `govern(session_id, **kwargs)` | 运行治理流程 |
| `reflect(session_id, **kwargs)` | 调 `reflection.session(...)` |

### `api.execution`

| 方法 | 说明 |
| --- | --- |
| `start_run(user_id=None, goal=\"\", **kwargs)` | 创建 run |
| `search(query, **kwargs)` | 搜执行记录 |

### `api.recall`

| 方法 | 说明 |
| --- | --- |
| `query(query, **kwargs)` | 统一召回 |
| `plan(query, **kwargs)` | recall plan |
| `explain(query, **kwargs)` | recall 解释 |
| `compress_text(text, **kwargs)` | 本地文本压缩 |
| `context(query, **kwargs)` | `build_context(...)` 的别名入口 |

### `api.context`

| 方法 | 说明 |
| --- | --- |
| `build(query, **kwargs)` | 构建 prompt context artifact |
| `search(query, **kwargs)` | 搜上下文产物 |
| `get(artifact_id, **kwargs)` | 获取 artifact |
| `list(**kwargs)` | 列表 |

### `api.handoff`

| 方法 | 说明 |
| --- | --- |
| `build(target_agent_id, **kwargs)` | 生成 handoff pack |
| `search(query, **kwargs)` | 搜 handoff pack |
| `get(handoff_id, **kwargs)` | 获取 handoff |
| `list(**kwargs)` | 列表 |

### `api.reflection`

| 方法 | 说明 |
| --- | --- |
| `session(session_id, **kwargs)` | 会话反思 |
| `run(run_id, **kwargs)` | run 反思 |
| `search(query, **kwargs)` | 搜 reflection memory |
| `get(reflection_id, **kwargs)` | 获取 reflection |
| `list(**kwargs)` | 列表 |

### `api.acl`

| 方法 | 说明 |
| --- | --- |
| `get(rule_id, **kwargs)` | 获取 ACL 规则 |
| `list(**kwargs)` | 列表 |
| `grant(**kwargs)` | 授权 |
| `revoke(rule_id=None, **kwargs)` | 撤销 |

## 5. 平台事件 API

默认 `memory.events` 对外提供：

| 方法 | 说明 |
| --- | --- |
| `on_turn_end(**payload)` | turn 结束后可自动压缩 / recall / build context |
| `on_agent_end(**payload)` | agent 结束后可自动压缩 / context / reflection |
| `on_handoff(**payload)` | 生成 handoff，并可附带 context |
| `on_session_close(session_id, **payload)` | 关闭 session，并可压缩 / reflection / prune / archive |

这些方法适合挂在协同平台的 runtime lifecycle hooks 上。

## 6. 平台 LLM 压缩入口

只有下面这些高级语义压缩入口支持 `use_platform_llm=True`：

- `api.context.build(...)`
- `api.handoff.build(...)`
- `api.reflection.session(...)`
- `api.reflection.run(...)`

语义：

- 若已绑定平台 LLM 插件，则优先走平台压缩
- 若平台插件异常或缺失，则回退本地压缩
- job 状态会区分 `completed` 和 `degraded`

## 7. ACL 语义

当前资源类型覆盖：

- `memory`
- `knowledge`
- `skill`
- `archive`
- `session`
- `context`
- `handoff`
- `reflection`
- `all`

权限语义：

- `read`
- `write`
- `manage`

当前代码已把 `write / manage` 校验下沉到更多修改型接口，不再只停留在单纯的 memory id 前置校验。

## 8. 能力自检

`memory.describe_capabilities()` 当前返回：

- `core`
- `platform`
- `embeddings`
- `vector_index`
- `graph_store`
- `algorithms`
- `mcp`

其中 `platform` 会标出：

- 当前注册的平台 LLM 插件列表
- 当前配置的 `platform_llm_plugin`
- 当前激活的 provider / model
- 当前平台事件适配器名称
