# AIMemory API Reference

这份文档按当前代码实现描述 `aimemory` 的公开接口。

## 顶层导出

```python
from aimemory import (
    AIMemory,
    MemoryDB,
    ScopedAIMemory,
    ScopedMemoryDB,
    MemoryConfig,
    Scope,
    MemoryDraft,
    MemoryRecord,
    SearchHit,
    SearchQuery,
    SearchResult,
    Embedder,
    HashEmbedder,
    Extractor,
    RetrievalGate,
    Reranker,
)
```

别名关系：

- `AIMemory is MemoryDB`
- `ScopedAIMemory is ScopedMemoryDB`

## Scope

```python
from aimemory import Scope

scope = Scope(
    tenant_id="local",
    workspace_id="ws.alpha",
    project_id="proj.release",
    user_id="user-1",
    agent_id="planner",
    session_id="sess-001",
    run_id="run-001",
    namespace="default",
    visibility="private",
)
```

字段：

- `tenant_id`
- `workspace_id`
- `project_id`
- `user_id`
- `agent_id`
- `session_id`
- `run_id`
- `namespace`
- `visibility`

辅助方法：

- `Scope.from_value(value)`
- `Scope.from_record(record)`
- `scope.bind(**overrides)`
- `scope.as_dict()`
- `scope.path`
- `scope.key`

## MemoryConfig

```python
from aimemory import MemoryConfig

config = MemoryConfig(
    root_dir=".aimemory",
    vector_dim=32,
    chunk_size=480,
    chunk_overlap=64,
)
```

当前主要配置：

- `root_dir`
- `vector_dim`
- `chunk_size`
- `chunk_overlap`
- `semantic_dedupe_enabled`
- `semantic_dedupe_threshold`
- `semantic_dedupe_candidates`
- `working_memory_limit`
- `auto_flush`
- `flush_access_every`
- `flush_access_interval_ms`
- `worker_mode`
- `worker_poll_interval_ms`
- `worker_lease_ttl_ms`
- `query_cache_enabled`
- `recover_on_open`
- `recovery_batch_size`
- `retrieval_vector_weight`
- `retrieval_lexical_weight`
- `retrieval_exact_fact_weight`
- `retrieval_scope_specificity_weight`
- `retrieval_confidence_floor`
- `procedure_version_mode`
- `embedding_model`
- `lifecycle_enabled`
- `lifecycle_batch_size`
- `lifecycle_freshness_window_ms`
- `lifecycle_cold_after_ms`
- `lifecycle_core_promote_importance`
- `lifecycle_core_promote_access_count`
- `lifecycle_core_promote_score`
- `lifecycle_core_demote_score`
- `lifecycle_cold_demote_score`
- `lifecycle_cold_reactivate_score`
- `worker_mode` supports `library_only` and `embedded`
- `procedure_version_mode` supports `append_only` and `supersede_by_fact_key`
- `flush_access_interval_ms`
- `worker_poll_interval_ms`
- `worker_lease_ttl_ms`

辅助方法：

- `resolved_root()`

## 类型对象

### MemoryDraft

```python
draft = {
    "text": "用户喜欢先给结论。",
    "kind": "preference",
    "layer": "longterm",
    "tier": "active",
    "importance": 0.9,
    "confidence": 0.8,
    "vector": [0.0] * 32,
    "fact_key": "style.answer",
    "metadata": {"channel": "chat"},
    "source_type": "message",
    "source_ref": "msg-1",
}
```

### MemoryRecord

主要字段：

- `head_id`
- `version_id`
- `scope_key`
- `kind`
- `layer`
- `tier`
- `state`
- `text`
- `abstract`
- `overview`
- `fact_key`
- `importance`
- `confidence`
- `access_count`
- `created_at`
- `updated_at`
- `metadata`

### SearchQuery

```python
from aimemory import SearchQuery

query = SearchQuery(
    query="回答风格偏好",
    top_k=5,
    filters={
        "tier": {"in": ["active", "core"]},
        "importance": {"gte": 0.8},
        "created_at": {"gte": 1700000000000},
    },
)
```

### SearchHit

字段：

- `head_id`
- `version_id`
- `chunk_id`
- `kind`
- `layer`
- `tier`
- `text`
- `abstract`
- `overview`
- `score`
- `lexical_score`
- `vector_score`
- `access_count`
- `valid_from`
- `valid_to`
- `metadata`

### SearchResult

字段：

- `query`
- `hits`
- `used_working_memory`
- `used_longterm_memory`

## filters

所有 `list` / `search` / `query` / `export_*` 相关接口都使用同一套轻量 JSON 风格 filters。

支持操作：

- `eq`
- `ne`
- `in`
- `gte`
- `lte`
- `contains`

例子：

```python
filters = {
    "kind": {"in": ["fact", "preference"]},
    "tier": {"in": ["active", "core"]},
    "importance": {"gte": 0.8},
    "text": {"contains": "SQLite"},
}
```

## 插件协议

### Extractor

```python
class MyExtractor:
    def extract(self, messages, scope):
        return [{"text": "提取出的记忆", "kind": "fact"}]
```

### RetrievalGate

```python
class MyGate:
    def should_retrieve(self, query, scope):
        return "history" in query.lower()
```

### Reranker

```python
class MyReranker:
    def rerank(self, query, docs, top_k):
        return [(index, 1.0) for index in range(min(top_k, len(docs)))]
```

### Embedder

```python
class MyEmbedder:
    @property
    def dimension(self):
        return 32

    @property
    def model_name(self):
        return "my-embedder"

    def embed_texts(self, texts):
        return [[0.0] * 32 for _ in texts]
```

默认实现：

- `HashEmbedder`

## MemoryDB

### 初始化

```python
db = AIMemory.open(".aimemory")
```

或：

```python
db = AIMemory(
    {"root_dir": ".aimemory"},
    embedder=my_embedder,
    extractor=my_extractor,
    reranker=my_reranker,
    retrieval_gate=my_gate,
)
```

### scoped

```python
scoped = db.scoped(scope)
scoped = db.scoped(scope, session_id="sess-002")
```

返回 `ScopedMemoryDB`。

### put

```python
record = db.put(
    scope=scope,
    text="用户喜欢先给结论，再给步骤。",
    kind="preference",
    layer="longterm",
    tier="active",
    importance=0.9,
    confidence=0.8,
    vector=[0.0] * 32,
    fact_key="style.answer",
    metadata={"channel": "chat"},
    source_type="message",
    source_ref="msg-1",
)
```

行为：

- 规范化文本
- 精确去重
- 语义去重
- 对 versioned kinds 执行 supersede
- 切 chunk、入 SQLite、排 outbox job
- 更新 LMDB hot state

### put_many

```python
records = db.put_many(
    scope=scope,
    items=[
        {"text": "SQLite 是事实源。", "kind": "fact"},
        {"text": "LMDB 是热状态层。", "kind": "fact"},
    ],
)
```

### ingest_records

```python
records = db.ingest_records(
    scope=scope,
    records=[
        {"text": "LanceDB 是向量索引层。", "kind": "fact"},
        {"text": "用户喜欢结论优先。", "kind": "preference"},
    ],
)
```

### ingest_jsonl

```python
records = db.ingest_jsonl(
    scope=scope,
    path="imports/memory.jsonl",
)
```

### ingest_messages

```python
records = db.ingest_messages(
    scope=scope,
    messages=[
        {"role": "user", "content": "需要简洁的发布说明。"},
        {"role": "assistant", "content": "会先给摘要再给步骤。"},
    ],
    extractor=my_extractor,
)
```

如果既没有传入 `extractor=`，也没有在初始化时注入 extractor，会抛出 `ValueError`。

### get

```python
record = db.get(scope=scope, head_id=head_id)
```

### list

```python
records = db.list(
    scope=scope,
    filters={"kind": {"in": ["fact", "preference"]}},
    limit=50,
)
```

### search

```python
hits = db.search(
    scope=scope,
    query="回答风格偏好",
    top_k=5,
    filters={"tier": {"in": ["active", "core"]}},
)
```

返回 `list[dict]`，适合简单调用。

### query

```python
result = db.query(
    scope=scope,
    search=SearchQuery(
        query="回答风格偏好",
        top_k=5,
        filters={"tier": {"in": ["active", "core"]}},
    ),
)
```

也支持：

```python
result = db.query(
    scope=scope,
    search="回答风格偏好",
    top_k=5,
    filters={"tier": {"in": ["active", "core"]}},
)
```

返回 `SearchResult`。

### history

```python
history = db.history(scope=scope, head_id=head_id)
```

返回：

- `versions`
- `events`

P1 状态说明：

- `versions[*].state` 是 version 投影状态
- 持久化 head 状态只有 `active / archived / deleted`
- `superseded` 只出现在 `history()` 和 package export 的 version 视图里，不作为 head 状态落库

### delete / restore

```python
deleted = db.delete(scope=scope, head_id=head_id)
restored = db.restore(scope=scope, head_id=head_id)
```

### archive / restore_archive

```python
archived = db.archive(scope=scope, head_id=head_id)
restored = db.restore_archive(scope=scope, head_id=head_id)
```

P1 行为：

- `archive()` 只接受当前 `active` 的 head，并为当前版本排入 `delete_vector` 任务
- `restore_archive()` 只接受当前 `archived` 的 head，并为相关 chunk 排入 `rebuild_vector` 任务
- archived 记录默认不参与普通 `list()` / `search()` / `query()` 结果

### feedback

```python
updated = db.feedback(
    scope=scope,
    head_id=head_id,
    text="新的修正内容",
)
```

### working_append / working_snapshot

```python
db.working_append(
    scope=scope,
    role="user",
    content="需要一个发布 checklist",
    metadata={"source": "chat"},
)

snapshot = db.working_snapshot(scope=scope, limit=20)
```

### export_records

```python
records = db.export_records(
    scope=scope,
    filters={"kind": {"in": ["fact", "preference"]}},
    limit=100,
    state="active",
)
```

默认 `state="active"`；如果要导出 archived 或 deleted 记录，需要显式传入对应 `state`。

### export_jsonl / import_jsonl

```python
result = db.export_jsonl(
    scope=scope,
    path="exports/memory.jsonl",
)

records = db.import_jsonl(
    path="exports/memory.jsonl",
    scope=scope,
)
```

`export_jsonl()` 返回：

- `path`
- `count`

### export_package / import_package

```python
result = db.export_package(
    scope=scope,
    path="exports/history-package",
)

stats = db.import_package(
    path="exports/history-package",
    scope=scope,
)
```

导出目录包含：

- `manifest.json`
- `heads.jsonl`
- `versions.jsonl`
- `chunks.jsonl`
- `events.jsonl`
- `links.jsonl`

适合历史级迁移与完整结构保留。

P1 语义补充：

- package export 会保留 archived / deleted head 状态
- `versions.jsonl` 会写出 version 级 `state`，因此可保留 `superseded` 视图

### flush

```python
stats = db.flush()
```

返回：

- `jobs`
- `access_updates`
- `lifecycle_evaluated`
- `lifecycle_changed`
- `lifecycle_jobs`

### run_lifecycle

```python
stats = db.run_lifecycle()
```

返回：

- `evaluated`
- `changed`
- `jobs`
- `jobs_processed`

### recover

```python
stats = db.recover()
```

返回：

- `reset_jobs`
- `repaired_chunks`
- `mirrored_jobs`
- `processed_jobs`
- `access_updates`

### compact

```python
db.compact()
```

### reindex

```python
count = db.reindex()
```

### stats

```python
stats = db.stats()
```

当前返回：

- `heads`
- `versions`
- `chunks`
- `pending_jobs`

### close

```python
db.close()
```

也支持上下文管理器：

```python
with AIMemory.open(".aimemory") as db:
    ...
```

## ScopedMemoryDB

```python
scoped = db.scoped(scope)
```

支持的方法与 `MemoryDB` 基本一致，但自动继承固定 `Scope`：

- `scoped(**overrides)`
- `put(**kwargs)`
- `put_many(items)`
- `ingest_records(records)`
- `ingest_jsonl(path)`
- `ingest_messages(messages, extractor=None)`
- `get(head_id)`
- `list(filters=None, limit=100)`
- `search(query, top_k=10, filters=None)`
- `query(search, top_k=None, filters=None)`
- `history(head_id)`
- `delete(head_id)`
- `archive(head_id)`
- `restore_archive(head_id)`
- `restore(head_id)`
- `feedback(head_id, text)`
- `working_append(role, content, metadata=None)`
- `working_snapshot(limit=None)`
- `export_records(filters=None, limit=1000, state="active")`
- `export_jsonl(path=None, filters=None, limit=1000, state="active")`
- `import_jsonl(path)`
- `export_package(path=None, filters=None, limit=1000, state=None)`
- `import_package(path)`
- `flush()`
- `run_lifecycle()`
- `recover()`
- `compact()`
- `reindex()`
- `stats()`
- `worker_status()`

## P1 Notes

- `procedure_version_mode` supports `append_only` and `supersede_by_fact_key`
- Persisted head states are `active / archived / deleted`
- `superseded` is a version-projection state, not a persisted head state
- Archived records are excluded from default `list()` / `search()` / `query()` results
- Hybrid retrieval combines vector, lexical, exact fact, scope specificity, and confidence multiplier terms
- Outbox covers `upsert_vector / delete_vector / rebuild_vector / flush_access`

## 存储语义

当前实现中的关键语义：

- SQLite 是唯一 durable truth
- LMDB 不是事实源，只保存 hot state 与缓存
- LanceDB 不是事实源，只保存向量索引
- `profile / preference / entity` 使用 `fact_key` 维护版本链
- `fact` 等非 versioned kinds 默认创建新 head
- `search()` 是便捷接口，`query()` 是结构化接口

## 稳定性边界

下面这些是当前推荐的稳定公共接口：

- `aimemory.__init__` 中导出的顶层对象
- `MemoryDB` / `ScopedMemoryDB`
- `Scope`
- `MemoryConfig`
- `SearchQuery` / `SearchResult`
- `Extractor` / `RetrievalGate` / `Reranker` / `Embedder`

下面这些更偏内部实现，不建议直接依赖：

- `catalog.sqlite_store`
- `hotstore.lmdb_store`
- `pipeline.*`
- `vector.lancedb_store`
