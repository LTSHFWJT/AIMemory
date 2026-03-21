# AIMemory Facade API

这个文件名来自旧文档体系，但当前项目里已经没有旧版那套 `memory.api.*` façade。

现在真正的 façade 很简单：

- `MemoryDB`
- `ScopedMemoryDB`
- 顶层别名 `AIMemory` / `ScopedAIMemory`

也就是说，协同平台直接对接的就是这两个对象，而不是一层更深的 session/context/handoff service。

## 1. 推荐接入面

按优先级排序：

1. `AIMemory.open(...)`
2. `db.scoped(scope)`
3. `scoped.put(...) / scoped.search(...) / scoped.query(...)`
4. `scoped.ingest_*`
5. `scoped.export_* / import_*`
6. `scoped.flush() / recover() / run_lifecycle()`

不建议平台代码直接依赖：

- `SQLiteCatalog`
- `LMDBHotStore`
- `LanceVectorStore`
- `MemoryWritePath`
- `MemoryReadPath`
- `MaintenanceCoordinator`
- `RecoveryCoordinator`

这些类是内核实现细节，不是稳定 façade。

## 2. `AIMemory` / `MemoryDB`

最常见的初始化：

```python
from aimemory import AIMemory

db = AIMemory.open(".aimemory")
```

注入自定义组件：

```python
db = AIMemory(
    {"root_dir": ".aimemory"},
    embedder=my_embedder,
    extractor=my_extractor,
    reranker=my_reranker,
    retrieval_gate=my_gate,
)
```

适合直接用 `MemoryDB` 的场景：

- 平台根对象单例
- 批处理导入
- 多 scope 共用一个数据库实例
- 运维脚本或迁移脚本

## 3. `ScopedMemoryDB`

如果同一个 agent、workspace 或 session 会频繁复用同一组 scope，优先拿 scoped wrapper：

```python
from aimemory import Scope

scope = Scope(
    workspace_id="ws.alpha",
    project_id="proj.release",
    user_id="user-1",
    agent_id="planner",
    session_id="sess-001",
)

scoped = db.scoped(scope)
```

后续调用：

```python
scoped.put(text="用户喜欢短答案。", kind="preference")
hits = scoped.search("回答偏好")
result = scoped.query("回答偏好", top_k=5)
```

适合：

- 单 agent runtime
- 单 session orchestration
- 某个 workspace 或 project 的长期上下文对象

## 4. façade 层应该怎么用

### 写入

```python
scoped.put(...)
scoped.put_many([...])
scoped.ingest_records([...])
scoped.ingest_jsonl(path)
scoped.ingest_messages(messages, extractor=...)
```

### 检索

简单结果：

```python
hits = scoped.search("查询词", top_k=5)
```

结构化结果：

```python
from aimemory import SearchQuery

result = scoped.query(
    SearchQuery(
        query="查询词",
        top_k=5,
        filters={"tier": {"in": ["active", "core"]}},
    )
)
```

### 生命周期与恢复

```python
scoped.flush()
scoped.run_lifecycle()
scoped.recover()
scoped.reindex()
scoped.compact()
```

### 迁移

```python
scoped.export_jsonl("exports/current.jsonl")
scoped.export_package("exports/history-package")
```

## 5. search 和 query 的选择

`search()`：

- 返回 `list[dict]`
- 适合脚本、模板层、快速接入

`query()`：

- 返回 `SearchResult`
- 带 `used_working_memory`
- 带 `used_longterm_memory`
- 更适合平台编排层和调试链路

推荐：

- 平台内部统一调用优先用 `query()`
- 面向外部简单接口时再暴露 `search()`

## 6. façade 层的插件入口

当前 façade 允许注入四类组件：

### Embedder

控制 document/query embedding。

### Extractor

控制 `ingest_messages()` 如何把消息批转成 `MemoryDraft`。

### RetrievalGate

控制某次 query 是否进入长期记忆。

### Reranker

控制召回后的重排。

## 7. 当前 façade 不包含什么

与旧文档相比，当前 façade 明确不包含：

- `memory.api.session.*`
- `memory.api.context.*`
- `memory.api.handoff.*`
- `memory.api.reflection.*`
- `memory.events.*`
- `AsyncAIMemory`
- 平台 LLM 绑定接口
- MCP adapter

如果未来这些能力重新加入，也会以“在当前 `MemoryDB` 之上增量扩展”的方式出现，而不是恢复旧版大体量分层。

## 8. 对平台接入的建议

推荐模式：

1. 平台初始化一个 `MemoryDB`
2. 每个 agent / session / run 派生一个 `ScopedMemoryDB`
3. 写入使用 `put` / `put_many` / `ingest_messages`
4. 检索统一走 `query()`
5. 周期性或关键节点调用 `flush()`
6. 崩溃恢复或重启后调用 `recover()`，或依赖默认 `recover_on_open=True`

不推荐模式：

1. 平台层直接拼 SQL
2. 直接读写 LMDB 内部 DB
3. 把 LanceDB 当作 truth source
4. 直接 new 内部 pipeline 协调器作为外部编排入口
