# AIMemory

`AIMemory` 是一个面向 AI Agent 的本地化、轻量化、智能化全域存储 Python 库。

它的定位不是云服务，也不是通用数据库封装层，而是一个可以直接嵌入 Agent Runtime 的“本地记忆内核”：

- 对上提供适合 Agent 调用的 `Facade` 与 `MCP Adapter`
- 对下连接本地数据库与对象存储，默认只依赖本地文件目录
- 中间用轻量本地算法完成提取、检索、去重、压缩、归档和投影

## 项目定位

`AIMemory` 适合以下场景：

- 团队多智能体协同平台
- 单机/边缘侧 Agent Runtime
- 不希望额外部署数据库服务的本地记忆系统
- 希望把“长期记忆 / 短期记忆 / 知识库 / 技能 / 归档”统一到一个 Python 库里的项目

它明确坚持以下边界：

- 不内置 LLM 推理链路
- 不提供云端 SaaS API
- 不强依赖外部数据库服务
- 不做多模态理解，但对非文本内容保留扩展位

## 核心设计

### 1. 轻量

- 默认存储使用本地 `SQLite`
- 对象数据走本地目录
- 向量与图能力支持插件式增强，不是强依赖
- 缺少可选依赖时自动回退到本地可运行模式

### 2. 智能

- 不依赖写死的规则词表驱动主流程
- 使用本地统计与语义算法做候选提取、检索、去重与压缩
- 在不引入内部 LLM 的前提下尽量降低上层 Agent 的 token 负担

### 3. 全域

统一覆盖以下域：

- 长期记忆
- 短期记忆
- 会话交互上下文
- 知识库
- 技能
- 归档记忆
- 执行过程记录

### 4. 易扩展

- 关系型后端：默认 `SQLite`，可通过插件注册自定义实现
- 向量后端：`sqlite` 回退 / `LanceDB` / `FAISS`
- 图后端：`sqlite` 回退 / `Kuzu`
- MCP 适配：内置工具描述与 `FastMCP` 绑定
- Provider 配置：通过 `LiteLLM` 风格配置向上透出，不在库内做推理调用

## 项目分析

从当前代码结构看，`AIMemory` 已形成较清晰的分层：

- `aimemory/core/`
  - 统一入口 `AIMemory`
  - scoped 作用域封装
  - 配置、路由、能力描述、文本工具
- `aimemory/algorithms/`
  - 压缩、蒸馏、去重、检索重排
- `aimemory/storage/`
  - `sqlite`、`lancedb`、`faiss`、`kuzu`、对象存储
- `aimemory/backends/`
  - 向量 / 图后端注册与默认实现
- `aimemory/services/`
  - 更细粒度的领域服务层
- `aimemory/workers/`
  - 清理、压缩、晋升、治理、投影等后台 worker
- `aimemory/mcp/`
  - 面向上层 Agent 的 MCP 工具适配

这使它更像：

- 一个“Agent Memory Kernel”
- 一个“本地 Agent Store + 检索压缩内核”

而不是：

- 一个传统 ORM
- 一个云记忆服务
- 一个强耦合某家 LLM 的框架

## 当前能力

### 统一入口

当前主入口：

- `AIMemory`
- `AsyncAIMemory`
- `ScopedAIMemory`
- `AIMemoryMCPAdapter`

### 默认嵌入模型

默认词嵌入配置：

- Provider：`sentence-transformers`
- Model：`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- 维度：`384`

如果本地环境不满足依赖，会回退到轻量哈希嵌入，因此基础链路仍可运行。

### 算法能力

- 自适应信息蒸馏
- 轻量语义去重
- 稀疏 + 向量的混合检索
- 时间衰减排序
- MMR 多样性重排
- 本地上下文压缩

### 存储域

| 域 | 主要表 | 主要用途 |
| --- | --- | --- |
| 长期记忆 | `memories`、`memory_index` | 存稳定、可复用的信息 |
| 短期记忆 | `memories`、`conversation_turns`、`working_memory_snapshots` | 存当前窗口的重要上下文 |
| 知识库 | `documents`、`document_chunks`、`knowledge_chunk_index` | 文档切块与检索 |
| 技能 | `skills`、`skill_versions`、`skill_index` | 多 Agent 可复用技能 |
| 归档 | `archive_units`、`archive_summaries`、`archive_summary_index` | 低成本长期保存与再唤起 |
| 执行记录 | `runs`、`tasks`、`task_steps`、`tool_calls`、`observations` | Agent 执行过程留痕 |

### 多智能体作用域

`AIMemory` 目前已经具备多层次作用域隔离：

- 基础主体维度
  - `owner_agent_id`
  - `subject_type`
  - `subject_id`
  - `interaction_type`
- 团队协同维度
  - `platform_id`
  - `workspace_id`
  - `team_id`
  - `project_id`
- 自动派生
  - `namespace_key`

这些字段会同时影响：

- 记忆写入
- 统一查询
- 归档检索
- 对象存储路径前缀
- MCP 默认作用域

## 安装

基础安装：

```bash
pip install .
```

常见可选依赖：

```bash
pip install .[embeddings]
pip install .[mcp]
pip install .[lancedb]
pip install .[faiss]
pip install .[kuzu]
pip install .[all]
```

## 快速开始

### 0. 面向 Agent 的域级 API

除原有 `remember_* / ingest_* / save_skill / archive_*` 入口外，`AIMemory` 现在直接提供更适合外部 Agent 调用的域级 API。

推荐优先使用新的分组入口：

- `memory.api.long_term.add/get/list/search/update/delete/compress`
- `memory.api.short_term.add/get/list/search/update/delete/compress`
- `memory.api.knowledge.add/get/list/search/update/delete`
- `memory.api.skill.add/get/list/search/update/delete`
- `memory.api.archive.add/get/list/search/update/delete/compress`
- `memory.api.session.create/get/append/compress/promote/archive/govern`
- `memory.api.recall.query/explain`

`ScopedAIMemory` 同样支持 `scoped.api.*`。

旧的平铺方法不再作为对外接口，统一使用 `memory.api.*` / `scoped.api.*`。

这些接口会自动沿用：

- `owner_agent_id`
- `subject_type`
- `subject_id`
- `interaction_type`
- `namespace_key`

来区分人-agent、agent-agent 两类交互，并对不同主体与不同 agent 做隔离。

### 0.1 数据库插件接入

关系型存储默认走本地 `SQLite`，也支持插件注册：

```python
from aimemory import AIMemory, register_relational_backend
from aimemory.storage.sqlite.database import SQLiteDatabase

register_relational_backend("sqlite_alias", lambda config: SQLiteDatabase(config.sqlite_path))

memory = AIMemory(
    {
        "root_dir": ".aimemory-demo",
        "relational_backend": "sqlite_alias",
    }
)
```

向量与图后端也可分别通过：

- `register_vector_backend(...)`
- `register_graph_backend(...)`

接入自定义实现。

### 0.2 全局知识库与外部压缩钩子

知识库与归档支持 `global_scope=True`，用于所有 agent 可访问的共享内容：

```python
memory.api.knowledge.add(
    title="全局规则",
    text="所有 agent 都必须优先检索本地知识库，再决定是否访问外部模型。",
    global_scope=True,
)
```

如果上层 Agent 想接管压缩，也可以注册域级压缩器：

```python
def custom_compressor(*, domain, records, budget_chars, **_):
    text = " | ".join(item["text"] for item in records[:3])
    return {"summary": text[:budget_chars], "highlights": [text[:budget_chars]]}

memory.register_domain_compressor("long_term", custom_compressor)
```

### 1. 最小可运行示例

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as memory:
    session = memory.api.session.create(
        user_id="user-1",
        owner_agent_id="agent.assistant",
        subject_type="human",
        subject_id="user-1",
        interaction_type="human_agent",
        title="demo",
    )

    memory.api.session.append(
        session["id"],
        "user",
        "我偏好 Markdown 列表输出，并且希望尽量节省 token。",
    )

    memory.api.long_term.add(
        "用户偏好 Markdown 列表输出。",
        user_id="user-1",
        owner_agent_id="agent.assistant",
        subject_type="human",
        subject_id="user-1",
        interaction_type="human_agent",
        memory_type="preference",
        importance=0.9,
    )

    memory.api.knowledge.add(
        "上下文压缩策略",
        "AIMemory 使用本地算法对会话做压缩与归档。",
        user_id="user-1",
        owner_agent_id="agent.assistant",
        subject_type="human",
        subject_id="user-1",
    )

    result = memory.api.recall.query(
        "用户偏好什么输出形式，以及如何压缩上下文",
        user_id="user-1",
        owner_agent_id="agent.assistant",
        subject_type="human",
        subject_id="user-1",
        interaction_type="human_agent",
        session_id=session["id"],
        limit=8,
    )

    print(result["results"])
```

### 2. 面向团队多智能体平台的 scoped 用法

推荐先绑定作用域，再做所有读写：

```python
from aimemory import AIMemory

memory = AIMemory(
    {
        "root_dir": ".aimemory-team",
        "workspace_id": "ws.alpha",
        "team_id": "team.memory",
    }
)

planner_memory = memory.scoped(
    owner_agent_id="agent.planner",
    subject_type="agent",
    subject_id="agent.executor",
    interaction_type="agent_agent",
    project_id="mission-42",
)

session = planner_memory.api.session.create(title="planner-executor sync")
planner_memory.api.session.append(session["id"], "assistant", "把最近执行经验压缩成短摘要。")
planner_memory.api.long_term.add("executor 擅长把长计划压缩成可执行步骤。")

print(planner_memory.api.recall.query("executor 最近擅长什么", domains=["memory", "skill"]))
```

### 3. 查看当前作用域下的存储布局

```python
layout = planner_memory.storage_layout()
print(layout["domains"]["knowledge"]["object_prefix"])
```

### 4. 使用 MCP Adapter 暴露给上层 Agent

```python
from aimemory import AIMemory

memory = AIMemory({"root_dir": ".aimemory-demo"})

adapter = memory.create_mcp_adapter(
    scope={
        "workspace_id": "ws.alpha",
        "team_id": "team.memory",
        "owner_agent_id": "agent.planner",
    }
)

tools = adapter.tool_specs()

result = adapter.call_tool(
    "recall_query",
    {
        "query": "最近的执行偏好",
        "context_scope": {
            "subject_type": "agent",
            "subject_id": "agent.executor",
            "interaction_type": "agent_agent",
        },
    },
)

print(tools[0]["name"], result["results"])
```

## 自定义后端插件

如果你希望接入自己的向量库或图数据库，可以直接注册：

```python
from aimemory.backends import register_graph_backend, register_vector_backend

register_vector_backend("my_vector", my_vector_factory)
register_graph_backend("my_graph", my_graph_factory)
```

然后通过配置启用对应后端名。

## LiteLLM / MCP 关系说明

`AIMemory` 当前对 `LiteLLM` 的支持是“配置透出”，不是“内部发起推理调用”：

- `ProviderLiteConfig` 保存上层 Agent 要用的 provider/model/api_base 等
- `AIMemoryMCPAdapter.manifest()` 会把这些信息透出给上层
- 记忆系统本身仍保持“无内置 LLM”

这符合项目目标：

- 让外部 Agent 自己决定怎么调用模型
- 让 `AIMemory` 专注本地记忆与压缩检索

## 推荐使用方式

### 适合直接用 `AIMemory`

- 希望快速集成
- 希望统一使用一个 Facade
- 希望直接走 `memory.api.*` 的统一分组接口

### 适合用 `ScopedAIMemory`

- 团队多智能体平台
- 同一作用域下会频繁读写
- 希望避免在每次调用时重复传 `owner_agent_id` / `workspace_id` / `team_id`

### 适合用 `AIMemoryMCPAdapter`

- 需要把能力作为工具暴露给外部 Agent
- 需要导出 MCP `tool schema`
- 需要默认作用域 + 局部覆写

### 适合直接用 `services/*`

- 需要更底层的领域控制
- 想分别操作 interaction / execution / knowledge / skill / archive
- 在本地 runtime 中手动编排 worker 流程

## 非目标

当前项目明确不是：

- 托管式记忆平台
- 在线 SaaS 检索服务
- 强绑定某个大模型 SDK 的 Agent 框架
- 多模态理解引擎

## 文档导航

- 快速开始：`doc/QUICKSTART.md`
- 总体 API 参考：`doc/API_REFERENCE.md`
- Facade 详细 API：`doc/facade-api.md`
- Service / Worker API：`doc/service-worker-api.md`

## 当前状态

当前代码路径已经覆盖：

- 长期 / 短期记忆写入与检索
- 会话压缩与短期记忆晋升
- 知识文档切块与检索
- 技能保存与检索
- 归档摘要与统一查询
- MCP 工具导出与 `FastMCP` 绑定
- 团队多智能体 namespace 作用域隔离

当前仓库也包含基础测试，已覆盖：

- 多 workspace namespace 隔离
- scoped 存储布局
- MCP 默认 scope 与 `context_scope`
