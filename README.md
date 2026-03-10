# AIMemory

`AIMemory` 是一个给 AI Agent 用的本地化、轻量化、智能化全域存储 Python 库。

它不是云服务，不依赖额外数据库服务，不内置 LLM 推理链路。  
它更像一个可以直接嵌入 Agent Runtime 的“本地记忆内核”：

- 对上提供 MCP 友好的工具封装
- 对下默认使用本地 SQLite，并可选接入 `LanceDB` / `FAISS` / `Kuzu`
- 中间使用本地轻量算法做提取、检索、去重、压缩和归档

## 设计目标

- 轻量：默认只需要本地文件目录
- 智能：不用规则词表驱动主流程，改为本地统计与语义算法
- 全域：统一管理长期记忆、短期记忆、知识库、技能、归档和会话上下文
- 易扩展：向量库、图数据库、MCP 适配都可插件化替换

## 当前实现

当前主入口为：

- `AIMemory`
- `AsyncAIMemory`
- `AIMemoryMCPAdapter`

当前主算法栈为：

- 自适应信息蒸馏：按新颖度、信息密度、长度和多样性选取候选记忆
- 混合检索：稀疏 token 匹配 + 本地哈希向量 + 时间衰减
- 语义去重：SimHash + 轻量向量相似度联合判重
- 本地压缩：MMR 多样性重排 + 预算内摘要压缩

当前默认词嵌入配置为：

- 模型：`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- 维度：`384`
- 可替换为其他本地 `sentence-transformers` 模型
- 若本地环境未安装或模型不可用，会自动回退到轻量哈希嵌入

当前存储策略为：

- 长期记忆：`memories` + `memory_index`
- 短期记忆：`conversation_turns` + `working_memory_snapshots` + session scope memory
- 知识库：`documents` + `document_chunks` + `knowledge_chunk_index`
- 技能：`skills` + `skill_versions` + `skill_index`
- 归档：`archive_units` + `archive_summaries` + `archive_summary_index`
- 语义缓存：`semantic_index_cache`

## 后端插件

默认后端：

- 关系型：`SQLite`
- 向量：`sqlite` 语义缓存回退
- 图：`sqlite` 图关系回退

可选后端：

- 向量：`lancedb`、`faiss`
- 图：`kuzu`

这些后端都不是必须的；缺少依赖时会自动回退到本地 SQLite 方案。

## 一个最短示例

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as memory:
    session = memory.create_session("user-1", title="demo")

    memory.append_turn(
        session["id"],
        "user",
        "我偏好 Markdown 列表输出，并且希望尽量节省 token。",
    )

    memory.remember_long_term(
        "用户偏好 Markdown 列表输出。",
        user_id="user-1",
        memory_type="preference",
        importance=0.9,
    )

    memory.ingest_document(
        "上下文压缩策略",
        "AIMemory 使用本地算法对会话做压缩与归档。",
        user_id="user-1",
    )

    result = memory.query(
        "用户偏好什么输出形式，以及如何压缩上下文",
        user_id="user-1",
        session_id=session["id"],
        limit=8,
    )

    print(result["results"])
```

## MCP 封装

不启动服务时，你可以直接把工具定义暴露给上层 Agent：

```python
from aimemory import AIMemory

memory = AIMemory({"root_dir": ".aimemory-demo"})
adapter = memory.create_mcp_adapter()

tools = adapter.tool_specs()
result = adapter.call_tool("memory_search", {"query": "Markdown 输出", "user_id": "user-1"})
```

如果本地环境安装了 `mcp`，也可以把这些工具注册到 `FastMCP`，但库本身不负责运行服务。

## 当前状态

这次重构的主路径已经覆盖：

- 长期 / 短期记忆写入与搜索
- 会话压缩与会话记忆晋升
- 知识文档切块与检索
- 技能保存与检索
- 归档摘要与统一查询
- MCP 工具描述与调用桥接

我已做过一轮最小 smoke test，验证上述主路径可正常跑通。
