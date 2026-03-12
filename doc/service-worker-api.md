# Service & Worker API

本文档面向高级集成者，介绍 `aimemory/services/*` 与 `aimemory/workers/*`。

如果你只是业务侧接入，优先使用：

- `AIMemory`
- `ScopedAIMemory`
- `AIMemoryMCPAdapter`

Service / Worker 更适合：

- 自定义 runtime 编排
- 更细粒度控制各个存储域
- 本地后台任务治理

## 1. Service 层总览

当前 Service 层包含：

| 服务 | 作用 |
| --- | --- |
| `MemoryService` | 记忆写入、记忆维护、晋升、清理规划 |
| `InteractionService` | 会话、轮次、变量、工具状态、上下文压缩 |
| `KnowledgeService` | 知识源、文档写入、文档读取 |
| `SkillService` | 技能注册、版本激活、技能查询 |
| `ArchiveService` | 记忆 / 会话归档与恢复 |
| `ExecutionService` | run / task / step / tool call / observation |
| `RetrievalService` | 各域搜索与统一召回 |
| `ProjectionService` | 延迟投影与索引队列 |

说明：

- Service 层更接近领域能力
- 与最新团队 scope 能力相比，Facade 层封装更完整
- 如果你是平台方，优先建议从 Facade 往下调，而不是直接拼 Service

## 2. `MemoryService`

### 核心方法

| 方法 | 说明 |
| --- | --- |
| `set_intelligence_pipeline(pipeline)` | 注入自定义智能提取管线 |
| `add(messages)` | 批量抽取并写入记忆 |
| `remember(text)` | 写单条记忆 |
| `get(memory_id)` | 获取单条记忆 |
| `get_all(...)` | 列出记忆 |
| `promote_session_memories(session_id, ...)` | 从会话中晋升长期记忆 |
| `plan_low_value_cleanup()` | 规划低价值记忆清理 |
| `update(memory_id, ...)` | 更新记忆 |
| `delete(memory_id)` | 删除记忆 |
| `delete_by_query(query)` | 按查询删除 |
| `history(memory_id)` | 查看事件历史 |
| `build_scope_context()` | 构建作用域上下文 |

### 适合场景

- 想替换默认提取管线
- 想做更细粒度的记忆维护
- 想单独控制晋升和清理策略

## 3. `InteractionService`

### 核心方法

| 方法 | 说明 |
| --- | --- |
| `create_session(...)` | 创建会话 |
| `get_session(session_id)` | 读取会话 |
| `append_turn(...)` | 写入轮次 |
| `list_turns(session_id, limit=20, offset=0)` | 列出轮次 |
| `upsert_snapshot(...)` | 写 / 更新工作记忆快照 |
| `set_tool_state(...)` | 保存工具状态 |
| `set_variable(session_id, key, value)` | 保存会话变量 |
| `get_context(session_id, limit=12)` | 拉取会话上下文 |
| `compress_session_context(...)` | 压缩会话 |
| `session_health(session_id)` | 会话健康检查 |
| `prune_snapshots(session_id)` | 清理旧快照 |
| `clear_session(session_id)` | 清理会话关联内容 |

### `get_context()` 返回

通常包括：

- `session`
- `turns`
- `snapshot`
- `variables`
- `tool_states`

## 4. `KnowledgeService`

### 核心方法

| 方法 | 说明 |
| --- | --- |
| `create_source(name, source_type, ...)` | 创建知识源 |
| `ingest_text(title, text, ...)` | 写入文档文本 |
| `get_document(document_id)` | 获取文档 |
| `list_documents(...)` | 列出文档 |
| `get_document_text(document_id)` | 读取文档正文 |

### 适合场景

- 需要自己管理知识源
- 需要手动定义版本标签
- 需要批量文档入库流程

## 5. `SkillService`

### 核心方法

| 方法 | 说明 |
| --- | --- |
| `register(name, description, ...)` | 注册技能 |
| `get_skill(skill_id)` | 获取技能 |
| `list_skills(status=None, owner_agent_id=None)` | 列出技能 |
| `activate_version(skill_id, version)` | 激活指定版本 |

### 技能适合承载的内容

- prompt 模板
- workflow
- 工具绑定
- 测试样例
- capability 标签

## 6. `ArchiveService`

### 核心方法

| 方法 | 说明 |
| --- | --- |
| `archive_session(session_id, ...)` | 归档会话 |
| `archive_memory(memory_id, ...)` | 归档单条记忆 |
| `get_archive(archive_unit_id)` | 获取归档信息 |
| `restore_archive(archive_unit_id)` | 从对象存储恢复 payload |

### `restore_archive()` 返回

通常包含：

- `archive`
- `payload`

## 7. `ExecutionService`

### 核心方法

| 方法 | 说明 |
| --- | --- |
| `start_run(...)` | 创建 run |
| `get_run(run_id)` | 获取 run |
| `update_run(run_id, ...)` | 更新 run 状态 |
| `create_task(run_id, title, ...)` | 创建任务 |
| `get_task(task_id)` | 获取任务 |
| `add_task_step(...)` | 增加步骤 |
| `checkpoint(run_id, snapshot, ...)` | 保存 checkpoint |
| `log_tool_call(...)` | 记录工具调用 |
| `add_observation(...)` | 增加观察 |
| `get_run_timeline(run_id)` | 拉取时间线 |

### `get_run_timeline()` 返回

通常包括：

- `run`
- `tasks`
- `steps`
- `checkpoints`
- `tool_calls`
- `observations`

## 8. `RetrievalService`

### 核心方法

| 方法 | 说明 |
| --- | --- |
| `search_memory(query, ...)` | 搜索记忆 |
| `retrieve(query, ...)` | 统一检索入口 |
| `search_interaction(query, ...)` | 搜索交互上下文 |
| `search_knowledge(query, ...)` | 搜索知识库 |
| `search_skills(query, ...)` | 搜索技能 |
| `search_archive(query, ...)` | 搜索归档 |
| `search_execution(query, ...)` | 搜索执行记录 |
| `plan_memory_recall(query)` | 规划召回 |
| `explain_memory_recall(query)` | 解释召回过程 |

### 使用建议

- 平台业务层优先用 `AIMemory.api.recall.query()`
- 如果你在做自定义检索编排，再下沉到 `RetrievalService`

## 9. `ProjectionService`

### 核心方法

| 方法 | 说明 |
| --- | --- |
| `enqueue(topic, entity_type, entity_id, action, payload)` | 加入投影队列 |
| `project_pending(limit)` | 执行待处理投影 |

适合：

- 做异步索引刷新
- 控制重建节奏
- 做批处理投影

## 10. Worker 层总览

当前 Worker：

| Worker | 作用 |
| --- | --- |
| `LowValueMemoryCleanerWorker` | 清理低价值记忆 |
| `SessionCompactionWorker` | 压缩会话上下文 |
| `SessionMemoryPromoterWorker` | 晋升会话记忆 |
| `GovernanceAutomationWorker` | 组合治理 |
| `ProjectorWorker` | 批量执行投影 |

## 11. `LowValueMemoryCleanerWorker`

### 方法

| 方法 | 说明 |
| --- | --- |
| `run_once()` | 执行一次清理 |
| `run_forever(poll_interval)` | 持续轮询执行 |
| `describe_capabilities()` | 输出能力说明 |

### 适合场景

- 定时清理长期无价值记忆
- 控制本地存储膨胀

## 12. `SessionCompactionWorker`

### 方法

| 方法 | 说明 |
| --- | --- |
| `run_once(session_id)` | 压缩一个 session |
| `run_forever(session_ids, poll_interval)` | 周期性压缩多个 session |
| `describe_capabilities()` | 输出能力说明 |

### 适合场景

- 长对话 Agent
- 上下文成本需要持续控制

## 13. `SessionMemoryPromoterWorker`

### 方法

| 方法 | 说明 |
| --- | --- |
| `run_once(session_id)` | 对一个 session 执行晋升 |
| `run_forever(session_ids, poll_interval)` | 周期性晋升多个 session |
| `describe_capabilities()` | 输出能力说明 |

### 适合场景

- 在任务结束后沉淀经验
- 周期性把短期结论升级为长期记忆

## 14. `GovernanceAutomationWorker`

### 方法

| 方法 | 说明 |
| --- | --- |
| `assess_session(session_id)` | 评估会话治理需求 |
| `run_once(session_id)` | 对单个 session 执行治理 |
| `run_forever(session_ids, poll_interval)` | 周期性治理 |
| `describe_capabilities()` | 输出能力说明 |

### 治理通常组合

- 压缩
- 晋升
- snapshot 清理
- 低价值清理建议

## 15. `ProjectorWorker`

### 方法

| 方法 | 说明 |
| --- | --- |
| `run_once(limit)` | 执行一次投影 |
| `run_forever(poll_interval, limit)` | 持续执行投影 |
| `describe_capabilities()` | 输出能力说明 |

## 16. 推荐使用策略

### 业务项目

优先顺序：

1. `AIMemory`
2. `ScopedAIMemory`
3. `AIMemoryMCPAdapter`

### 平台 / Runtime 项目

优先顺序：

1. `AIMemory` 统一入口
2. `services/*` 做精细控制
3. `workers/*` 做后台自动治理

### 不推荐

不建议一开始就直接围绕 Service + Worker 自己拼完整流程，原因是：

- 作用域处理更容易出错
- 跨域查询要自己协调
- 平台迭代成本更高
