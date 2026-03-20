# Service & Worker API

这份文档面向内核二开者，说明 `aimemory/services/*`、`aimemory/workers/*` 和 `memory_intelligence/*` 的职责边界。

先给结论：

- 业务接入方优先用 façade：`AIMemory.api.*` 和 `memory.events.*`
- service / worker 更适合批处理、内核扩展、定制算法链路
- 平台 LLM 压缩仍然建议从 façade 进入，不建议在 service 层直接硬编码平台调用

## 1. 分层关系

```text
Facade
  -> scope merge
  -> ACL
  -> multi-domain orchestration
  -> platform event hooks
  -> platform LLM compression fallback

Service
  -> domain-level operations
  -> closer to tables / projection queue
  -> reusable building blocks

Worker
  -> scheduled automation
  -> compaction / promotion / cleaning / governance / projection

Memory Intelligence
  -> candidate extraction
  -> neighbor recall
  -> add / update / supersede / merge / delete planning
```

## 2. `ServiceBase`

所有 service 都以 `ServiceBase` 为基类。

构造参数：

- `db`
- `projection`
- `config`
- `object_store=None`

基础能力：

- 行反序列化
- 对象存储落库辅助
- 惰性 `_kernel()`，必要时按同一份 `config` 创建内部 `AIMemory`

说明：

- service 不是默认导出的公共对象
- 你需要自己实例化和编排

## 3. `MemoryService`

文件：`aimemory/services/memory_service.py`

公开方法：

| 方法 | 作用 |
| --- | --- |
| `set_intelligence_pipeline(pipeline)` | 替换记忆抽取管线 |
| `add(messages, **kwargs)` | 批量抽取并写入记忆 |
| `remember(text, **kwargs)` | 直接写单条记忆 |
| `get(memory_id)` | 获取记忆 |
| `get_all(...)` | 列表 |
| `promote_session_memories(session_id, ...)` | 会话记忆晋升 |
| `plan_low_value_cleanup(...)` | 规划低价值清理 |
| `update(memory_id, ...)` | 更新 |
| `supersede(memory_id, ...)` | 版本替代 |
| `link(memory_id, target_memory_ids, ...)` | 建立关系 |
| `delete(memory_id)` | 删除 |
| `delete_by_query(query, ...)` | 按查询删除 |
| `history(memory_id)` | 审计历史 |
| `build_scope_context(...)` | 构建 `MemoryScopeContext` |

适合场景：

- 定制抽取 / 规划算法
- 批量记忆维护
- 离线清理与版本修复

## 4. `InteractionService`

文件：`aimemory/services/interaction_service.py`

公开方法：

| 方法 | 作用 |
| --- | --- |
| `create_session(...)` | 创建会话 |
| `get_session(session_id)` | 读取会话 |
| `append_turn(...)` | 写入 turn |
| `list_turns(session_id, limit=20, offset=0)` | 列表 turn |
| `upsert_snapshot(...)` | 写或更新 working memory snapshot |
| `set_tool_state(...)` | 保存工具状态 |
| `set_variable(session_id, key, value)` | 保存 session 变量 |
| `get_context(session_id, limit=12)` | 获取 session 上下文 |
| `compress_session_context(...)` | 本地压缩 session |
| `session_health(session_id)` | 健康检查 |
| `prune_snapshots(session_id, ...)` | 清理旧 snapshot |
| `clear_session(session_id)` | 清理会话关联内容 |

注意：

- façade 的 `api.session.*` 会额外处理 scope、ACL、自动 capture、事件编排
- 直接下沉到 service 时，这些语义需要你自己补

## 5. `KnowledgeService`

文件：`aimemory/services/knowledge_service.py`

公开方法：

- `create_source(...)`
- `ingest_text(...)`
- `get_document(document_id)`
- `list_documents(...)`
- `get_document_text(document_id)`

定位：

- 更接近知识入库流水线
- 不负责完整多智能体协作语义

## 6. `SkillService`

文件：`aimemory/services/skill_service.py`

公开方法：

- `register(...)`
- `get_skill(skill_id)`
- `list_skills(status=None, owner_agent_id=None)`

说明：

- façade 层的 skill 能力更完整，因为额外包含 reference 搜索、execution context 刷新和 ACL

## 7. `ArchiveService`

文件：`aimemory/services/archive_service.py`

公开方法：

- `archive_session(session_id, ...)`
- `archive_memory(memory_id, ...)`
- `get_archive(archive_unit_id)`
- `restore_archive(archive_unit_id)`

## 8. `ExecutionService`

文件：`aimemory/services/execution_service.py`

公开方法：

- `start_run(...)`
- `get_run(run_id)`
- `update_run(run_id, status, metadata=None, ended=False)`
- `create_task(run_id, title, ...)`
- `get_task(task_id)`
- `add_task_step(...)`
- `checkpoint(...)`
- `log_tool_call(...)`
- `add_observation(...)`
- `get_run_timeline(run_id)`

## 9. `RetrievalService`

文件：`aimemory/services/retrieval_service.py`

构造时可注入：

- `router`
- `reranker`
- `index_backend`
- `graph_backend`
- `recall_planner`

公开方法：

| 方法 | 作用 |
| --- | --- |
| `search_memory(query, ...)` | 搜记忆 |
| `retrieve(query, ...)` | 统一检索 |
| `search_interaction(query, ...)` | 搜会话交互 |
| `search_knowledge(query, ...)` | 搜知识切块 |
| `search_skills(query, ...)` | 搜技能 |
| `search_archive(query, ...)` | 搜归档 |
| `search_execution(query, ...)` | 搜执行记录 |
| `plan_memory_recall(query, ...)` | recall plan |
| `explain_memory_recall(query, ...)` | recall 解释 |

适合场景：

- 做定制 router / planner / reranker
- 离线检索实验
- 独立检索服务封装

## 10. `ProjectionService`

文件：`aimemory/services/projection_service.py`

作用：

- 处理投影队列
- 把 memory / knowledge chunk / skill / archive / context / handoff / reflection 写入向量索引
- 可选构建图关系

公开方法：

- `enqueue(...)`
- `project_pending(limit=None)`

如果你要替换向量后端或增加图投影，这是关键入口。

## 11. `MemoryIntelligencePipeline`

文件：`aimemory/memory_intelligence/pipeline.py`

职责：

- 规范化消息
- 事实候选抽取
- 邻域召回
- 动作规划
- 执行动作：`ADD / UPDATE / SUPERSEDE / MERGE / LINK / DELETE`

核心方法：

- `add(messages, context=..., metadata=..., long_term=True, ...)`

内部关键阶段：

1. `vision_processor.normalize(...)`
2. `extractor.extract(...)`
3. `_retrieve_neighbors(...)`
4. `planner.plan(...)`
5. `_apply_action(...)`

这部分是“自动记忆写入”的主引擎。

## 12. Worker

### `SessionCompactionWorker`

文件：`aimemory/workers/compactor.py`

作用：

- 定时触发 `compress_session_context(...)`

### `SessionMemoryPromoterWorker`

文件：`aimemory/workers/distiller.py`

作用：

- 把 session memory 晋升为 long-term memory

### `LowValueMemoryCleanerWorker`

文件：`aimemory/workers/cleaner.py`

作用：

- 清理低价值记忆
- 可联动归档

### `GovernanceAutomationWorker`

文件：`aimemory/workers/governor.py`

作用：

- 把 session health、压缩、晋升、清理串成治理流程

### `ProjectorWorker`

文件：`aimemory/workers/projector.py`

作用：

- 持续消费投影队列

## 13. 与平台 LLM 的边界

需要特别区分两类压缩：

### 本地算法压缩

典型入口：

- `InteractionService.compress_session_context(...)`
- `AIMemory.compress_text(...)`
- `AIMemory.compress_document(...)`
- memory / archive / skill reference 的域级压缩

特点：

- 稳定
- 无外部依赖
- 适合在线 runtime 的基础窗口治理

### 平台 LLM 压缩

推荐入口：

- `AIMemory.api.context.build(...)`
- `AIMemory.api.handoff.build(...)`
- `AIMemory.api.reflection.session(...)`
- `AIMemory.api.reflection.run(...)`

特点：

- 走平台 LLM 插件
- 有本地回退
- 会记录 `compression_jobs`

因此，如果你在做平台接入，不要在 service 层直接塞一个“外部 LLM 调用”；应通过 façade 的插件路径统一接入。

## 14. 二开建议

如果你要对 `aimemory` 继续扩展，优先选择下面这些扩展点：

- 平台 LLM：`register_platform_llm_plugin(...)`
- 平台事件：自定义 `PlatformEventAdapter`
- 抽取 / 规划：替换 `MemoryIntelligencePipeline` 的 extractor / planner
- 检索：替换 `RetrievalService` 的 router / planner / reranker
- 投影：替换 `ProjectionService` 的 index / graph backend

不建议做的事：

- 在业务层绕开 façade 直接拼 SQL
- 把平台 LLM 压缩塞进 MCP 工具调用链
- 把所有正文都强制外置为本地文件
