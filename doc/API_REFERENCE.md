# AIMemory API Reference

## 顶层导出

```python
from aimemory import (
    AIMemory,
    MemoryDB,
    ScopedMemoryDB,
    Scope,
    MemoryDraft,
    SearchHit,
    SearchQuery,
    SearchResult,
    HashEmbedder,
    Extractor,
    RetrievalGate,
    Reranker,
)
```

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
- `scope.path`
- `scope.key`

## 类型对象

### `MemoryDraft`

```python
draft = {
    "text": "用户喜欢先给结论。",
    "kind": "preference",
    "layer": "longterm",
    "tier": "active",
    "importance": 0.9,
    "confidence": 0.8,
    "fact_key": "style.answer",
    "metadata": {"channel": "chat"},
    "source_type": "message",
    "source_ref": "msg-1",
}
```

### `SearchQuery`

```python
from aimemory import SearchQuery

query = SearchQuery(
    query="回答风格偏好",
    top_k=5,
    filters={"tier": {"in": ["active", "core"]}},
)
```

### `SearchResult`

```python
from aimemory import SearchResult
```

包含：

- `query`
- `hits`
- `used_working_memory`
- `used_longterm_memory`

### `SearchHit`

搜索结果字段：

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

## 可插拔协议

### `Extractor`

```python
from aimemory import Extractor

class MyExtractor:
    def extract(self, messages, scope):
        return [{"text": "提取出的记忆", "kind": "fact"}]
```

### `RetrievalGate`

```python
from aimemory import RetrievalGate

class MyGate:
    def should_retrieve(self, query, scope):
        return "历史" in query or "remember" in query.lower()
```

### `Reranker`

```python
from aimemory import Reranker

class MyReranker:
    def rerank(self, query, docs, top_k):
        return [(index, 1.0) for index in range(min(top_k, len(docs)))]
```

## MemoryDB

### 打开数据库

```python
db = AIMemory.open(".aimemory")
```

或：

```python
from aimemory import MemoryDB, MemoryConfig

db = MemoryDB(
    MemoryConfig(root_dir=".aimemory"),
    reranker=my_reranker,
    retrieval_gate=my_gate,
)
```

### `put`

```python
record = db.put(
    scope=scope,
    text="用户喜欢先给结论，再给步骤。",
    kind="preference",
    layer="longterm",
    tier="active",
    importance=0.9,
    confidence=0.8,
    fact_key="style.answer",
    metadata={"channel": "chat"},
    source_type="message",
    source_ref="msg-1",
)
```

### `put_many`

```python
records = db.put_many(
    scope=scope,
    items=[
        {"text": "使用 SQLite 作为事实源。", "kind": "fact"},
        {"text": "使用 LMDB 维护工作记忆。", "kind": "fact"},
    ],
)
```

`put_many()` now uses a single SQLite transaction for the whole batch and applies LMDB hot-state updates in bulk after commit.

### `ingest_records`

```python
records = db.ingest_records(
    scope=scope,
    records=[
        {"text": "SQLite stores durable metadata.", "kind": "fact"},
        {"text": "LMDB stores hot working state.", "kind": "fact"},
    ],
)
```

### `ingest_jsonl`

```python
records = db.ingest_jsonl(
    scope=scope,
    path="imports/memory.jsonl",
)
```

### `ingest_messages`

```python
records = db.ingest_messages(
    scope=scope,
    messages=[
        {"role": "user", "content": "Need concise rollout notes."},
        {"role": "assistant", "content": "Will keep the answer short."},
    ],
    extractor=my_extractor,
)
```

### `get`

```python
record = db.get(scope=scope, head_id=head_id)
```

### `list`

```python
records = db.list(
    scope=scope,
    filters={"kind": {"in": ["fact", "preference"]}},
    limit=50,
)
```

支持的 filter 操作：

- `eq`
- `ne`
- `in`
- `gte`
- `lte`
- `contains`

### `search`

```python
hits = db.search(
    scope=scope,
    query="回答风格偏好",
    top_k=5,
    filters={"tier": {"in": ["active", "core"]}},
)
```

搜索路径：

- 先查 LMDB `working_set / turn_buffer`
- 再由 `RetrievalGate` 决定是否进入长期记忆检索
- 长期记忆检索采用 SQLite FTS5 + LanceDB hybrid retrieval
- 可选再经过 `Reranker`

### `history`

```python
history = db.history(scope=scope, head_id=head_id)
```

返回：

- `versions`
- `events`

### `delete`

```python
deleted = db.delete(scope=scope, head_id=head_id)
```

### `restore`

```python
restored = db.restore(scope=scope, head_id=head_id)
```

### `feedback`

```python
updated = db.feedback(
    scope=scope,
    head_id=head_id,
    text="新的修正内容",
)
```

### `working_append`

```python
db.working_append(
    scope=scope,
    role="user",
    content="需要一个发布 checklist",
    metadata={"source": "chat"},
)
```

### `working_snapshot`

```python
snapshot = db.working_snapshot(scope=scope, limit=20)
```

### `export_records`

```python
records = db.export_records(
    scope=scope,
    filters={"kind": {"in": ["fact", "preference"]}},
    limit=100,
)
```

### `export_jsonl`

```python
result = db.export_jsonl(
    scope=scope,
    path="exports/memory.jsonl",
)
```

Returns a small result object with `path` and `count`.

### `import_jsonl`

```python
records = db.import_jsonl(
    path="exports/memory.jsonl",
    scope=scope,
)
```

If `scope` is omitted, the importer uses the embedded `scope` from exported records.

### `flush`

```python
stats = db.flush()
```

执行：

- outbox job flush
- access delta flush
- lifecycle tier rebalance

### `run_lifecycle`

```python
stats = db.run_lifecycle()
```

Executes active/core/cold tier promotion and demotion, then refreshes vector rows for changed heads.

### `recover`

```python
stats = db.recover()
```

执行启动补偿恢复并重放 pending/failed/running 的索引任务，同时刷回未提交的 access delta。

### `compact`

```python
db.compact()
```

### `reindex`

```python
count = db.reindex()
```

### `stats`

```python
stats = db.stats()
```

当前返回：

- `heads`
- `versions`
- `chunks`
- `pending_jobs`

### `scoped`

```python
scoped = db.scoped(scope)
```

## ScopedMemoryDB

```python
scoped = db.scoped(scope)

scoped.put(text="用户偏好短答案。", kind="preference")
hits = scoped.search("回答偏好")
snapshot = scoped.working_snapshot()
```

支持方法：

- `scoped(**overrides)`
- `put(**kwargs)`
- `put_many(items)`
- `ingest_records(records)`
- `ingest_jsonl(path)`
- `ingest_messages(messages, extractor=None)`
- `get(head_id)`
- `list(filters=None, limit=100)`
- `search(query, top_k=10, filters=None)`
- `history(head_id)`
- `delete(head_id)`
- `restore(head_id)`
- `feedback(head_id, text)`
- `working_append(role, content, metadata=None)`
- `working_snapshot(limit=None)`
- `export_records(filters=None, limit=1000, state="active")`
- `export_jsonl(path=None, filters=None, limit=1000, state="active")`
- `import_jsonl(path)`
- `flush()`
- `run_lifecycle()`
- `recover()`
- `compact()`
- `reindex()`
- `stats()`
