# AIMemory Maintenance & Worker Model

P0 status update:

- `worker_mode="library_only"`: no background thread; `auto_flush=True` keeps the foreground maintenance path.
- `worker_mode="embedded"`: starts an in-process maintenance thread and uses LMDB `lease` for single-leader coordination.
- access delta flush now triggers on either `flush_access_every` or `flush_access_interval_ms`.
- `worker_status()` exposes the current maintenance-thread and lease snapshot.

这个文件名来自旧文档体系，但当前项目里已经没有公开的 `services/*` / `workers/*` 包。

现在的后台处理模型是内嵌式、library-first 的：

- 写入先落 SQLite
- 向量刷新通过 SQLite outbox job 排队
- LMDB 维护 job mirror、working memory、缓存和 access delta
- 维护操作通过 `flush()` / `run_lifecycle()` / `recover()` 触发

所以这份文档描述的是“当前内部维护模型”，不是独立 worker 进程 API。

## 1. 当前组件分工

### 写入链路

- `MemoryWritePath`
- `SQLiteCatalog`
- `LMDBHotStore`

职责：

- 规范化文本
- 精确去重
- 语义去重
- 版本链维护
- chunk 切分
- outbox job 入队
- working memory / cache 更新

### 读取链路

- `MemoryReadPath`
- `SQLiteCatalog`
- `LMDBHotStore`
- `LanceVectorStore`

职责：

- working-memory-first 检索
- SQLite FTS5 + LanceDB hybrid retrieval
- `SearchQuery` / `SearchResult`
- query cache

### 维护链路

- `MaintenanceCoordinator`
- `RecoveryCoordinator`

职责：

- 刷出 outbox 向量任务
- 刷回访问增量
- tier lifecycle 调整
- 启动恢复
- reindex / compact

## 2. 写入后的后台动作

一次 `put()` / `put_many()` 之后，典型过程是：

1. 记录先写入 SQLite heads / versions / chunks
2. 为新 chunk 在 outbox 中创建 `upsert_vector` job
3. LMDB 镜像这些 job，便于快速恢复
4. 如果 `auto_flush=True`，当前调用会继续触发 `flush()`
5. `flush_jobs()` 将 chunk 写入 LanceDB

对于 supersede 或 delete，还会创建 `delete_vector` job。

## 3. outbox job 类型

当前主要 job：

- `upsert_vector`
- `delete_vector`

处理逻辑位于 `MaintenanceCoordinator.flush_jobs()`：

- `upsert_vector`
  - 取 chunk
  - 从 LMDB embedding cache 取向量
  - 没有就即时 embedding
  - upsert 到 LanceDB
- `delete_vector`
  - 从 LanceDB 删除旧 chunk

## 4. `flush()`

公开入口：

```python
stats = db.flush()
```

等价于三件事：

1. `flush_access()`
2. `run_lifecycle()`
3. `flush_jobs()`

返回结构：

- `jobs`
- `access_updates`
- `lifecycle_evaluated`
- `lifecycle_changed`
- `lifecycle_jobs`

适合：

- 批量写入后的显式收尾
- 关闭前刷盘
- 调试时手动推进维护链路

## 5. `run_lifecycle()`

公开入口：

```python
stats = db.run_lifecycle()
```

当前 tier：

- `active`
- `core`
- `cold`

生命周期依据：

- `importance`
- `confidence`
- `access_count`
- `updated_at`
- `last_accessed_at`

调整后会：

- 更新 `memory_heads.tier`
- 写入 `history_events`
- 为当前 version 的 chunks 重新 enqueue `upsert_vector`

## 6. `recover()`

公开入口：

```python
stats = db.recover()
```

恢复过程：

1. 重置 `pending / failed / running` job 为可恢复状态
2. 扫描 `embedding_state != ready` 的 chunk，补建 `upsert_vector` job
3. 重新同步 LMDB job mirror
4. 持续消费恢复后的 job，直到清空
5. 刷回 access delta

默认 `MemoryDB` 初始化时，如果 `recover_on_open=True`，会自动执行一次恢复。

## 7. `reindex()` 和 `compact()`

### reindex

```python
count = db.reindex()
```

行为：

- 删掉所有 indexable chunks 的 LanceDB 条目
- 重新 enqueue `upsert_vector`
- 立即 flush job

### compact

```python
db.compact()
```

行为：

- 先执行 `flush_all()`
- 再执行 SQLite `VACUUM`

## 8. access delta

访问计数不会每次 search 都直接写 SQLite，而是先累积在 LMDB：

- `query()` / `search()` 命中 durable head 时，增加 `access_delta`
- 达到 `flush_access_every` 阈值后自动刷回
- `flush()` / `recover()` 也会主动刷回

这样可以降低高频检索下的 SQLite 写放大。

## 9. lease 现状

`LMDBHotStore` 已经有：

```python
acquire_lease(worker_name, now_ms=..., ttl_ms=...)
```

但当前版本里它还没有接入公开的 worker loop。

也就是说，当前状态是：

- `lease` 基础设施已存在
- outbox / recovery / lifecycle 都已存在
- 但还没有对外暴露“常驻后台线程 / 多进程 worker API”

如果后续要增加嵌入式 worker，这会是直接可复用的互斥基础。

## 10. 当前没有的东西

当前仓库不包含这些公开层：

- `aimemory/services/*`
- `aimemory/workers/*`
- 独立 daemon
- HTTP job control API
- 事件总线式 scheduler

如果你看到旧文档里提到这些内容，可以直接认为那是已经删除的旧架构。

## 11. 扩展建议

如果你要在当前版本上扩展后台能力，推荐顺序：

1. 优先通过 `flush()` / `run_lifecycle()` / `recover()` 组合现有能力
2. 如果需要长驻维护，再在进程内封装一个轻量线程循环
3. 如果需要多进程互斥，复用 LMDB `lease`
4. 不要把 SQLite / LMDB / LanceDB 的内部表结构直接暴露成外部调度 API

一句话概括：当前项目是“内嵌维护模型”，不是“独立 worker 平台”。
