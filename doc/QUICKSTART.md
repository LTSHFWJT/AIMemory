# AIMemory Quickstart

这份文档只覆盖当前仓库已经实现的能力，目标是让你在几分钟内把 `aimemory` 接进一个多 agent 协作 runtime。

## 1. 打开数据库

```python
from aimemory import AIMemory

db = AIMemory.open(".aimemory-demo")
```

如果你要覆盖默认配置：

```python
from aimemory import AIMemory, MemoryConfig

db = AIMemory(
    MemoryConfig(
        root_dir=".aimemory-demo",
        auto_flush=True,
        working_memory_limit=64,
    )
)
```

## 2. 定义 scope

所有 durable memory 都是 scope-first 的。推荐先固定一个 `Scope`：

```python
from aimemory import Scope

scope = Scope(
    workspace_id="ws.alpha",
    project_id="proj.release",
    user_id="user-1",
    agent_id="planner",
    session_id="sess-001",
)
```

如果一个组件会长期复用这组 scope，直接拿 scoped wrapper：

```python
scoped = db.scoped(scope)
```

## 3. 写入长期记忆

### 单条写入

```python
record = scoped.put(
    text="用户喜欢先给结论，再给步骤，最后补风险。",
    kind="preference",
    importance=0.92,
)
```

### 批量写入

```python
records = scoped.put_many(
    [
        {"text": "SQLite 是 durable source of truth。", "kind": "fact"},
        {"text": "LMDB 保存 hot state 和 working memory。", "kind": "fact"},
    ]
)
```

`put_many()` 会在一个 SQLite 事务里完成整批写入。

### versioned memory

`profile / preference / entity` 会按 `fact_key` 维护版本链：

```python
scoped.put(
    text="用户偏好短答案。",
    kind="preference",
    fact_key="style.answer",
)

updated = scoped.put(
    text="用户偏好短答案，并先给一行结论。",
    kind="preference",
    fact_key="style.answer",
)
```

第二次写入不会创建新 head，而是 supersede 到同一个 head 的新 version。

## 4. 使用 working memory

`working memory` 放在 LMDB，适合保存最近对话或临时上下文：

```python
scoped.working_append("user", "这次发布需要一份回滚清单。")
scoped.working_append("assistant", "先列出数据库和服务回滚步骤。")

snapshot = scoped.working_snapshot()
```

工作记忆会优先参与检索。

## 5. 检索

### 简单搜索

```python
hits = scoped.search("回答风格偏好", top_k=5)
```

### typed query

```python
from aimemory import SearchQuery

result = scoped.query(
    SearchQuery(
        query="发布相关的高优先级记忆",
        top_k=5,
        filters={
            "kind": {"in": ["fact", "preference"]},
            "tier": {"in": ["active", "core"]},
            "importance": {"gte": 0.8},
        },
    )
)

for hit in result.hits:
    print(hit.head_id, hit.score, hit.text)
```

搜索路径：

1. 先查 LMDB working memory
2. 再由 `RetrievalGate` 决定是否进入长期记忆
3. 长期记忆用 SQLite FTS5 + LanceDB hybrid retrieval
4. 可选经过 `Reranker`

## 6. 导入与 ingestion

### records

```python
scoped.ingest_records(
    [
        {"text": "LanceDB 负责向量索引。", "kind": "fact"},
        {"text": "用户偏好结论优先。", "kind": "preference", "fact_key": "style.answer"},
    ]
)
```

### JSONL

```python
scoped.ingest_jsonl("imports/memory.jsonl")
```

### messages + extractor

```python
class DemoExtractor:
    def extract(self, messages, scope):
        return [
            {
                "text": " | ".join(item["content"] for item in messages if item.get("content")),
                "kind": "summary",
                "source_type": "message_batch",
            }
        ]


db = AIMemory.open(".aimemory-extractor", extractor=DemoExtractor())
db.ingest_messages(
    scope=scope,
    messages=[
        {"role": "user", "content": "需要简洁的发布说明。"},
        {"role": "assistant", "content": "会先给摘要再给步骤。"},
    ],
)
```

## 7. 查看历史、删除与恢复

```python
history = scoped.history(record["head_id"])
archived = scoped.archive(record["head_id"])
restored_archive = scoped.restore_archive(record["head_id"])
deleted = scoped.delete(record["head_id"])
restored = scoped.restore(record["head_id"])
```

`history()` 会返回：

- `versions`
- `events`

其中 `versions[*].state` 是版本视图状态；`superseded` 只会出现在这里或 package export 的版本视图里。
`archive()` 后记录默认不会再出现在普通搜索结果里，`restore_archive()` 会重新排入向量重建任务。

## 8. 导出与迁移

### 快照级导出

```python
scoped.export_jsonl("exports/memory.jsonl")
scoped.import_jsonl("exports/memory.jsonl")
```

这条链路只处理“当前记录视图”。

### 历史级导出

```python
package_info = scoped.export_package("exports/history-package")
stats = scoped.import_package("exports/history-package")
```

package 目录包含：

- `manifest.json`
- `heads.jsonl`
- `versions.jsonl`
- `chunks.jsonl`
- `events.jsonl`
- `links.jsonl`
- package 会保留 archived / deleted head 状态，以及 version 级 `state` 投影。

这条链路会保留 head/version/chunk/history 结构，并在导入后重建向量索引任务。

## 9. 维护操作

### flush

```python
stats = scoped.flush()
```

`flush()` 会：

- 刷出 outbox 向量任务
- 刷回 access delta
- 执行 lifecycle 调整

### lifecycle

```python
stats = scoped.run_lifecycle()
```

### recovery

```python
stats = scoped.recover()
```

### reindex / compact

```python
count = scoped.reindex()
scoped.compact()
```

## 10. 关闭资源

```python
db.close()
```

或者：

```python
from aimemory import AIMemory

with AIMemory.open(".aimemory-demo") as db:
    db.put(scope=scope, text="临时写入", kind="fact")
```

## 常见建议

- runtime 内高频调用推荐先拿 `scoped = db.scoped(scope)`
- 需要更稳定的结果语义时，优先用 `query()` 而不是 `search()`
- 如果调用方已经有向量，可以在 `put(..., vector=[...])` 时直接传入，避免该条记录后续重复 document embedding
- 如果你要迁移完整历史，优先用 `export_package()` / `import_package()`
