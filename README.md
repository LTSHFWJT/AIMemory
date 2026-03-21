# AIMemory

P0 maintenance model 已完成：

- `worker_mode="library_only"`：不启动后台线程，`auto_flush=True` 时继续使用前台同步维护路径。
- `worker_mode="embedded"`：启动进程内维护线程，并通过 LMDB `lease` 保证同一存储根目录只有一个活跃维护者。
- access flush 现在同时支持累计阈值 `flush_access_every` 和时间窗口 `flush_access_interval_ms`。
- 可通过 `worker_status()` 查看当前线程是否存活、是否持有 leader lease，以及当前 lease 快照。

`AIMemory` 是一个面向多 agent 协同平台的本地优先 memory kernel。

当前实现已经按 [selfdoc/multi-agent-storage-design.md](selfdoc/multi-agent-storage-design.md) 重构到新的轻量架构：

- `SQLite` 负责 durable source of truth
- `LMDB` 负责 working memory、缓存、访问增量、任务镜像、去重指纹
- `LanceDB` 负责向量索引与近邻召回

旧版 `aimemory` 的庞杂 `service / worker / adapter / provider / domain` 架构已不再作为当前实现基础，也不再是文档前提。

## 当前能力

- scope-first 的 `MemoryDB` / `ScopedMemoryDB` API
- `fact / profile / preference / entity / summary` 等长期记忆写入
- `profile / preference / entity` 的版本链与 supersede
- 精确去重 + 语义去重
- working-memory-first 检索
- SQLite FTS5 + LanceDB hybrid retrieval
- `SearchQuery` / `SearchResult` typed search
- `Extractor` / `RetrievalGate` / `Reranker` 可插拔
- 批量写入、批量导入、JSONL 导入
- 快照导出导入和历史级 package 导出导入
- `active / core / cold` 生命周期管理
- crash recovery、reindex、compact
- 显式 `active / archived / deleted` head 状态，以及 history/export 中的 `superseded` version 状态投影
- `procedure_version_mode` 支持 `append_only` 与 `supersede_by_fact_key`
- hybrid retrieval 评分包含 exact fact boost、scope specificity boost 和 confidence multiplier
- outbox 已扩展为 `upsert_vector / delete_vector / rebuild_vector / flush_access`

## 安装

```bash
pip install -e .
```

依赖：

- `lmdb`
- `lancedb>=0.16.0`

## 快速开始

```python
from aimemory import AIMemory, Scope, SearchQuery

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

db.working_append(
    scope=scope,
    role="user",
    content="当前在准备一次发布计划。",
)

hits = db.search(
    scope=scope,
    query="回答风格偏好",
    top_k=5,
)

result = db.query(
    scope=scope,
    search=SearchQuery(
        query="回答风格偏好",
        top_k=5,
        filters={"tier": {"in": ["active", "core"]}},
    ),
)

print(record["head_id"])
print(hits[0]["text"])
print(result.used_working_memory, result.used_longterm_memory)
```

## 存储布局

默认根目录结构：

```text
.aimemory/
  manifest.json
  catalog.sqlite3
  catalog.sqlite3-shm
  catalog.sqlite3-wal
  lmdb/
    data.mdb
    lock.mdb
  lancedb/
    memory_vectors.lance/
  backups/
  exports/
```

说明：

- `manifest.json` 描述当前存储格式、向量维度和基础后端
- `catalog.sqlite3` 保存 heads、versions、chunks、history、outbox
- `lmdb/` 保存 hot state 与缓存
- `lancedb/` 保存向量索引

## 公开对象

顶层导出：

- `AIMemory`
- `MemoryDB`
- `ScopedAIMemory`
- `ScopedMemoryDB`
- `MemoryConfig`
- `Scope`
- `MemoryDraft`
- `MemoryRecord`
- `SearchHit`
- `SearchQuery`
- `SearchResult`
- `Embedder`
- `HashEmbedder`
- `Extractor`
- `RetrievalGate`
- `Reranker`

其中：

- `AIMemory` 是 `MemoryDB` 的别名
- `ScopedAIMemory` 是 `ScopedMemoryDB` 的别名

## 公开 API 概览

`MemoryDB`：

- `open(root_dir, embedder=None, extractor=None, reranker=None, retrieval_gate=None)`
- `scoped(scope=None, **scope_overrides)`
- `put(scope=..., ...)`
- `put_many(scope=..., items=[...])`
- `ingest_records(scope=..., records=[...])`
- `ingest_jsonl(scope=..., path=...)`
- `ingest_messages(scope=..., messages=[...], extractor=None)`
- `get(scope=..., head_id=...)`
- `list(scope=..., filters=None, limit=100)`
- `search(scope=..., query=..., top_k=10, filters=None)`
- `query(scope=..., search=SearchQuery(...) | "query", top_k=None, filters=None)`
- `history(scope=..., head_id=...)`
- `delete(scope=..., head_id=...)`
- `archive(scope=..., head_id=...)`
- `restore_archive(scope=..., head_id=...)`
- `restore(scope=..., head_id=...)`
- `feedback(scope=..., head_id=..., text=...)`
- `working_append(scope=..., role=..., content=..., metadata=None)`
- `working_snapshot(scope=..., limit=None)`
- `export_records(scope=..., filters=None, limit=1000, state="active")`
- `export_jsonl(scope=..., path=None, filters=None, limit=1000, state="active")`
- `import_jsonl(path=..., scope=None)`
- `export_package(scope=..., path=None, filters=None, limit=1000, state=None)`
- `import_package(path=..., scope=None)`
- `flush()`
- `run_lifecycle()`
- `recover()`
- `compact()`
- `reindex()`
- `stats()`
- `worker_status()`
- `close()`

`ScopedMemoryDB` 会绑定固定 `Scope`，因此相同方法不再重复传入 `scope`。

状态与检索语义：

- 持久化 head 状态为 `active / archived / deleted`
- `superseded` 只作为 version 投影状态出现在 `history()` 和 `export_package()` 中，不作为 head 持久化状态
- 默认 `list()` / `search()` / `query()` 只返回 active 记录；archived 记录需要显式按 `state` 过滤或导出

## 插件协议

可插拔协议位于 [`aimemory/plugins/protocols.py`](aimemory/plugins/protocols.py)：

- `Extractor.extract(messages, scope) -> list[MemoryDraft]`
- `RetrievalGate.should_retrieve(query, scope) -> bool`
- `Reranker.rerank(query, docs, top_k) -> list[tuple[int, float]]`

向量接口位于 [`aimemory/vector/embeddings.py`](aimemory/vector/embeddings.py)：

- `Embedder.dimension`
- `Embedder.model_name`
- `Embedder.embed_texts(texts)`

默认使用本地 `HashEmbedder`，不依赖外部模型服务。

## 文档

- [Quickstart](doc/QUICKSTART.md)
- [API Reference](doc/API_REFERENCE.md)
- [Facade API](doc/facade-api.md)
- [Maintenance & Worker Model](doc/service-worker-api.md)

## 测试

```bash
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

## 当前边界

当前实现是一个 library-first memory kernel，不包含：

- 独立部署的 HTTP 服务
- 旧版 `service/*` / `worker/*` 公共 API
- 异步 façade
- 平台事件编排层
- MCP adapter 公共接口

这些能力如果后续重新引入，会基于当前轻量架构增量演进，而不是回到旧工程形态。
