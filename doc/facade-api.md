# Facade API

这份文档只讲一层：`AIMemory` 和 `AsyncAIMemory`。

如果你的使用方式是“把 AIMemory 当成普通 Python 库直接调用”，那大部分时间只需要看这一份。  
如果你需要直接操作内部 service 或 worker，再去看 `service-worker-api.md`。

---

## 1. 先看常见返回对象

很多 facade 接口会返回相同结构的对象。先看这里，后面查接口会更快。

### 1.1 Memory 对象

| 字段 | 说明 |
| --- | --- |
| `id` | 记忆 ID |
| `user_id` | 所属用户 ID |
| `agent_id` | 所属 agent ID，可为空 |
| `session_id` | 所属 session，可为空 |
| `run_id` | 所属 run，可为空 |
| `scope` | 记忆范围，常见值为 `session` 或 `long-term` |
| `memory_type` | 记忆类型，如 `semantic`、`preference` |
| `text` | 记忆原文 |
| `summary` | 自动生成的短摘要 |
| `importance` | 重要度分数 |
| `status` | 常见值：`active`、`archived`、`deleted` |
| `source` | 记忆来源 |
| `metadata` | 扩展元数据 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |
| `archived_at` | 归档时间，可为空 |
| `actor_id` | 若 metadata 中带有此字段，会提升到顶层 |
| `role` | 若 metadata 中带有此字段，会提升到顶层 |

### 1.2 Mutation 对象

`add()` 返回的 `results` 里，通常是这种结构。

| 字段 | 说明 |
| --- | --- |
| `event` | 记忆动作，常见值：`ADD`、`UPDATE`、`DELETE`、`NONE` |
| `memory` | 最终处理后的记忆文本 |
| `reason` | 为什么会做这个动作 |
| `id` | 涉及到的记忆 ID |
| `confidence` | 该动作的置信度 |
| `previous_memory` | 更新前的旧文本，可为空 |
| `evidence` | 动作依据 |

### 1.3 `search()` / `memory_search()` 返回

| 字段 | 说明 |
| --- | --- |
| `results` | 检索命中的记忆列表 |
| `relations` | 图关系列表 |
| `recall_plan` | 本次召回计划 |

### 1.4 `query()` 返回

| 字段 | 说明 |
| --- | --- |
| `results` | 多域检索结果列表 |
| `route` | 实际走过的检索路径 |

### 1.5 Session Health 返回

| 字段 | 说明 |
| --- | --- |
| `session_id` | 会话 ID |
| `turn_count` | 对话轮次数 |
| `snapshot_count` | 当前 snapshot 数量 |
| `session_memory_count` | session memory 数量 |
| `promotable_session_memory_count` | 当前可晋升为长期记忆的 session memory 数量 |
| `latest_snapshot_at` | 最近一次 snapshot 时间 |
| `snapshot_age_hours` | 最近 snapshot 距今多少小时 |
| `recommendations` | 系统建议执行的治理动作 |

### 1.6 Capability 返回

| 字段 | 说明 |
| --- | --- |
| `category` | 能力类别 |
| `provider` | 配置的 Provider 名称 |
| `active_provider` | 实际生效的 Provider，可为空 |
| `features` | 当前能力开关与特性描述 |
| `items` | 子能力集合 |
| `notes` | 备注信息 |

---

## 2. `AIMemory`：记忆读写接口

### 2.1 `add(messages, **kwargs)`

```python
store.add(messages, **kwargs)
```

作用：

- 让系统从消息里自动抽取记忆
- 默认经过 `MemoryIntelligencePipeline`

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `messages` | 是 | 支持 `str`、单个消息字典、消息列表 |
| `user_id` | 否 | 用户 ID |
| `agent_id` | 否 | agent ID |
| `session_id` | 否 | session ID；若同时 `record_turns=True`，会记录轮次 |
| `run_id` | 否 | run ID |
| `actor_id` | 否 | 角色实例 ID |
| `role` | 否 | 角色名或上下文角色 |
| `metadata` | 否 | 扩展元数据 |
| `memory_type` | 否 | 显式指定记忆类型；不传时可推断 |
| `importance` | 否 | 非智能路径下的默认重要度 |
| `long_term` | 否 | 是否写成长期记忆，默认 `True` |
| `source` | 否 | 来源标识，默认 `conversation` |
| `record_turns` | 否 | 是否把消息同步记到 interaction 域 |
| `infer` | 否 | 是否启用类型推断 |
| `prompt` | 否 | 预留参数 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `results` | Mutation 列表，字段见上面的 Mutation 对象 |
| `facts` | 从消息中抽取出的事实文本列表 |

### 2.2 `memory_store(text, user_id=None, session_id=None, long_term=True, **kwargs)`

```python
store.memory_store(text, user_id=None, session_id=None, long_term=True, **kwargs)
```

作用：

- 显式写入一条记忆
- 适合你已经明确知道要存什么时使用

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `text` | 是 | 要存储的记忆文本 |
| `user_id` | 否 | 用户 ID |
| `session_id` | 否 | session ID |
| `long_term` | 否 | 是否存为长期记忆，默认 `True` |
| `agent_id` | 否 | agent ID |
| `run_id` | 否 | run ID |
| `actor_id` | 否 | 角色实例 ID |
| `role` | 否 | 角色名 |
| `metadata` | 否 | 扩展元数据 |
| `memory_type` | 否 | 记忆类型 |
| `importance` | 否 | 重要度 |
| `source` | 否 | 来源标识 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Memory 对象` | 返回单条 Memory，字段见上面的 Memory 对象 |

### 2.3 `get(memory_id)` / `memory_get(memory_id)`

```python
store.get(memory_id)
store.memory_get(memory_id)
```

作用：

- 根据 ID 获取一条记忆

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `memory_id` | 是 | 记忆 ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Memory 对象` | 找到时返回 Memory |
| `None` | 找不到时返回 `None` |

### 2.4 `get_all(**kwargs)` / `memory_list(...)`

```python
store.get_all(**kwargs)
store.memory_list(user_id=None, session_id=None, scope="all", limit=100, offset=0, **kwargs)
```

作用：

- 批量列出记忆

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `user_id` | 否 | 用户过滤条件 |
| `agent_id` | 否 | agent 过滤条件 |
| `session_id` | 否 | session 过滤条件 |
| `run_id` | 否 | run 过滤条件 |
| `actor_id` | 否 | actor 过滤条件 |
| `role` | 否 | role 过滤条件 |
| `strategy_scope` | 否 | 按 `user / agent / run` 过滤 |
| `scope` | 否 | `session` / `long-term` / `all` |
| `limit` | 否 | 返回条数 |
| `offset` | 否 | 偏移量 |
| `include_deleted` | 否 | 是否包含已删除记忆 |
| `filters` | 否 | 过滤 DSL |
| `page_size` / `pageSize` | 否 | 兼容别名，会映射到 `limit` |
| `page` | 否 | 兼容别名，会换算成 `offset` |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `results` | Memory 列表 |

### 2.5 `search(query, **kwargs)` / `memory_search(...)`

```python
store.search(query, **kwargs)
store.memory_search(query, user_id=None, session_id=None, scope="all", top_k=5, search_threshold=0.0, **kwargs)
```

作用：

- 检索记忆
- 返回结果、图关系和召回计划

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `query` | 是 | 查询文本 |
| `user_id` | 否 | 用户上下文 |
| `session_id` | 否 | session 上下文 |
| `agent_id` | 否 | agent 上下文 |
| `run_id` | 否 | run 上下文 |
| `actor_id` | 否 | actor 上下文 |
| `role` | 否 | role 上下文 |
| `scope` | 否 | `session` / `long-term` / `all` |
| `limit` | 否 | 返回条数 |
| `threshold` | 否 | 最低分过滤 |
| `filters` | 否 | 过滤 DSL |
| `top_k` / `topK` | 否 | 兼容别名，会映射到 `limit` |
| `search_threshold` / `searchThreshold` | 否 | 兼容别名，会映射到 `threshold` |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `results` | 命中的 Memory 列表 |
| `relations` | 图关系列表 |
| `recall_plan` | 本次召回计划 |

### 2.6 `update(memory_id, **kwargs)`

```python
store.update(memory_id, **kwargs)
```

作用：

- 更新已有记忆

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `memory_id` | 是 | 记忆 ID |
| `text` | 否 | 新文本 |
| `metadata` | 否 | 新元数据，会与旧 metadata 合并 |
| `importance` | 否 | 新重要度 |
| `status` | 否 | 新状态 |
| `timestamp` | 否 | 指定更新时间 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Memory 对象` | 返回更新后的 Memory |

### 2.7 `delete(memory_id)`

```python
store.delete(memory_id)
```

作用：

- 按 ID 删除一条记忆

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `memory_id` | 是 | 记忆 ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `message` | 删除结果提示 |
| `id` | 被删除的记忆 ID |

### 2.8 `memory_forget(...)`

```python
store.memory_forget(memory_id=None, query=None, user_id=None, session_id=None, scope="all", limit=10, **kwargs)
```

作用：

- 忘记一条或一批记忆
- 可以按 ID 删除，也可以按查询删除

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `memory_id` | 否 | 直接删除指定 ID |
| `query` | 否 | 用查询命中一批记忆再删除 |
| `user_id` | 否 | 用户上下文 |
| `session_id` | 否 | session 上下文 |
| `scope` | 否 | `session` / `long-term` / `all` |
| `limit` | 否 | 查询删除时最多处理多少条 |
| `agent_id` | 否 | agent 过滤条件 |
| `run_id` | 否 | run 过滤条件 |
| `actor_id` | 否 | actor 过滤条件 |
| `role` | 否 | role 过滤条件 |
| `filters` | 否 | 过滤 DSL |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `message` | 删除结果提示 |
| `id` | 按 ID 删除时返回单个 ID |
| `ids` | 按 query 删除时返回 ID 列表 |

### 2.9 `history(memory_id)`

```python
store.history(memory_id)
```

作用：

- 查看某条记忆的事件历史

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `memory_id` | 是 | 记忆 ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `list[dict]` | 返回事件列表；每条通常包含 `id`、`memory_id`、`event_type`、`payload`、`created_at` |

---

## 3. `AIMemory`：检索与解释接口

### 3.1 `query(query, **kwargs)`

```python
store.query(query, user_id=None, session_id=None, agent_id=None, run_id=None, actor_id=None, role=None, domains=None, filters=None, limit=10, threshold=0.0)
```

作用：

- 在多个域之间做统一检索

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `query` | 是 | 查询文本 |
| `user_id` | 否 | 用户上下文 |
| `session_id` | 否 | session 上下文 |
| `agent_id` | 否 | agent 上下文 |
| `run_id` | 否 | run 上下文 |
| `actor_id` | 否 | actor 上下文 |
| `role` | 否 | role 上下文 |
| `domains` | 否 | 指定要查的域；不传时自动路由 |
| `filters` | 否 | 过滤 DSL |
| `limit` | 否 | 返回条数 |
| `threshold` | 否 | 最低分过滤 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `results` | 多域结果列表 |
| `route` | 实际走过的域顺序 |

### 3.2 `explain_recall(query, **kwargs)`

```python
store.explain_recall(query, **kwargs)
```

作用：

- 只解释“系统准备怎么召回”
- 不真正执行检索结果返回

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `query` | 是 | 查询文本 |
| `user_id` | 否 | 用户上下文 |
| `session_id` | 否 | session 上下文 |
| `agent_id` | 否 | agent 上下文 |
| `run_id` | 否 | run 上下文 |
| `actor_id` | 否 | actor 上下文 |
| `role` | 否 | role 上下文 |
| `preferred_scope` | 否 | 指定优先查 `session` 或 `long-term` |
| `limit` | 否 | 主阶段召回条数 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `strategy_scope` | 当前策略作用域 |
| `strategy_name` | 召回策略名 |
| `query_profile` | 查询画像 |
| `handoff_domains` | 可能需要补查的域 |
| `graph_enrichment` | 是否启用图增强 |
| `policy_notes` | 当前策略说明 |
| `stages` | 多阶段召回计划 |

---

## 4. `AIMemory`：session、run、知识和技能接口

### 4.1 `create_session(user_id, session_id=None, **kwargs)`

```python
store.create_session(user_id, session_id=None, **kwargs)
```

作用：

- 创建一个 session

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `user_id` | 是 | 用户 ID |
| `session_id` | 否 | 自定义 session ID；不传时自动生成 |
| `agent_id` | 否 | agent ID |
| `title` | 否 | 会话标题 |
| `ttl_seconds` | 否 | TTL 秒数 |
| `metadata` | 否 | 扩展元数据 |
| `status` | 否 | 会话状态，默认 `active` |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Session 对象` | 返回创建后的 session 数据 |

### 4.2 `append_turn(session_id, role, content, **kwargs)`

```python
store.append_turn(session_id, role, content, **kwargs)
```

作用：

- 向 session 追加一轮消息

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `role` | 是 | 角色名，如 `user`、`assistant` |
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
| `Turn 对象` | 返回追加后的对话轮次 |

### 4.3 `start_run(user_id, goal, **kwargs)`

```python
store.start_run(user_id, goal, **kwargs)
```

作用：

- 创建一次执行 run

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
| `Run 对象` | 返回 run 数据 |

### 4.4 `ingest_document(title, text, **kwargs)`

```python
store.ingest_document(title, text, **kwargs)
```

作用：

- 把文本写入 knowledge 域
- 会自动切块并投影到索引后端

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `title` | 是 | 文档标题 |
| `text` | 是 | 文档正文 |
| `user_id` | 否 | 用户 ID |
| `source_id` | 否 | 指定知识源 ID |
| `source_name` | 否 | 知识源名称，默认 `manual` |
| `version_label` | 否 | 版本号标签 |
| `metadata` | 否 | 扩展元数据 |
| `chunk_size` | 否 | 分块大小 |
| `overlap` | 否 | 分块重叠字符数 |
| `document_id` | 否 | 自定义文档 ID |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Document 对象` | 返回文档对象 |
| `versions` | 文档版本列表 |
| `chunk_count` | 当前分块数量 |

### 4.5 `register_skill(name, description, **kwargs)`

```python
store.register_skill(name, description, **kwargs)
```

作用：

- 注册一项技能

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 技能名 |
| `description` | 是 | 技能描述 |
| `owner_id` | 否 | 技能拥有者 |
| `prompt_template` | 否 | 提示模板 |
| `workflow` | 否 | 工作流定义 |
| `schema` | 否 | 输入输出 schema |
| `version` | 否 | 版本号，默认 `0.1.0` |
| `tools` | 否 | 绑定工具列表 |
| `tests` | 否 | 技能测试样例 |
| `topics` | 否 | 主题标签 |
| `assets` | 否 | 附加资源 |
| `status` | 否 | 技能状态，默认 `draft` |
| `metadata` | 否 | 扩展元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `Skill 对象` | 返回技能对象 |
| `versions` | 版本列表 |
| `bindings` | 工具绑定列表 |
| `tests` | 测试样例列表 |

### 4.6 `archive_session(session_id, **kwargs)`

```python
store.archive_session(session_id, **kwargs)
```

作用：

- 把整个 session 归档

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

---

## 5. `AIMemory`：治理与运维接口

### 5.1 `promote_session_memories(session_id, **kwargs)`

```python
store.promote_session_memories(session_id, **kwargs)
```

作用：

- 从 session memory 里筛选值得保留的内容，晋升到长期记忆

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `user_id` | 否 | 用户 ID |
| `agent_id` | 否 | agent ID |
| `run_id` | 否 | run ID |
| `limit` | 否 | 最多考察多少条 session memory |
| `min_importance` | 否 | 晋升的最低重要度 |
| `include_memory_types` | 否 | 只晋升这些类型 |
| `force` | 否 | 是否强制执行 |
| `archive_after_promotion` | 否 | 晋升后是否把源记忆标为 archived |
| `metadata` | 否 | 额外附加到晋升结果的元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `source_count` | 被选中的源记忆数量 |
| `promoted_count` | 实际晋升成功的数量 |
| `results` | 晋升动作结果列表 |
| `facts` | 被晋升的文本列表 |
| `source_ids` | 源记忆 ID 列表 |
| `skipped` | 跳过原因列表 |

### 5.2 `compress_session_context(session_id, **kwargs)`

```python
store.compress_session_context(session_id, **kwargs)
```

作用：

- 压缩长对话，生成 working memory snapshot

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `preserve_recent_turns` | 否 | 保留最近多少轮原文 |
| `min_turns` | 否 | 至少多少轮才开始压缩 |
| `max_summary_chars` | 否 | 摘要最大字符数 |
| `metadata` | 否 | snapshot 元数据 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `compressed` | 是否真的执行了压缩 |
| `session_id` | session ID |
| `turn_count` | 当前轮次数 |
| `reason` | 未压缩时的原因 |
| `compressed_turn_count` | 被压缩掉的旧轮次数 |
| `snapshot` | 生成的 snapshot 对象 |

### 5.3 `session_health(session_id)`

```python
store.session_health(session_id)
```

作用：

- 评估当前 session 是否需要治理

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
| `promotable_session_memory_count` | 当前可晋升的 session memory 数量 |
| `latest_snapshot_at` | 最近 snapshot 时间 |
| `snapshot_age_hours` | 距离最近 snapshot 的小时数 |
| `recommendations` | 建议执行的治理动作列表 |

### 5.4 `prune_session_snapshots(session_id, **kwargs)`

```python
store.prune_session_snapshots(session_id, **kwargs)
```

作用：

- 清理旧的 snapshot，只保留最近一部分

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `keep_recent` | 否 | 保留最近多少个 snapshot |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `session_id` | session ID |
| `kept` | 实际保留数量 |
| `deleted` | 实际删除数量 |
| `deleted_ids` | 被删掉的 snapshot ID 列表 |

### 5.5 `cleanup_low_value_memories(**kwargs)`

```python
store.cleanup_low_value_memories(**kwargs)
```

作用：

- 查找并归档或删除低价值记忆

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `user_id` | 否 | 用户 ID |
| `agent_id` | 否 | agent ID |
| `run_id` | 否 | run ID |
| `scope` | 否 | 默认 `long-term` |
| `limit` | 否 | 最多扫描多少条记忆 |
| `threshold` | 否 | 自定义清理阈值 |
| `archive` | 否 | 是否归档 |
| `delete` | 否 | 是否直接删除 |
| `dry_run` | 否 | 是否只预览不执行 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `planned` | 计划处理的数量 |
| `results` | `dry_run=True` 时的候选列表 |
| `threshold` | 实际使用的阈值 |
| `archived_ids` | 已归档的记忆 ID 列表 |
| `deleted_ids` | 已删除的记忆 ID 列表 |
| `skipped` | 未执行项及原因 |

### 5.6 `govern_session(session_id, **kwargs)`

```python
store.govern_session(session_id, **kwargs)
```

作用：

- 对某个 session 做一轮综合治理

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `session_id` | 是 | session ID |
| `user_id` | 否 | 用户 ID |
| `agent_id` | 否 | agent ID |
| `run_id` | 否 | run ID |
| `compact` | 否 | 是否允许压缩 |
| `promote` | 否 | 是否允许晋升 |
| `prune_snapshots` | 否 | 是否允许清理 snapshot |
| `cleanup` | 否 | 是否顺带做低价值记忆清理 |
| `cleanup_scope` | 否 | 清理的 scope |
| `cleanup_threshold` | 否 | 清理阈值 |
| `cleanup_dry_run` | 否 | 是否只预览清理计划 |
| `force` | 否 | 是否忽略推荐直接执行 |
| `compaction_kwargs` | 否 | 传给压缩逻辑的参数 |
| `promotion_kwargs` | 否 | 传给晋升逻辑的参数 |
| `prune_kwargs` | 否 | 传给 snapshot 清理的参数 |
| `cleanup_kwargs` | 否 | 传给低价值清理逻辑的参数 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `session_id` | session ID |
| `health_before` | 治理前的健康状态 |
| `actions` | 实际执行的动作列表 |
| `compaction` | 压缩结果，可选 |
| `promotion` | 晋升结果，可选 |
| `snapshot_prune` | snapshot 清理结果，可选 |
| `cleanup` | 低价值记忆清理结果，可选 |
| `health_after` | 治理后的健康状态 |

### 5.7 `project(limit=None)`

```python
store.project(limit=None)
```

作用：

- 手动处理 outbox，把主库里的待投影事件同步到索引和图后端

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| `limit` | 否 | 本次最多处理多少条事件 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `processed` | 处理成功的事件数量 |
| `failed` | 处理失败的事件数量 |
| `event_ids` | 成功处理的事件 ID 列表 |

### 5.8 `describe_capabilities()`

```python
store.describe_capabilities()
```

作用：

- 查看当前 Provider、Backend 和 Worker 的能力描述

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| 无 | - | 无入参 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `llm` | LLM Provider capability |
| `vision` | Vision Provider capability |
| `extractor` | 抽取器 capability |
| `planner` | 规划器 capability |
| `recall_planner` | 召回规划器 capability |
| `reranker` | 重排器 capability |
| `index_backend` | 索引后端 capability |
| `graph_backend` | 图后端 capability |
| `workers` | worker 能力集合 |
| `governance` | 治理规则说明 |
| `memory_type_policy` | 各类记忆策略说明 |

### 5.9 `close()`

```python
store.close()
```

作用：

- 关闭底层连接

参数表：

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| 无 | - | 无入参 |

返回表：

| 返回字段 | 说明 |
| --- | --- |
| `None` | 无返回值 |

---

## 6. `AsyncAIMemory`

`AsyncAIMemory` 目前是对同步实现的轻量异步包装。  
返回结构和同步版一致，主要差别是调用方式需要 `await`。

### 6.1 方法对应表

| 异步方法 | 对应同步方法 | 说明 |
| --- | --- | --- |
| `await add(...)` | `add(...)` | 自动抽取记忆 |
| `await search(...)` | `search(...)` | 检索记忆 |
| `await memory_store(...)` | `memory_store(...)` | 显式写入记忆 |
| `await query(...)` | `query(...)` | 多域检索 |
| `await get(...)` | `get(...)` | 获取单条记忆 |
| `await promote_session_memories(...)` | `promote_session_memories(...)` | 晋升 session memory |
| `await compress_session_context(...)` | `compress_session_context(...)` | 压缩会话上下文 |
| `await session_health(...)` | `session_health(...)` | 查看 session 健康状态 |
| `await prune_session_snapshots(...)` | `prune_session_snapshots(...)` | 清理旧 snapshot |
| `await cleanup_low_value_memories(...)` | `cleanup_low_value_memories(...)` | 清理低价值记忆 |
| `await govern_session(...)` | `govern_session(...)` | 综合治理 |
| `await explain_recall(...)` | `explain_recall(...)` | 解释召回计划 |
| `await describe_capabilities()` | `describe_capabilities()` | 查看能力描述 |
| `await close()` | `close()` | 关闭连接 |

### 6.2 注意事项

| 项目 | 说明 |
| --- | --- |
| 上下文管理 | 当前没有 `async with` |
| 关闭方式 | 使用完后要手动 `await store.close()` |
| 返回结构 | 与同步版保持一致 |

---

## 7. 过滤 DSL

很多 facade 接口都支持 `filters`，尤其是：

- `memory_list()`
- `search()`
- `memory_search()`
- `query()`

### 7.1 支持的逻辑组合

| 关键字 | 说明 |
| --- | --- |
| `AND` | 所有条件同时满足 |
| `OR` | 任意条件满足即可 |
| `NOT` | 条件取反 |

### 7.2 支持的比较操作

| 操作符 | 说明 |
| --- | --- |
| `eq` | 等于 |
| `ne` | 不等于 |
| `in` | 在某个集合内 |
| `nin` | 不在某个集合内 |
| `gt` | 大于 |
| `gte` | 大于等于 |
| `lt` | 小于 |
| `lte` | 小于等于 |
| `contains` | 字符串包含 |
| `icontains` | 忽略大小写的包含 |
| `*` | 字段存在即可 |

### 7.3 常见字段路径

| 字段路径 | 说明 |
| --- | --- |
| `memory_type` | 记忆类型 |
| `scope` | 记忆范围 |
| `actor_id` | 角色实例 ID |
| `role` | 角色名 |
| `metadata.topic` | metadata 中的 topic |
| `metadata.actor_id` | metadata 中的 actor_id |
| `metadata.role` | metadata 中的 role |

### 7.4 过滤示例

```python
filters = {
    "AND": [
        {"memory_type": {"eq": "preference"}},
        {"metadata.topic": {"contains": "style"}},
        {"actor_id": {"eq": "planner"}},
    ]
}
```

---

## 8. 示例：公开接口常见用法

### 8.1 基础记忆流

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    # 1）先用 add() 自动抽取记忆
    add_result = store.add(
        [
            {"role": "user", "content": "用户偏好中文回复，并且喜欢结构化答案。"},
            {"role": "assistant", "content": "好的，我会优先使用中文和结构化表达。"},
        ],
        user_id="user-1",
        session_id="session-1",
        infer=True,
    )

    # 2）再显式写入一条长期记忆
    memory = store.memory_store(
        "用户偏好 Markdown 列表输出。",
        user_id="user-1",
        long_term=True,
        memory_type="preference",
    )

    # 3）按 ID 读取
    fetched = store.get(memory["id"])

    # 4）列出记忆
    listed = store.memory_list(user_id="user-1", scope="all", limit=20)

    # 5）搜索记忆
    searched = store.search("用户喜欢什么输出风格", user_id="user-1", top_k=5)

    # 6）更新记忆
    updated = store.update(memory["id"], text="用户偏好 Markdown 列表输出，并且希望回答尽量简洁。")

    # 7）查看历史
    history = store.history(memory["id"])

    print(add_result)
    print(fetched)
    print(listed)
    print(searched)
    print(updated)
    print(history)
```

### 8.2 多域检索与治理

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    # 创建 session
    store.create_session(user_id="user-2", session_id="session-2", agent_id="agent-2")

    # 写入对话轮次
    store.append_turn("session-2", "user", "请帮我设计一套记忆层。", user_id="user-2")
    store.append_turn("session-2", "assistant", "好的，我会同时考虑 memory、knowledge 和 archive。", user_id="user-2")

    # 写入知识和技能
    store.ingest_document(
        title="Memory Notes",
        text="一个完整的记忆层通常需要 memory、knowledge、archive 三个域协同。",
        user_id="user-2",
        source_name="notes",
    )
    store.register_skill(
        name="memory_router",
        description="根据问题类型把查询路由到不同域。",
        tools=["query", "search"],
        topics=["memory", "knowledge", "archive"],
        status="active",
    )

    # 多域查询
    query_result = store.query(
        "这个记忆层应该查哪些域",
        user_id="user-2",
        session_id="session-2",
        limit=10,
    )

    # 解释召回
    recall = store.explain_recall(
        "刚才这个会话发生了什么",
        user_id="user-2",
        session_id="session-2",
    )

    # 查看并执行治理
    health = store.session_health("session-2")
    governance = store.govern_session("session-2", user_id="user-2", cleanup=True, cleanup_dry_run=True, force=True)

    print(query_result)
    print(recall)
    print(health)
    print(governance)
```

### 8.3 异步示例

```python
import asyncio

from aimemory import AsyncAIMemory


async def main():
    store = AsyncAIMemory({"root_dir": ".aimemory-demo"})
    try:
        # 异步写入记忆
        await store.add(
            [
                {"role": "user", "content": "用户喜欢中文回复。"},
                {"role": "assistant", "content": "好的，我会优先使用中文。"},
            ],
            user_id="async-user",
        )

        # 异步检索
        result = await store.search("中文回复", user_id="async-user", top_k=5)

        # 异步查看 capability
        capabilities = await store.describe_capabilities()

        print(result)
        print(capabilities)
    finally:
        # 当前没有 async with，需要手动关闭
        await store.close()


asyncio.run(main())
```
