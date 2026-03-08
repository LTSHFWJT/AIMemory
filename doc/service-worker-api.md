# Service / Worker API

这份文档面向两类人：

- 你已经不满足于只用 `AIMemory` facade，想直接调用内部 service
- 你准备做二次开发，想知道 worker、service、归档、知识和技能这些挂点在哪里

如果你只是日常使用 AIMemory，优先看 `facade-api.md`。  
这份文档更偏“进阶使用”和“实现层能力定位”。

---

## 1. 常见对象速览

### 1.1 Session 对象

| 字段 | 说明 |
| --- | --- |
| `id` | session ID |
| `user_id` | 用户 ID |
| `agent_id` | agent ID |
| `title` | 会话标题 |
| `status` | 会话状态 |
| `metadata` | 扩展元数据 |
| `ttl_seconds` | TTL 秒数 |
| `expires_at` | 过期时间 |
| `last_accessed_at` | 最近访问时间 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

### 1.2 Turn 对象

| 字段 | 说明 |
| --- | --- |
| `id` | turn ID |
| `session_id` | 所属 session |
| `run_id` | 所属 run，可为空 |
| `role` | 角色名 |
| `content` | 文本内容 |
| `name` | 实例名，可为空 |
| `metadata` | 扩展元数据 |
| `tokens_in` | 输入 token 数 |
| `tokens_out` | 输出 token 数 |
| `created_at` | 创建时间 |

### 1.3 Run / Task / Step

| 对象 | 常见字段 |
| --- | --- |
| `Run` | `id`、`session_id`、`user_id`、`agent_id`、`goal`、`status`、`metadata`、`started_at`、`ended_at`、`updated_at` |
| `Task` | `id`、`run_id`、`session_id`、`parent_task_id`、`title`、`status`、`priority`、`metadata`、`created_at`、`updated_at` |
| `Step` | `id`、`task_id`、`run_id`、`step_index`、`title`、`status`、`detail`、`metadata`、`created_at`、`updated_at` |

### 1.4 Context 返回

`store.interaction.get_context()` 返回：

| 字段 | 说明 |
| --- | --- |
| `session` | Session 对象 |
| `turns` | 最近若干轮对话 |
| `snapshot` | 最新 working memory snapshot |
| `variables` | session 变量列表 |
| `tool_states` | 工具状态列表 |

### 1.5 Timeline 返回

`store.execution.get_run_timeline()` 返回：

| 字段 | 说明 |
| --- | --- |
| `run` | Run 对象 |
| `tasks` | 任务列表 |
| `steps` | 步骤列表 |
| `checkpoints` | checkpoint 列表 |
| `tool_calls` | 工具调用记录 |
| `observations` | 观察记录 |

---

## 2. `InteractionService`

### 2.1 `create_session(...)`

```python
store.interaction.create_session(user_id, session_id=None, agent_id=None, title=None, ttl_seconds=None, metadata=None, status="active")
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `user_id` | 是 | 用户 ID |
| `session_id` | 否 | 自定义 session ID |
| `agent_id` | 否 | agent ID |
| `title` | 否 | 会话标题 |
| `ttl_seconds` | 否 | TTL 秒数 |
| `metadata` | 否 | 扩展元数据 |
| `status` | 否 | 状态，默认 `active` |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Session 对象` | 返回创建好的 session |

### 2.2 `append_turn(...)`

```python
store.interaction.append_turn(session_id, role, content, run_id=None, user_id=None, name=None, metadata=None, tokens_in=None, tokens_out=None, turn_id=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `role` | 是 | 角色名 |
| `content` | 是 | 轮次文本 |
| `run_id` | 否 | run ID |
| `user_id` | 否 | 用户 ID |
| `name` | 否 | 角色实例名 |
| `metadata` | 否 | 扩展元数据 |
| `tokens_in` | 否 | 输入 token 数 |
| `tokens_out` | 否 | 输出 token 数 |
| `turn_id` | 否 | 自定义 turn ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Turn 对象` | 返回写入后的 turn |

### 2.3 `get_context(session_id, limit=12)`

```python
store.interaction.get_context(session_id, limit=12)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `limit` | 否 | 返回最近多少轮 turn |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `session` | Session 对象 |
| `turns` | 最近对话轮次 |
| `snapshot` | 最新 snapshot |
| `variables` | 变量列表 |
| `tool_states` | 工具状态列表 |

### 2.4 `set_variable(session_id, key, value)`

```python
store.interaction.set_variable(session_id, key, value)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `key` | 是 | 变量名 |
| `value` | 是 | 变量值，会序列化存储 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Variable 对象` | 返回写入后的变量记录 |

### 2.5 `set_tool_state(...)`

```python
store.interaction.set_tool_state(session_id, tool_name, state_key, state_value, run_id=None, expires_at=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `tool_name` | 是 | 工具名 |
| `state_key` | 是 | 状态键 |
| `state_value` | 是 | 状态值 |
| `run_id` | 否 | run ID |
| `expires_at` | 否 | 过期时间 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `ToolState 对象` | 返回工具状态记录 |

### 2.6 `clear_session(session_id)`

```python
store.interaction.clear_session(session_id)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `message` | 结果提示 |
| `session_id` | 被清理的 session ID |

### 2.7 `compress_session_context(...)`

```python
store.interaction.compress_session_context(session_id, preserve_recent_turns=None, min_turns=None, max_summary_chars=420, metadata=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `preserve_recent_turns` | 否 | 保留最近多少轮原文 |
| `min_turns` | 否 | 至少多少轮才压缩 |
| `max_summary_chars` | 否 | 摘要最大字符数 |
| `metadata` | 否 | snapshot 元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `compressed` | 是否执行了压缩 |
| `session_id` | session ID |
| `turn_count` | 当前轮次数 |
| `reason` | 未压缩时的原因 |
| `compressed_turn_count` | 压缩掉的轮次数 |
| `snapshot` | 生成的 snapshot |

### 2.8 `session_health(session_id)`

```python
store.interaction.session_health(session_id)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `session_id` | session ID |
| `turn_count` | 轮次数 |
| `snapshot_count` | snapshot 数量 |
| `session_memory_count` | session memory 数量 |
| `promotable_session_memory_count` | 可晋升 session memory 数量 |
| `latest_snapshot_at` | 最近 snapshot 时间 |
| `snapshot_age_hours` | 距最近 snapshot 的小时数 |
| `recommendations` | 建议动作列表 |

### 2.9 `prune_snapshots(session_id, keep_recent=None)`

```python
store.interaction.prune_snapshots(session_id, keep_recent=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `keep_recent` | 否 | 保留最近多少个 snapshot |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `session_id` | session ID |
| `kept` | 保留数量 |
| `deleted` | 删除数量 |
| `deleted_ids` | 删除的 snapshot ID 列表 |

---

## 3. `ExecutionService`

### 3.1 `start_run(...)`

```python
store.execution.start_run(user_id, goal, session_id=None, run_id=None, agent_id=None, metadata=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `user_id` | 是 | 用户 ID |
| `goal` | 是 | 本次执行目标 |
| `session_id` | 否 | 关联 session |
| `run_id` | 否 | 自定义 run ID |
| `agent_id` | 否 | agent ID |
| `metadata` | 否 | 扩展元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Run 对象` | 返回创建后的 run |

### 3.2 `create_task(...)`

```python
store.execution.create_task(run_id, title, task_id=None, session_id=None, parent_task_id=None, priority=50, metadata=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `run_id` | 是 | 所属 run |
| `title` | 是 | 任务标题 |
| `task_id` | 否 | 自定义 task ID |
| `session_id` | 否 | 所属 session |
| `parent_task_id` | 否 | 父任务 ID |
| `priority` | 否 | 优先级 |
| `metadata` | 否 | 扩展元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Task 对象` | 返回创建后的 task |

### 3.3 `get_task(task_id)`

```python
store.execution.get_task(task_id)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `task_id` | 是 | task ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Task 对象` | 找到时返回 task |
| `None` | 找不到时返回 `None` |

### 3.4 `add_task_step(...)`

```python
store.execution.add_task_step(task_id, run_id, title, detail=None, step_index=None, status="pending", metadata=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `task_id` | 是 | 所属 task |
| `run_id` | 是 | 所属 run |
| `title` | 是 | 步骤标题 |
| `detail` | 否 | 步骤细节 |
| `step_index` | 否 | 步骤序号，不传时自动递增 |
| `status` | 否 | 步骤状态 |
| `metadata` | 否 | 扩展元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Step 对象` | 返回创建后的 step |

### 3.5 `checkpoint(...)`

```python
store.execution.checkpoint(run_id, snapshot, session_id=None, checkpoint_name="checkpoint", metadata=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `run_id` | 是 | run ID |
| `snapshot` | 是 | checkpoint 内容 |
| `session_id` | 否 | session ID |
| `checkpoint_name` | 否 | checkpoint 名称 |
| `metadata` | 否 | 扩展元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Checkpoint 对象` | 返回 checkpoint 记录 |

### 3.6 `log_tool_call(...)`

```python
store.execution.log_tool_call(run_id, tool_name, arguments=None, result=None, task_id=None, session_id=None, status="completed", metadata=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `run_id` | 是 | run ID |
| `tool_name` | 是 | 工具名 |
| `arguments` | 否 | 工具参数 |
| `result` | 否 | 工具结果 |
| `task_id` | 否 | task ID |
| `session_id` | 否 | session ID |
| `status` | 否 | 调用状态 |
| `metadata` | 否 | 扩展元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `ToolCall 对象` | 返回工具调用记录 |

### 3.7 `add_observation(...)`

```python
store.execution.add_observation(run_id, kind, content, task_id=None, session_id=None, metadata=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `run_id` | 是 | run ID |
| `kind` | 是 | 观察类型 |
| `content` | 是 | 观察内容 |
| `task_id` | 否 | task ID |
| `session_id` | 否 | session ID |
| `metadata` | 否 | 扩展元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Observation 对象` | 返回观察记录 |

### 3.8 `get_run(run_id)`

```python
store.execution.get_run(run_id)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `run_id` | 是 | run ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Run 对象` | 找到时返回 run |
| `None` | 找不到时返回 `None` |

### 3.9 `update_run(run_id, status, metadata=None, ended=False)`

```python
store.execution.update_run(run_id, status, metadata=None, ended=False)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `run_id` | 是 | run ID |
| `status` | 是 | 新状态 |
| `metadata` | 否 | 扩展元数据 |
| `ended` | 否 | 是否顺带标记为结束 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Run 对象` | 返回更新后的 run |

### 3.10 `get_run_timeline(run_id)`

```python
store.execution.get_run_timeline(run_id)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `run_id` | 是 | run ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `run` | Run 对象 |
| `tasks` | Task 列表 |
| `steps` | Step 列表 |
| `checkpoints` | Checkpoint 列表 |
| `tool_calls` | Tool Call 列表 |
| `observations` | Observation 列表 |

---

## 4. `KnowledgeService`

### 4.1 `create_source(...)`

```python
store.knowledge.create_source(name, source_type="manual", uri=None, metadata=None, source_id=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 知识源名称 |
| `source_type` | 否 | 知识源类型，默认 `manual` |
| `uri` | 否 | 来源 URI |
| `metadata` | 否 | 扩展元数据 |
| `source_id` | 否 | 自定义 source ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `KnowledgeSource 对象` | 返回知识源记录 |

### 4.2 `ingest_text(...)`

```python
store.knowledge.ingest_text(title, text, user_id=None, source_id=None, source_name="manual", version_label="v1", metadata=None, chunk_size=500, overlap=80, document_id=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `title` | 是 | 文档标题 |
| `text` | 是 | 文档正文 |
| `user_id` | 否 | 用户 ID |
| `source_id` | 否 | 知识源 ID |
| `source_name` | 否 | 知识源名称 |
| `version_label` | 否 | 版本标签 |
| `metadata` | 否 | 扩展元数据 |
| `chunk_size` | 否 | 分块大小 |
| `overlap` | 否 | 重叠字符数 |
| `document_id` | 否 | 自定义文档 ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Document 对象` | 返回文档对象 |
| `versions` | 文档版本列表 |
| `chunk_count` | 分块数量 |

### 4.3 `get_document(document_id)`

```python
store.knowledge.get_document(document_id)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `document_id` | 是 | 文档 ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Document 对象` | 找到时返回文档 |
| `None` | 找不到时返回 `None` |

### 4.4 `list_documents(source_id=None, user_id=None)`

```python
store.knowledge.list_documents(source_id=None, user_id=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `source_id` | 否 | 知识源过滤条件 |
| `user_id` | 否 | 用户过滤条件 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `results` | 文档列表 |

### 4.5 `get_document_text(document_id)`

```python
store.knowledge.get_document_text(document_id)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `document_id` | 是 | 文档 ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `str` | 返回文档正文文本 |

---

## 5. `SkillService`

### 5.1 `register(...)`

```python
store.skills.register(name, description, owner_id=None, prompt_template=None, workflow=None, schema=None, version="0.1.0", tools=None, tests=None, topics=None, assets=None, status="draft", metadata=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 技能名称 |
| `description` | 是 | 技能描述 |
| `owner_id` | 否 | 技能拥有者 |
| `prompt_template` | 否 | 提示模板 |
| `workflow` | 否 | 工作流定义 |
| `schema` | 否 | 输入输出 schema |
| `version` | 否 | 版本号 |
| `tools` | 否 | 绑定工具列表 |
| `tests` | 否 | 技能测试样例 |
| `topics` | 否 | 主题标签 |
| `assets` | 否 | 附件或资源描述 |
| `status` | 否 | 技能状态 |
| `metadata` | 否 | 扩展元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Skill 对象` | 返回技能对象 |
| `versions` | 版本列表 |
| `bindings` | 绑定工具列表 |
| `tests` | 测试样例列表 |

### 5.2 `get_skill(skill_id)`

```python
store.skills.get_skill(skill_id)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `skill_id` | 是 | 技能 ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Skill 对象` | 找到时返回技能 |
| `None` | 找不到时返回 `None` |

### 5.3 `list_skills(status=None)`

```python
store.skills.list_skills(status=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `status` | 否 | 按状态过滤技能 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `results` | 技能列表 |

### 5.4 `activate_version(skill_id, version)`

```python
store.skills.activate_version(skill_id, version)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `skill_id` | 是 | 技能 ID |
| `version` | 是 | 要激活的版本号 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Skill 对象` | 返回激活后的技能对象 |

---

## 6. `ArchiveService`

### 6.1 `archive_session(...)`

```python
store.archive.archive_session(session_id, user_id=None, summary=None, metadata=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `user_id` | 否 | 用户 ID |
| `summary` | 否 | 手动指定归档摘要 |
| `metadata` | 否 | 扩展元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Archive 对象` | 返回归档记录 |

### 6.2 `archive_memory(memory_id, metadata=None)`

```python
store.archive.archive_memory(memory_id, metadata=None)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `memory_id` | 是 | 记忆 ID |
| `metadata` | 否 | 扩展元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Archive 对象` | 返回归档记录 |

### 6.3 `get_archive(archive_unit_id)`

```python
store.archive.get_archive(archive_unit_id)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `archive_unit_id` | 是 | 归档 ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Archive 对象` | 找到时返回归档对象 |
| `None` | 找不到时返回 `None` |

### 6.4 `restore_archive(archive_unit_id)`

```python
store.archive.restore_archive(archive_unit_id)
```

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `archive_unit_id` | 是 | 归档 ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `dict` | 返回归档时保存的原始 JSON 载荷 |

---

## 7. 其他内部 service

这一节主要补充 facade 不直接展开、但在二次开发时很有用的几个挂点。

### 7.1 `MemoryService`

`store.memory` 上最常用的方法如下。

| 方法 | 主要参数 | 返回信息 |
| --- | --- | --- |
| `add(messages, user_id=None, agent_id=None, session_id=None, run_id=None, actor_id=None, role=None, metadata=None, memory_type=None, importance=0.5, long_term=True, source="conversation", record_turns=True, infer=True, prompt=None)` | 与 facade 的 `add()` 基本一致 | 返回 `results`、`facts` 或非智能路径下的 `results`、`scope` |
| `remember(text, user_id=None, agent_id=None, session_id=None, run_id=None, actor_id=None, role=None, metadata=None, memory_type="semantic", importance=0.5, long_term=True, source="explicit")` | 显式写入单条记忆 | 返回单个 Memory 对象 |
| `get(memory_id)` | `memory_id` | 返回单个 Memory 或 `None` |
| `get_all(user_id=None, agent_id=None, session_id=None, run_id=None, actor_id=None, role=None, strategy_scope=None, scope="long-term", limit=100, offset=0, include_deleted=False, filters=None)` | 直接列出记忆 | 返回 `results` |
| `promote_session_memories(session_id, user_id=None, agent_id=None, run_id=None, limit=50, min_importance=0.55, include_memory_types=None, force=False, archive_after_promotion=False, metadata=None)` | 晋升 session memory | 返回 `source_count`、`promoted_count`、`results`、`facts`、`source_ids`、`skipped` |
| `plan_low_value_cleanup(user_id=None, agent_id=None, run_id=None, scope="long-term", limit=100, threshold=None)` | 只生成低价值记忆清理计划 | 返回 `threshold`、`results` |
| `update(memory_id, text=None, metadata=None, importance=None, status=None, timestamp=None)` | 更新记忆 | 返回更新后的 Memory |
| `delete(memory_id)` | 删除单条记忆 | 返回 `message`、`id` |
| `delete_by_query(query, retrieval_service, user_id=None, session_id=None, scope="all", limit=10, filters=None)` | 先检索再删除 | 返回 `message`、`ids` |
| `history(memory_id)` | 查看记忆历史 | 返回事件列表 |

说明：

- 如果你只是正常使用，优先还是用 facade。
- `store.memory` 更适合你要在内部流程里直接控制记忆写入方式时使用。

### 7.2 `RetrievalService`

`store.retrieve` 主要用于更细粒度地控制召回过程。

| 方法 | 主要参数 | 返回信息 |
| --- | --- | --- |
| `search_memory(query, user_id=None, session_id=None, agent_id=None, run_id=None, actor_id=None, role=None, scope="all", limit=10, threshold=0.0, filters=None)` | 只查 memory 域 | 返回 `results`、`relations`、`recall_plan` |
| `retrieve(query, user_id=None, session_id=None, agent_id=None, run_id=None, actor_id=None, role=None, domains=None, filters=None, limit=10, threshold=0.0)` | 多域统一检索 | 返回 `results`、`route` |
| `search_interaction(query, session_id, actor_id=None, role=None, limit=10, threshold=0.0, filters=None)` | 只查 interaction 域 | 返回 `results` |
| `search_knowledge(query, limit=10, threshold=0.0, filters=None)` | 只查 knowledge 域 | 返回 `results` |
| `search_skills(query, limit=10, threshold=0.0, filters=None)` | 只查 skill 域 | 返回 `results` |
| `search_archive(query, user_id=None, session_id=None, limit=10, threshold=0.0, filters=None)` | 只查 archive 域 | 返回 `results` |
| `search_execution(query, user_id=None, session_id=None, limit=10, threshold=0.0, filters=None)` | 只查 execution 域 | 返回 `results` |
| `plan_memory_recall(query, context, preferred_scope=None, limit=None, auxiliary_limit=None)` | 只生成召回计划 | 返回 `strategy_scope`、`strategy_name`、`query_profile`、`stages` 等 |
| `explain_memory_recall(query, user_id=None, session_id=None, agent_id=None, run_id=None, actor_id=None, role=None, preferred_scope=None, limit=None)` | 用上下文生成可读召回计划 | 返回 recall plan |

### 7.3 `ProjectionService`

`store.projection` 主要用于 outbox 投影。

| 方法 | 主要参数 | 返回信息 |
| --- | --- | --- |
| `enqueue(topic, entity_type, entity_id, action, payload=None)` | 手动往 outbox 塞一个事件 | 返回 outbox 事件对象 |
| `project_pending(limit=None)` | 处理待投影事件 | 返回 `processed`、`failed`、`event_ids` |

---

## 8. Worker

### 7.1 `store.projector.run_once(limit=None)`

作用：

- 处理 outbox，把主库里的待投影事件同步到索引和图后端

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `limit` | 否 | 最多处理多少条事件 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `processed` | 成功处理的事件数 |
| `failed` | 失败的事件数 |
| `event_ids` | 成功处理的事件 ID 列表 |

### 7.2 `store.compactor.run_once(session_id, **kwargs)`

作用：

- 压缩长对话上下文

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `preserve_recent_turns` | 否 | 保留最近多少轮 |
| `min_turns` | 否 | 至少多少轮才压缩 |
| `max_summary_chars` | 否 | 摘要最大字符数 |
| `metadata` | 否 | snapshot 元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| 同 `compress_session_context()` | 返回结构与 interaction 压缩接口一致 |

### 7.3 `store.distiller.run_once(session_id, **kwargs)`

作用：

- 把 session memory 晋升到长期记忆

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `user_id` | 否 | 用户 ID |
| `agent_id` | 否 | agent ID |
| `run_id` | 否 | run ID |
| `limit` | 否 | 最多考察多少条 session memory |
| `min_importance` | 否 | 晋升最低重要度 |
| `include_memory_types` | 否 | 只晋升这些类型 |
| `force` | 否 | 是否强制执行 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| 同 `promote_session_memories()` | 返回结构与晋升接口一致 |

### 7.4 `store.cleaner.run_once(...)`

作用：

- 查找并处理低价值记忆

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `user_id` | 否 | 用户 ID |
| `agent_id` | 否 | agent ID |
| `run_id` | 否 | run ID |
| `scope` | 否 | 清理范围 |
| `limit` | 否 | 扫描上限 |
| `threshold` | 否 | 清理阈值 |
| `archive` | 否 | 是否归档 |
| `delete` | 否 | 是否直接删除 |
| `dry_run` | 否 | 是否只预览 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| 同 `cleanup_low_value_memories()` | 返回结构与 facade 清理接口一致 |

### 7.5 `store.governor.run_once(session_id, **kwargs)`

作用：

- 对某个 session 做一轮综合治理

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `user_id` | 否 | 用户 ID |
| `agent_id` | 否 | agent ID |
| `run_id` | 否 | run ID |
| `compact` | 否 | 是否压缩 |
| `promote` | 否 | 是否晋升 |
| `prune_snapshots` | 否 | 是否清理 snapshot |
| `cleanup` | 否 | 是否做低价值清理 |
| `cleanup_scope` | 否 | 清理范围 |
| `cleanup_threshold` | 否 | 清理阈值 |
| `cleanup_dry_run` | 否 | 是否只预览清理 |
| `force` | 否 | 是否忽略推荐直接执行 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| 同 `govern_session()` | 返回结构与 facade 治理接口一致 |

---

### 8.6 Worker 的其他方法

除了上面的 `run_once(...)`，几个 worker 还普遍带有下面这些方法：

| 方法 | 说明 |
| --- | --- |
| `run_forever(...)` | 常驻循环执行；更适合你自己在本地脚本里调度 |
| `describe_capabilities()` | 返回当前 worker 的能力描述 |

---

## 9. 进阶示例

### 9.1 直接操作 service

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    # ===== interaction =====
    session = store.interaction.create_session(
        user_id="user-7",
        session_id="session-7",
        agent_id="agent-7",
        title="高级接口演示",
    )

    store.interaction.append_turn(
        session_id="session-7",
        role="user",
        content="请记录我的工作上下文。",
        user_id="user-7",
    )

    # 写一个 session 变量
    variable = store.interaction.set_variable(
        session_id="session-7",
        key="current_goal",
        value={"name": "service-demo", "status": "running"},
    )

    # 写一个工具状态
    tool_state = store.interaction.set_tool_state(
        session_id="session-7",
        tool_name="planner",
        state_key="phase",
        state_value={"step": "analysis"},
    )

    context = store.interaction.get_context("session-7", limit=12)

    # ===== execution =====
    run = store.execution.start_run(
        user_id="user-7",
        goal="演示 service 接口",
        session_id="session-7",
        agent_id="agent-7",
    )

    task = store.execution.create_task(
        run_id=run["id"],
        title="设计数据库模式",
        session_id="session-7",
        priority=10,
    )

    step = store.execution.add_task_step(
        task_id=task["id"],
        run_id=run["id"],
        title="创建 memories 表",
        detail="先定义 memory 主表和事件表",
    )

    checkpoint = store.execution.checkpoint(
        run_id=run["id"],
        session_id="session-7",
        checkpoint_name="schema-v1",
        snapshot={"step": step["title"], "status": "done"},
    )

    tool_call = store.execution.log_tool_call(
        run_id=run["id"],
        tool_name="sqlite.migrate",
        arguments={"table": "memories"},
        result={"ok": True},
        task_id=task["id"],
        session_id="session-7",
    )

    observation = store.execution.add_observation(
        run_id=run["id"],
        kind="note",
        content="数据库模式完成第一版。",
        task_id=task["id"],
        session_id="session-7",
    )

    timeline = store.execution.get_run_timeline(run["id"])

    # ===== knowledge =====
    source = store.knowledge.create_source(
        name="openclaw-notes",
        source_type="manual",
        uri="local://notes.md",
    )

    document = store.knowledge.ingest_text(
        title="OpenClaw 设计说明",
        text="OpenClaw 需要 memory、knowledge、archive 三域协同。",
        user_id="user-7",
        source_id=source["id"],
    )

    # ===== skills =====
    skill = store.skills.register(
        name="openclaw_router",
        description="负责把问题路由到正确域。",
        owner_id="agent-7",
        tools=["query", "search"],
        topics=["routing", "memory", "OpenClaw"],
        status="draft",
    )

    activated_skill = store.skills.activate_version(skill["id"], "0.1.0")

    # ===== archive =====
    memory = store.memory_store(
        "用户偏好结构化输出。",
        user_id="user-7",
        session_id="session-7",
        long_term=True,
    )

    archived_memory = store.archive.archive_memory(memory["id"])
    restored_memory = store.archive.restore_archive(archived_memory["id"])

    archived_session = store.archive.archive_session("session-7", user_id="user-7")
    restored_session = store.archive.restore_archive(archived_session["id"])

    print(session)
    print(variable)
    print(tool_state)
    print(context)
    print(task)
    print(step)
    print(checkpoint)
    print(tool_call)
    print(observation)
    print(timeline)
    print(document)
    print(activated_skill)
    print(restored_memory)
    print(restored_session)
```

### 9.2 直接操作 worker

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    # 准备一些数据，方便演示 worker
    store.create_session(user_id="user-8", session_id="session-8")
    store.append_turn("session-8", "user", "请记录这个长对话。", user_id="user-8")
    store.append_turn("session-8", "assistant", "好的，我会整理上下文。", user_id="user-8")
    store.memory_store(
        "本轮会话正在整理上下文。",
        user_id="user-8",
        session_id="session-8",
        long_term=False,
    )

    # 手动执行 outbox 投影
    project_result = store.projector.run_once(limit=100)

    # 压缩对话
    compact_result = store.compactor.run_once(
        "session-8",
        min_turns=2,
        preserve_recent_turns=1,
    )

    # 晋升 session memory
    promote_result = store.distiller.run_once(
        "session-8",
        user_id="user-8",
        min_importance=0.2,
        force=True,
    )

    # 低价值记忆清理，先 dry-run 预览
    cleanup_result = store.cleaner.run_once(
        user_id="user-8",
        scope="long-term",
        dry_run=True,
    )

    # 做一轮综合治理
    govern_result = store.governor.run_once(
        "session-8",
        user_id="user-8",
        cleanup=True,
        cleanup_dry_run=True,
        force=True,
    )

    print(project_result)
    print(compact_result)
    print(promote_result)
    print(cleanup_result)
    print(govern_result)
```
