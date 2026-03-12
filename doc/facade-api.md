# AIMemory Facade API

本文档聚焦 `AIMemory` / `ScopedAIMemory` / `AsyncAIMemory` 这组对外主入口。

如果你只想接一个 API 层，优先看这份文档。

## 1.1 推荐的收敛调用方式

当前推荐优先使用分组入口：

- `memory.api.long_term.*`
- `memory.api.short_term.*`
- `memory.api.knowledge.*`
- `memory.api.skill.*`
- `memory.api.archive.*`
- `memory.api.session.*`
- `memory.api.recall.*`

其中 `ScopedAIMemory` 对应 `scoped.api.*`。

详细参数、返回结构与调用示例请直接看 `doc/API_REFERENCE.md`。
本文件以下内容更适合作为底层实现说明，不再代表推荐对外接口面。

## 1. 什么时候用 Facade

推荐直接使用 Facade 的场景：

- 你要接的是业务应用，而不是底层存储框架
- 你需要统一写入记忆、知识、技能、归档
- 你希望直接做跨域查询
- 你要适配团队多智能体协同平台

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

`AIMemory(config=None)` 中最常用的配置项：

| 配置项 | 说明 |
| --- | --- |
| `root_dir` | 所有本地数据根目录 |
| `workspace_id` / `team_id` / `project_id` | 团队协同作用域默认值 |
| `index_backend` | 向量后端名 |
| `graph_backend` | 图后端名 |
| `providers` | LiteLLM 风格 provider 配置 |
| `embeddings` | 嵌入配置 |
| `memory_policy` | 压缩 / 检索 / 去重策略 |

---

### 2.2 记忆写入 API

#### `add(messages, **kwargs)`

从消息列表中自动抽取候选记忆并写入。

适合：

- 从完整会话片段做智能提取
- 不想手写每条记忆

常见参数：

| 参数 | 说明 |
| --- | --- |
| `messages` | 消息列表或单条消息 |
| `user_id` | 用户 ID |
| `session_id` | 会话 ID |
| `owner_agent_id` | 记忆所有者 agent |
| `subject_type` / `subject_id` | 主体信息 |
| `interaction_type` | 交互类型 |
| `long_term` | 是否直接入长期记忆 |
| `infer` | 是否启用蒸馏式抽取 |
| `memory_type` | 记忆类型 |

#### `remember_long_term(text, **kwargs)`

直接写长期记忆。

#### `remember_short_term(text, **kwargs)`

直接写短期记忆。

#### `memory_store(text, **kwargs)`

统一存储入口，内部根据 `long_term` 决定写入长短期域。

---

### 2.3 记忆查询与维护 API

#### `memory_search(query, **kwargs)`

只查记忆域。

常见参数：

| 参数 | 说明 |
| --- | --- |
| `query` | 查询文本 |
| `user_id` | 用户 ID |
| `owner_agent_id` | agent 作用域 |
| `subject_type` / `subject_id` | 主体范围 |
| `interaction_type` | 交互类型 |
| `session_id` | 会话 ID |
| `scope` | `all` / `session` / `long-term` |
| `limit` | 返回条数 |
| `threshold` | 最小得分阈值 |

#### `memory_list(**kwargs)`

列出符合范围的记忆记录。

#### `memory_get(memory_id)`

读取单条记忆。

#### `update(memory_id, **kwargs)`

更新记忆文本、重要度、状态、元数据。

#### `delete(memory_id)`

删除单条记忆并清理索引。

#### `memory_forget(...)`

支持：

- 按 `memory_id` 删除
- 按查询结果批量删除

#### `history(memory_id)`

查看记忆事件历史，例如：

- `ADD`
- `MERGE`
- `DUPLICATE_TOUCH`
- `UPDATE`
- `DELETE`
- `ARCHIVE`

---

### 2.4 会话与上下文 API

#### `create_session(**kwargs)`

创建会话。

最常用参数：

| 参数 | 说明 |
| --- | --- |
| `user_id` | 用户 ID |
| `owner_agent_id` | 拥有该会话的 agent |
| `subject_type` / `subject_id` | 会话主体 |
| `interaction_type` | `human_agent` / `agent_agent` |
| `title` | 标题 |
| `ttl_seconds` | TTL |
| `metadata` | 附加信息 |

#### `append_turn(session_id, role, content, **kwargs)`

向会话追加一轮消息。

额外支持：

- 参与者 ID
- speaker / target 类型与外部 ID
- `turn_type`
- `salience_score`
- `run_id`

#### `compress_session_context(session_id, **kwargs)`

生成 working memory snapshot，压缩旧轮次上下文。

#### `promote_session_memories(session_id, **kwargs)`

从会话短期记忆中筛选高价值内容，晋升到长期记忆。

#### `session_health(session_id)`

查看当前会话状态，例如：

- turn 数量
- snapshot 情况
- 最近更新时间

#### `get_snapshot(snapshot_id)`

读取单个压缩快照。

#### `prune_session_snapshots(session_id)`

删除旧快照，保留最近若干条。

#### `govern_session(session_id, **kwargs)`

组合治理入口，会同时尝试：

- 健康检查
- 压缩
- 晋升
- snapshot 清理

---

### 2.5 知识库 API

#### `ingest_document(title, text, **kwargs)`

写入知识文档。

支持范围：

- `user_id`
- `owner_agent_id`
- `subject_type` / `subject_id`
- `source_name` / `source_type`
- `uri`
- `kb_namespace`
- `chunk_size`
- `chunk_overlap`

写入后会自动：

- 建立 `documents`
- 建立 `document_versions`
- 建立 `document_chunks`
- 建立 `knowledge_chunk_index`

#### `ingest_knowledge(title, text, **kwargs)`

`ingest_document` 的别名。

#### `get_document(document_id)`

返回：

- 文档元数据
- 版本列表
- chunk 列表

#### `search_knowledge(query, **kwargs)`

在知识库范围做检索。

---

### 2.6 技能 API

#### `save_skill(name, description, **kwargs)`

保存或更新技能。

支持内容：

- `version`
- `prompt_template`
- `workflow`
- `schema`
- `tools`
- `tests`
- `topics`
- `metadata`

#### `register_skill(name, description, **kwargs)`

`save_skill` 的别名。

#### `get_skill(skill_id)`

读取完整技能对象，包括版本。

#### `list_skills(status=None)`

按状态列出技能。

#### `search_skills(query, **kwargs)`

在技能索引中搜索。

---

### 2.7 归档 API

#### `archive_memory(memory_id, **kwargs)`

把单条记忆归档成摘要 + 对象存储 payload。

#### `archive_session(session_id, **kwargs)`

把整个会话归档。

返回通常包括：

- `archive`
- `compression`

#### `get_archive_unit(archive_unit_id)`

读取归档单元及其摘要列表。

#### `search_archive(query, **kwargs)`

在归档摘要上做检索。

---

### 2.8 执行过程 API

#### `start_run(user_id=None, goal="", **kwargs)`

创建执行 run。

适合：

- 记录 Agent 任务链
- 保存工具调用与观察

#### `search_execution(query, **kwargs)`

搜索 run / observation 等执行记录。

---

### 2.9 统一查询 API

#### `query(query, **kwargs)`

这是最推荐的统一召回入口。

可跨域联合搜索：

- `memory`
- `interaction`
- `knowledge`
- `skill`
- `archive`
- `execution`

常用参数：

| 参数 | 说明 |
| --- | --- |
| `query` | 查询文本 |
| `domains` | 限定域列表 |
| `limit` | 返回条数 |
| `threshold` | 最小分数 |
| `filters` | 额外结果过滤 |
| `owner_agent_id` | agent 作用域 |
| `subject_type` / `subject_id` | 主体作用域 |
| `workspace_id` / `team_id` / `project_id` | 团队作用域 |
| `namespace_key` | 手动指定 namespace |

#### `explain_recall(query, **kwargs)`

在查询结果基础上，补充当前策略信息：

- 向量后端
- 图后端
- rerank 参数
- scan limit

---

### 2.10 系统能力 API

#### `describe_capabilities()`

返回：

- `core`
- `embeddings`
- `vector_index`
- `graph_store`
- `algorithms`
- `mcp`

#### `storage_layout(**scope_kwargs)`

返回当前作用域下的存储布局。

适合：

- 调试 namespace
- 平台可观测性
- 校验不同域的对象前缀

#### `project(limit=None)`

重建 / 投影索引。

#### `litellm_config()`

返回 LiteLLM 风格 provider 配置。

---

## 3. `ScopedAIMemory`

### 3.1 为什么存在

当你在固定作用域下反复调用 Facade 时，不想每次都传：

- `owner_agent_id`
- `subject_type`
- `subject_id`
- `interaction_type`
- `workspace_id`
- `team_id`
- `project_id`

这时应该用：

```python
scoped = memory.scoped(
    workspace_id="ws.alpha",
    team_id="team.memory",
    owner_agent_id="agent.planner",
    subject_type="agent",
    subject_id="agent.executor",
    interaction_type="agent_agent",
)
```

### 3.2 常用方法

`ScopedAIMemory` 复用了主 Facade 的核心方法：

- `add`
- `create_session`
- `append_turn`
- `remember_long_term`
- `remember_short_term`
- `memory_search`
- `query`
- `ingest_document`
- `search_knowledge`
- `save_skill`
- `search_skills`
- `archive_session`
- `search_archive`
- `search_interaction`
- `search_execution`
- `compress_session_context`
- `storage_layout`
- `create_mcp_adapter`

### 3.3 继续叠加作用域

可以用 `using(...)` 进一步细化：

```python
executor_scope = scoped.using(subject_id="agent.executor.v2")
```

---

## 4. `AsyncAIMemory`

`AsyncAIMemory` 是 `AIMemory` 的异步包装版本。

适合：

- 异步 web 服务
- 异步 Agent runtime
- 需要 `await` 风格调用的应用层

使用建议：

- 业务逻辑尽量仍按同步 Facade 思维组织
- 仅在接入层换成 `AsyncAIMemory`

---

## 5. 推荐实践

### 实践 1：团队场景优先用 scoped facade

这能显著降低跨团队、跨 workspace 误查风险。

### 实践 2：统一召回优先用 `query()`

如果不是只查某一个域，优先使用 `query()` 而不是自己拼多次搜索。

### 实践 3：记忆与知识分开写

- 记忆存“跟当前主体长期相关的事实”
- 知识库存“文档化、块化内容”

### 实践 4：技能单独维护

技能更偏：

- 方法
- 流程
- Prompt 模板
- 工具组合

### 实践 5：定期压缩与归档

这样能持续降低上下文成本，同时保留可检索线索。
