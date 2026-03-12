# AIMemory Facade API

本文档只保留 `AIMemory` 当前推荐的 Facade 用法。

如果你只关心怎么接入，请看这份；如果你需要完整参数与返回结构，请看 `doc/API_REFERENCE.md`。

涉及固定枚举值与推荐约定值时，以 `doc/API_REFERENCE.md` 中的“作用域参数 / 严格枚举值 / 推荐约定值”章节为准。

## 1. 推荐接口面

当前只推荐使用以下入口：

- `AIMemory.api.*`
- `ScopedAIMemory.api.*`
- `AsyncAIMemory.api.*`

统一分组如下：

- `api.long_term`
- `api.short_term`
- `api.knowledge`
- `api.skill`
- `api.archive`
- `api.session`
- `api.recall`
- `api.execution`

## 2. `AIMemory`

### 2.1 初始化

```python
from aimemory import AIMemory

memory = AIMemory(
    {
        "root_dir": ".aimemory",
        "workspace_id": "ws.alpha",
        "team_id": "team.memory",
    }
)
```

最常用配置：

| 配置项 | 说明 |
| --- | --- |
| `root_dir` | 本地数据根目录 |
| `workspace_id` / `team_id` / `project_id` | 团队作用域默认值 |
| `index_backend` | 向量后端 |
| `graph_backend` | 图后端 |
| `providers` | LiteLLM 风格配置 |
| `embeddings` | 嵌入配置 |
| `memory_policy` | 压缩、检索、去重策略 |

### 2.2 最小示例

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as memory:
    session = memory.api.session.create(
        user_id="user-1",
        owner_agent_id="agent.assistant",
        subject_type="human",
        subject_id="user-1",
        interaction_type="human_agent",
        title="demo",
    )

    memory.api.session.append(
        session["id"],
        "user",
        "我喜欢简洁、分点、低 token 的回答。",
    )

    memory.api.long_term.add(
        "用户偏好简洁分点输出。",
        owner_agent_id="agent.assistant",
        subject_type="human",
        subject_id="user-1",
        interaction_type="human_agent",
        memory_type="preference",
        importance=0.9,
    )

    memory.api.knowledge.add(
        "平台规则",
        "先查知识库，再决定是否访问外部资源。",
        global_scope=True,
    )

    result = memory.api.recall.query(
        "用户喜欢什么输出风格？",
        owner_agent_id="agent.assistant",
        subject_type="human",
        subject_id="user-1",
        session_id=session["id"],
        domains=["memory", "knowledge"],
        limit=8,
    )

    print(result["results"])
```

### 2.3 根对象常用方法

| 方法 | 说明 |
| --- | --- |
| `api` | 当前唯一推荐调用入口 |
| `scoped(**scope_kwargs)` | 创建固定作用域句柄 |
| `create_mcp_adapter(scope=None)` | 创建 MCP 适配器 |
| `storage_layout(**scope_kwargs)` | 查看当前存储布局 |
| `describe_capabilities()` | 查看能力清单 |
| `litellm_config()` | 导出 LiteLLM 风格配置 |
| `register_domain_compressor(domain, compressor)` | 注册压缩器 |
| `project(limit=None)` | 重建索引 |
| `close()` | 关闭实例 |

## 3. 分组 API

### 3.1 记忆

| 分组 | 适用场景 |
| --- | --- |
| `api.long_term` | 跨会话稳定记忆 |
| `api.short_term` | 会话内短期上下文 |

常用方法：

- `add()`
- `get()`
- `list()`
- `search()`
- `update()`
- `delete()`
- `compress()`

推荐原则：

- 长期记忆写稳定偏好、事实、长期经验
- 短期记忆写当前会话中的关键上下文

### 3.2 知识、技能、归档

| 分组 | 适用场景 |
| --- | --- |
| `api.knowledge` | 先查证据再回答 |
| `api.skill` | 开始执行前先查已有技能 |
| `api.archive` | 低频但长期保留的冷数据 |

这三个分组统一使用以下方法形态：

- `add()`
- `get()`
- `list()`
- `search()`
- `update()`
- `delete()`

其中 `api.archive` 额外提供：

- `compress()`

### 3.3 会话

`api.session` 用于管理对话上下文与会话治理。

常用方法：

- `create()`
- `get()`
- `append()`
- `compress()`
- `promote()`
- `health()`
- `prune()`
- `archive()`
- `govern()`

推荐做法：

- 所有对话消息先写 `api.session.append()`
- 会话变长后调用 `api.session.compress()`
- 会话结束后根据需要调用 `api.session.promote()` 或 `api.session.archive()`

### 3.4 统一召回

`api.recall.query()` 是当前最推荐的统一读接口。

适合：

- 同时查记忆、知识、技能、归档
- 让 Agent 在执行前先拼好证据上下文
- 避免业务层自己做多次检索再手动合并

可选 `domains`：

- `memory`
- `interaction`
- `knowledge`
- `skill`
- `archive`
- `execution`

`api.recall.explain()` 用于查看召回策略和路由解释。

### 3.5 执行记录

`api.execution` 目前主要提供：

- `start_run()`
- `search()`

适合保存 run 级目标与后续回查。

## 4. `ScopedAIMemory`

当你在固定 scope 下频繁调用时，优先使用 `scoped()`：

```python
scoped = memory.scoped(
    workspace_id="ws.alpha",
    team_id="team.memory",
    owner_agent_id="agent.planner",
    subject_type="agent",
    subject_id="agent.executor",
    interaction_type="agent_agent",
)

scoped.api.long_term.add("executor 擅长把长计划压缩成可执行步骤。")
result = scoped.api.recall.query("executor 擅长什么", domains=["memory", "skill"])
```

`ScopedAIMemory` 公开能力：

| 方法 | 说明 |
| --- | --- |
| `api` | 自动携带默认 scope |
| `using(**scope_overrides)` | 基于当前 scope 派生新 scope |
| `scope_dict()` | 返回当前 scope |
| `storage_layout()` | 查看当前 scope 的存储布局 |
| `create_mcp_adapter()` | 创建带默认 scope 的 MCP adapter |

## 5. `AsyncAIMemory`

异步场景直接使用：

```python
from aimemory import AsyncAIMemory

memory = AsyncAIMemory({"root_dir": ".aimemory-async"})
await memory.api.long_term.add("异步入口也使用同一组 Facade API。")
await memory.close()
```

推荐场景：

- 异步 Web 服务
- 异步 Agent Runtime
- 统一用 `await` 风格组织接入层

## 6. MCP Adapter

如果要把能力暴露给上层 Agent，用：

```python
adapter = memory.create_mcp_adapter(
    scope={
        "workspace_id": "ws.alpha",
        "team_id": "team.memory",
        "owner_agent_id": "agent.planner",
    }
)
```

常见工具：

- `recall_query`
- `long_term_memory_*`
- `short_term_memory_*`
- `knowledge_document_*`
- `skill_*`
- `archive_memory_*`
- `session_*`
- `aimemory_manifest`

## 7. 推荐接入顺序

1. 初始化 `AIMemory`
2. 如有固定作用域，先 `memory.scoped(...)`
3. 先查 `api.skill.search()` / `api.knowledge.search()`
4. 用 `api.session.*` 管理会话
5. 用 `api.long_term` / `api.short_term` 管理记忆
6. 用 `api.recall.query()` 做统一召回
7. 用 `api.archive` 或 `api.session.archive()` 做冷存储
8. 需要工具化时接 `create_mcp_adapter()`

## 8. 更多细节

完整参数、返回结构、字段范围说明，请看：

- `doc/API_REFERENCE.md`
