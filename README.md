# AIMemory

`AIMemory` 正在按 [selfdoc/multi-agent-storage-design.md](e:/TraeProjects/AIMemory/selfdoc/multi-agent-storage-design.md) 重构为一个面向多 agent 协同平台的本地优先存储内核。

当前核心架构：

- `SQLite`：事实源、版本链、FTS5、审计、outbox
- `LMDB`：工作记忆、去重指纹、访问增量、查询缓存、任务镜像
- `LanceDB`：向量索引与语义召回

## 核心对象

- `MemoryDB`
- `ScopedMemoryDB`
- `Scope`
- `SearchQuery`
- `SearchResult`
- `HashEmbedder`
- `Extractor / RetrievalGate / Reranker`

为保持项目名连续性，`AIMemory` 是 `MemoryDB` 的别名。

## 安装

```bash
pip install -e .
```

## 快速开始

```python
from aimemory import AIMemory, Scope

db = AIMemory.open(".aimemory-demo")

scope = Scope(
    workspace_id="ws.alpha",
    project_id="proj.release",
    user_id="user-1",
    agent_id="planner",
    session_id="sess-001",
)

record = db.put(
    scope=scope,
    text="用户喜欢先给结论，再给步骤。",
    kind="preference",
    importance=0.92,
)

hits = db.search(
    scope=scope,
    query="回答风格偏好",
    top_k=5,
)

current = db.get(scope=scope, head_id=record["head_id"])
print(current["text"])
print(hits[0]["text"])
```

## 当前能力

- scoped durable memory write
- `profile / preference / entity` supersede 版本链
- SQLite FTS5 + LanceDB hybrid retrieval
- working-memory-first 检索
- `RetrievalGate` / `Reranker` 可插拔扩展
- outbox 驱动的向量索引刷新
- 启动时恢复 pending job 与 access delta
- automatic `active / core / cold` tier lifecycle
- soft delete / restore

## 当前公开 API

- `AIMemory.open(root_dir, embedder=None, reranker=None, retrieval_gate=None)`
- `put(scope=..., ...)`
- `put_many(scope=..., items=[...])`
- `ingest_records(scope=..., records=[...])`
- `ingest_jsonl(scope=..., path=...)`
- `ingest_messages(scope=..., messages=[...], extractor=None)`
- `get(scope=..., head_id=...)`
- `list(scope=..., filters=None, limit=100)`
- `search(scope=..., query=..., top_k=10, filters=None)`
- `history(scope=..., head_id=...)`
- `delete(scope=..., head_id=...)`
- `restore(scope=..., head_id=...)`
- `feedback(scope=..., head_id=..., text=...)`
- `working_append(scope=..., role=..., content=..., metadata=None)`
- `working_snapshot(scope=..., limit=None)`
- `export_records(scope=..., filters=None, limit=1000, state="active")`
- `export_jsonl(scope=..., path=None, filters=None, limit=1000, state="active")`
- `import_jsonl(path=..., scope=None)`
- `flush()`
- `run_lifecycle()`
- `recover()`
- `compact()`
- `reindex()`
- `stats()`
- `scoped(scope)`

`ScopedMemoryDB` 会绑定固定 `Scope`，因此同名方法不再需要重复传入 `scope`。

## 测试

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```
