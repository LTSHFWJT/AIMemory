# AIMemory API Reference

本文档是 `AIMemory` 当前唯一建议使用的对外调用手册。

## 1. 对外接口约定

`AIMemory` 当前对外只推荐两层接口：

- 根对象：`AIMemory` / `ScopedAIMemory` / `AsyncAIMemory`
- 分组 API：`memory.api.*` / `scoped.api.*` / `await async_memory.api.*`

统一分组如下：

| 分组 | 适用内容 | 调用范围 |
| --- | --- | --- |
| `api.long_term` | 跨会话稳定记忆 | 用户偏好、稳定事实、长期经验 |
| `api.short_term` | 会话内短期记忆 | 当前会话的重要上下文 |
| `api.knowledge` | 知识库 | 文档、规则、资源说明 |
| `api.skill` | 技能库 | 可复用 prompt、工作流、工具绑定 |
| `api.archive` | 归档记忆 | 低频但长期保留的摘要与 payload |
| `api.session` | 会话管理 | session、turn、压缩、晋升、归档 |
| `api.recall` | 统一召回 | 跨域查询与召回解释 |
| `api.execution` | 执行记录 | run 与执行搜索 |

不再把平铺旧方法作为对外契约。

## 2. 最小调用示例

```python
from aimemory import AIMemory

memory = AIMemory({"root_dir": ".aimemory-demo"})

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
    "遇到不确定信息时先查知识库，再决定是否访问外部资源。",
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

## 3. 作用域参数

以下参数几乎可用于所有 `api.*` 写入、列表、搜索与归档方法：

| 参数 | 类型 | 含义 | 常见取值 |
| --- | --- | --- | --- |
| `user_id` | `str` | 当前用户 ID | 业务侧用户主键 |
| `owner_agent_id` | `str` | 记忆/技能/会话的拥有者 agent | 如 `agent.assistant` |
| `subject_type` | `str` | 当前主体类型 | `human` / `agent` |
| `subject_id` | `str` | 当前主体 ID | 用户 ID 或 agent ID |
| `interaction_type` | `str` | 交互类型 | `human_agent` / `agent_agent` |
| `platform_id` | `str` | 平台维度 | 多平台隔离时使用 |
| `workspace_id` | `str` | 工作区维度 | 如 `ws.alpha` |
| `team_id` | `str` | 团队维度 | 如 `team.memory` |
| `project_id` | `str` | 项目维度 | 如 `mission-42` |
| `namespace_key` | `str` | 手动指定命名空间 | 不手动传时会自动推导 |

推荐原则：

- 人和 agent 的长期偏好、画像、事实，用 `subject_type="human"` 或 `subject_type="agent"` 明确区分
- 团队平台下，优先固定 `workspace_id` / `team_id` / `project_id`
- 不要把不同主体写进同一组 scope

### 3.1 严格枚举值

以下字段在代码中有明确枚举定义，文档按固定值说明：

| 字段 | 固定值 |
| --- | --- |
| `memory_type` | `semantic`、`episodic`、`procedural`、`profile`、`preference`、`relationship_summary` |
| `skill.status` | `draft`、`active`、`deprecated`、`archived` |
| `run.status` | `pending`、`running`、`completed`、`failed`、`cancelled` |
| `task.status` | `pending`、`running`、`completed`、`failed`、`skipped` |
| `session.status` | `active`、`idle`、`archived`、`closed` |
| `archive` 内置域值 | `session`、`memory`、`document`、`run` |
| `knowledge` 内置来源类型 | `manual`、`directory`、`url`、`git` |

### 3.2 推荐约定值

以下字段在实现里不是强制枚举，但主流程明显依赖这些约定值，建议严格按下列值传：

| 字段 | 推荐值 | 说明 |
| --- | --- | --- |
| `subject_type` | `human`、`agent` | 会影响主体推断、参与者绑定与隔离逻辑 |
| `interaction_type` | `human_agent`、`agent_agent` | 会影响默认作用域与检索行为 |
| `speaker_type` / `target_type` | `human`、`agent` | 会影响会话参与者自动绑定 |
| `role` | `user`、`human`、`assistant`、`peer_agent`、`system`、`tool` | 其中 `user`/`human`/`peer_agent` 会触发不同的默认参与者推断 |
| `domains` | `memory`、`interaction`、`knowledge`、`skill`、`archive`、`execution` | 统一召回支持的域列表 |

补充说明：

- `turn_type` 不是固定枚举，当前默认值是 `message`，可按业务扩展
- `knowledge.source_type` 与 `archive.domain` 虽有内置值，但当前实现也允许自定义字符串
- `knowledge.add()` 入口默认 `source_type="inline"`，这是 facade 层的默认写入值，属于可扩展字符串

## 4. 通用可选参数

| 参数 | 适用方法 | 含义 | 推荐范围 |
| --- | --- | --- | --- |
| `limit` | list/search/query | 返回条数 | `1` 到 `200` |
| `offset` | list | 偏移量 | `>= 0` |
| `threshold` | search/query/promote | 结果阈值 | `0.0` 到 `1.0` |
| `importance` | memory add/update | 记忆重要度 | 推荐 `0.0` 到 `1.0` |
| `metadata` | 大多数写入/update | 附加结构化信息 | `dict` |
| `filters` | list/search/query | 附加过滤条件 | `dict` |
| `global_scope` | knowledge/archive add | 是否写入全局域 | `True` / `False` |
| `include_global` | knowledge/archive list/search | 是否包含全局内容 | `True` / `False` |
| `include_generated` | memory list/search | 是否包含自动生成摘要记忆 | `True` / `False` |
| `include_inactive` | memory list | 是否包含非 active 记录 | `True` / `False` |
| `force` | compress | 是否强制压缩 | `True` / `False` |
| `budget_chars` | session/archive compress | 压缩预算字符数 | `> 0` |
| `status` | knowledge/skill/run update/list | 状态字段 | skill/run 用固定枚举；knowledge 当前默认 `active`，允许扩展字符串 |

## 5. 根对象

### 5.1 `AIMemory`

创建同步主入口：

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

常用根对象方法：

| 方法 | 说明 |
| --- | --- |
| `api` | 当前唯一推荐对外调用入口 |
| `scoped(**scope_kwargs)` | 生成带默认作用域的 `ScopedAIMemory` |
| `create_mcp_adapter(scope=None)` | 创建 MCP 适配器 |
| `storage_layout(**scope_kwargs)` | 查看当前作用域的数据布局 |
| `describe_capabilities()` | 查看当前能力清单 |
| `litellm_config()` | 导出 LiteLLM 风格配置 |
| `register_domain_compressor(domain, compressor)` | 自定义压缩器 |
| `unregister_domain_compressor(domain)` | 移除自定义压缩器 |
| `project(limit=None)` | 重建索引 |
| `close()` | 关闭数据库连接 |

### 5.2 `ScopedAIMemory`

适合固定团队/项目/主体作用域：

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
```

`ScopedAIMemory` 公开方法：

| 方法 | 说明 |
| --- | --- |
| `api` | 自动携带默认 scope 的分组 API |
| `using(**scope_overrides)` | 生成新的 scoped 句柄 |
| `scope_dict()` | 返回当前作用域 |
| `storage_layout()` | 查看当前 scoped 的存储布局 |
| `create_mcp_adapter()` | 创建带默认作用域的 MCP adapter |

### 5.3 `AsyncAIMemory`

异步入口使用方式：

```python
from aimemory import AsyncAIMemory

memory = AsyncAIMemory({"root_dir": ".aimemory-async"})
await memory.api.long_term.add("异步入口也使用同一组 api。")
await memory.close()
```

## 6. `api.long_term`

长期记忆用于跨会话沉淀稳定信息。

| 方法 | 用途 | 主要参数 |
| --- | --- | --- |
| `add(text, **kwargs)` | 写入长期记忆 | `text`，可选 `memory_type`、`importance`、`metadata`、作用域参数 |
| `get(memory_id)` | 获取单条长期记忆 | `memory_id` |
| `list(**kwargs)` | 列出长期记忆 | `include_generated`、`include_inactive`、`limit`、`offset`、`filters`、作用域参数 |
| `search(query, **kwargs)` | 搜索长期记忆 | `query`、`limit`、`threshold`、`include_generated`、作用域参数 |
| `update(memory_id, **kwargs)` | 更新长期记忆 | `text`、`importance`、`metadata`、`status` |
| `delete(memory_id)` | 删除长期记忆 | `memory_id` |
| `compress(**kwargs)` | 压缩长期记忆 | `force`、`limit`、作用域参数 |

`memory_type` 固定枚举值：

- `semantic`
- `episodic`
- `procedural`
- `profile`
- `preference`
- `relationship_summary`

## 7. `api.short_term`

短期记忆用于当前会话窗口内的重要上下文。

| 方法 | 用途 | 主要参数 |
| --- | --- | --- |
| `add(text, **kwargs)` | 写入短期记忆 | `text`，建议同时传 `session_id` |
| `get(memory_id)` | 获取单条短期记忆 | `memory_id` |
| `list(**kwargs)` | 列出短期记忆 | `session_id`、`limit`、`offset`、`include_generated`、`filters` |
| `search(query, **kwargs)` | 搜索短期记忆 | `query`、`session_id`、`limit`、`threshold` |
| `update(memory_id, **kwargs)` | 更新短期记忆 | `text`、`importance`、`metadata`、`status` |
| `delete(memory_id)` | 删除短期记忆 | `memory_id` |
| `compress(**kwargs)` | 压缩短期记忆 | `session_id`、`force`、`limit` |

推荐：

- 只在当前任务窗口内有价值的信息写入短期记忆
- 如果信息跨会话仍有价值，用 `api.session.promote()` 晋升到长期记忆

## 8. `api.knowledge`

知识库用于“先查证据，再回答”。

| 方法 | 用途 | 主要参数 |
| --- | --- | --- |
| `add(title, text, **kwargs)` | 写入知识库文档 | `title`、`text`、`source_name`、`source_type`、`uri`、`kb_namespace`、`global_scope`、`metadata`、作用域参数 |
| `get(document_id)` | 获取完整文档 | `document_id` |
| `list(**kwargs)` | 列出文档 | `include_global`、`limit`、`offset`、`status`、作用域参数 |
| `search(query, **kwargs)` | 搜索文档与切块 | `query`、`include_global`、`limit`、`threshold`、作用域参数 |
| `update(document_id, **kwargs)` | 更新文档 | `title`、`text`、`status`、`metadata`、`kb_namespace`、`global_scope`、作用域参数 |
| `delete(document_id)` | 删除文档 | `document_id` |

`source_type` 内置值：

- `manual`
- `directory`
- `url`
- `git`

补充：

- `api.knowledge.add()` 的默认值是 `inline`
- 除内置值外，也允许传业务自定义字符串

## 9. `api.skill`

技能库用于在开始执行前先查“已有技能”。

| 方法 | 用途 | 主要参数 |
| --- | --- | --- |
| `add(name, description, **kwargs)` | 新增技能 | `name`、`description`、`prompt_template`、`workflow`、`schema`、`tools`、`tests`、`topics`、`skill_markdown`、`files`、`references`、`scripts`、`assets`、`metadata`、`status`、作用域参数 |
| `get(skill_id)` | 获取完整技能内容 | `skill_id` |
| `list(**kwargs)` | 列出技能 metadata | `owner_agent_id`、`subject_type`、`subject_id`、`status`、`limit`、`offset`、作用域参数 |
| `search(query, **kwargs)` | 搜索技能 | `query`、`limit`、`threshold`、作用域参数；会联合 skill 主体、执行上下文和 `references/` 文本命中 |
| `search_references(query, **kwargs)` | 搜索 reference 分块 | `query`、`skill_id`、`path_prefix`、`limit`、`threshold`、作用域参数 |
| `refresh_execution_context(skill_id, **kwargs)` | 刷新 skill 常用执行上下文 | `skill_id`、`path_prefix`、`budget_chars`、`max_sentences`、`max_highlights` |
| `update(skill_id, **kwargs)` | 更新技能当前快照 | `name`、`description`、`prompt_template`、`workflow`、`schema`、`tools`、`tests`、`topics`、`skill_markdown`、`files`、`references`、`scripts`、`assets`、`metadata`、`status`、作用域参数 |
| `delete(skill_id)` | 删除技能 | `skill_id` |

`status` 固定枚举值：

- `draft`
- `active`
- `deprecated`
- `archived`

补充说明：

- skill 现在支持以“本地文件主存储”的方式保存技能包，完整文件清单会随当前快照返回。
- skill 不再暴露 `versions` 列表；`api.skill.get()` 返回 `current_snapshot` 及其展开后的文件、references、scripts、assets、execution_context。
- `SKILL.md` 是主入口；如果未显式传入，会根据 `name/description/prompt_template/workflow` 自动生成。
- `references` 文本会被切块进入辅助检索索引，从而提升 `api.skill.search()` 的召回，但真实文件仍保存在本地对象存储。
- 系统会基于 `references` 自动生成 `execution_context`，作为常用执行上下文随 `api.skill.get()` 返回。

## 10. `api.archive`

归档用于低频、低成本、长期保留。

| 方法 | 用途 | 主要参数 |
| --- | --- | --- |
| `add(summary, **kwargs)` | 手动写入归档记忆 | `summary`、`content`、`source_type`、`domain`、`session_id`、`global_scope`、`metadata`、作用域参数 |
| `get(archive_unit_id)` | 获取归档单元 | `archive_unit_id` |
| `list(**kwargs)` | 列出归档 | `include_global`、`include_generated`、`limit`、`offset`、作用域参数 |
| `search(query, **kwargs)` | 搜索归档摘要 | `query`、`include_global`、`limit`、`threshold`、作用域参数 |
| `update(archive_unit_id, **kwargs)` | 更新归档 | `summary`、`content`、`source_type`、`domain`、`metadata`、作用域参数 |
| `delete(archive_unit_id)` | 删除归档 | `archive_unit_id` |
| `compress(**kwargs)` | 压缩归档集合 | `include_global`、`force`、`limit`、作用域参数 |

适合归档的内容：

- 已完成任务的长会话摘要
- 低频但不能丢失的规则/经验
- 需要低成本唤起的历史结论

`domain` 补充说明：

- 系统内置归档域值是 `session`、`memory`、`document`、`run`
- `api.archive.add()` 的默认值是 `manual`
- 当前实现允许自定义字符串

## 11. `api.session`

会话 API 负责短期上下文与交互事件。

| 方法 | 用途 | 主要参数 |
| --- | --- | --- |
| `create(**kwargs)` | 创建 session | `user_id`、`session_id`、`title`、`ttl_seconds`、`metadata`、作用域参数 |
| `get(session_id)` | 获取 session | `session_id` |
| `append(session_id, role, content, **kwargs)` | 追加 turn | `session_id`、`role`、`content`，可选 `run_id`、`name`、`metadata`、`tokens_in`、`tokens_out`、`speaker_participant_id`、`target_participant_id`、`speaker_type`、`speaker_external_id`、`target_type`、`target_external_id`、`turn_type`、`salience_score` |
| `compress(session_id, **kwargs)` | 压缩上下文 | `budget_chars`、`preserve_recent_turns`、`run_id` |
| `promote(session_id, **kwargs)` | 晋升短期记忆为长期记忆 | `threshold`、`memory_type` |
| `health(session_id)` | 查看会话健康情况 | `session_id` |
| `prune(session_id, **kwargs)` | 清理旧 snapshot | `keep_recent` |
| `archive(session_id, **kwargs)` | 归档整个会话 | `budget_chars`、`metadata` |
| `govern(session_id, **kwargs)` | 一次执行健康检查、压缩、晋升、清理 | 会透传给 `compress/promote/prune` |

补充说明：

- `subject_type` 推荐固定传 `human` 或 `agent`
- `interaction_type` 推荐固定传 `human_agent` 或 `agent_agent`
- `role` 推荐使用 `user`、`human`、`assistant`、`peer_agent`、`system`、`tool`
- `speaker_type` / `target_type` 推荐固定传 `human` 或 `agent`
- `turn_type` 默认 `message`，当前不是固定枚举
- `ttl_seconds` 建议传正整数

## 12. `api.recall`

统一召回用于跨域找证据、记忆、技能和归档。

| 方法 | 用途 | 主要参数 |
| --- | --- | --- |
| `query(query, **kwargs)` | 跨域统一召回 | `query`、作用域参数、`session_id`、`run_id`、`domains`、`filters`、`limit`、`threshold` |
| `explain(query, **kwargs)` | 返回路由解释 | `query`、作用域参数、`session_id` |

`domains` 固定可选值：

- `memory`
- `interaction`
- `knowledge`
- `skill`
- `archive`
- `execution`

推荐：

- 先用 `api.skill.search()` 看是否已有技能
- 遇到事实不确定时优先 `api.knowledge.search()`
- 需要统一答案上下文时用 `api.recall.query()`

## 13. `api.execution`

执行记录用于 run 级留痕与回查。

| 方法 | 用途 | 主要参数 |
| --- | --- | --- |
| `start_run(user_id=None, goal="", **kwargs)` | 创建 run | `user_id`、`goal`、作用域参数、`session_id`、`metadata`、`status` |
| `search(query, **kwargs)` | 搜索执行记录 | `query`、`user_id`、`owner_agent_id`、`session_id`、团队作用域参数、`limit`、`threshold`、`filters` |

`RunStatus` 固定枚举值：

- `pending`
- `running`
- `completed`
- `failed`
- `cancelled`

调用 `api.execution.start_run(..., status=...)` 时，建议严格使用以上固定值。

`TaskStatus` 固定枚举值：

- `pending`
- `running`
- `completed`
- `failed`
- `skipped`

## 14. MCP Adapter

通过 `create_mcp_adapter()` 暴露工具给外部 Agent：

```python
adapter = memory.create_mcp_adapter(
    scope={
        "workspace_id": "ws.alpha",
        "team_id": "team.memory",
        "owner_agent_id": "agent.planner",
    }
)

result = adapter.call_tool(
    "recall_query",
    {
        "query": "最近的执行偏好",
        "context_scope": {
            "subject_type": "agent",
            "subject_id": "agent.executor",
            "interaction_type": "agent_agent",
        },
    },
)
```

当前推荐 MCP 工具名：

- `recall_query`
- `long_term_memory_*`
- `short_term_memory_*`
- `knowledge_document_*`
- `skill_*`
- `archive_memory_*`
- `session_*`
- `aimemory_manifest`

## 15. 常见返回结构

| 返回结构 | 典型方法 | 说明 |
| --- | --- | --- |
| `{"id": ..., ...}` | add/get/update | 单条实体 |
| `{"results": [...], "count": n, "limit": ..., "offset": ...}` | list/search | 列表型结果 |
| `{"snapshot": ..., "compressed": bool}` | `api.session.compress()` | 压缩结果 |
| `{"archive": ..., "memory": ...}` | `api.session.archive()` / `archive_memory()` | 归档结果 |
| `{"results": [...], "query": ...}` | `api.recall.query()` | 统一召回结果 |

## 16. 推荐接入顺序

1. 初始化 `AIMemory`
2. 固定 scope 时优先 `memory.scoped(...)`
3. 用 `api.skill.search()` / `api.knowledge.search()` 做执行前准备
4. 用 `api.session.*` 管理会话
5. 用 `api.long_term` / `api.short_term` 管理记忆
6. 用 `api.recall.query()` 做统一召回
7. 用 `api.archive` 或 `api.session.archive()` 做冷存储
8. 需要外部 Agent 工具化时接 `create_mcp_adapter()`
