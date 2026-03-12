# AIMemory Quickstart

本文档适合第一次接入 `AIMemory` 的开发者，目标是在最短路径内完成：

- 初始化本地记忆库
- 写入长期 / 短期记忆
- 创建会话并压缩上下文
- 写入知识库与技能
- 用 scoped 方式适配团队多智能体平台
- 用 MCP Adapter 暴露工具给外部 Agent

## 1. 安装

基础安装：

```bash
pip install .
```

常见增强依赖：

```bash
pip install .[embeddings]
pip install .[mcp]
pip install .[all]
```

说明：

- 不安装 `sentence-transformers` 时，会自动回退到轻量哈希嵌入
- 不安装 `mcp` 时，仍可使用本地 `tool_specs()` 与 `call_tool()`
- `LiteLLM` 在本项目里主要作为 provider 配置透出，不用于内部推理

## 2. 初始化

```python
from aimemory import AIMemory

memory = AIMemory(
    {
        "root_dir": ".aimemory-demo",
        "workspace_id": "ws.demo",
        "team_id": "team.demo",
    }
)
```

初始化后会自动准备：

- SQLite 数据库
- 对象存储目录
- 运行时 schema
- 默认向量 / 图后端
- 嵌入 runtime

## 2.1 数据库插件接入

关系型存储默认走本地 `SQLite`，也支持插件式注册：

```python
from aimemory import register_relational_backend
from aimemory.storage.sqlite.database import SQLiteDatabase

register_relational_backend("sqlite_alias", lambda config: SQLiteDatabase(config.sqlite_path))
```

然后在配置里选择：

```python
memory = AIMemory(
    {
        "root_dir": ".aimemory-demo",
        "relational_backend": "sqlite_alias",
    }
)
```

## 2.2 域级 API 一览

对外部 Agent 更推荐使用新的分组入口 `memory.api.*`：

- `memory.api.long_term.add/get/list/search/update/delete/compress`
- `memory.api.short_term.add/get/list/search/update/delete/compress`
- `memory.api.knowledge.add/get/list/search/update/delete`
- `memory.api.skill.add/get/list/search/update/delete`
- `memory.api.archive.add/get/list/search/update/delete/compress`
- `memory.api.session.create/get/append/compress/promote/archive/govern`
- `memory.api.recall.query/explain`

`ScopedAIMemory` 对应使用 `scoped.api.*`。

旧的平铺方法不再作为对外接口，统一使用 `memory.api.*` / `scoped.api.*`。

## 3. 写入长期记忆

```python
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
```

适合写入：

- 用户偏好
- 稳定事实
- 长期约束
- 长期可复用经验

## 4. 创建会话并写入短期上下文

```python
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
    "请记住我喜欢简洁、分点的回答方式。",
)
```

`append_turn()` 会完成几件事：

- 写入 `conversation_turns`
- 绑定参与者信息
- 可选自动抽取短期记忆
- 在需要时触发上下文压缩

## 5. 做统一查询

```python
result = memory.api.recall.query(
    "用户喜欢什么输出风格？",
    user_id="user-1",
    owner_agent_id="agent.assistant",
    subject_type="human",
    subject_id="user-1",
    interaction_type="human_agent",
    session_id=session["id"],
    domains=["memory", "interaction"],
    limit=8,
)

print(result["results"])
```

`memory.api.recall.query()` 会跨域聚合：

- 记忆
- 交互上下文
- 知识库
- 技能
- 归档
- 执行记录

然后做统一排序和多样性重排。

## 6. 压缩会话上下文

```python
compressed = memory.api.session.compress(session["id"], budget_chars=600)
print(compressed["snapshot"])
```

适合在以下场景调用：

- 上下文轮次太长
- 希望减少后续 prompt 拼接成本
- 想把旧上下文沉淀为 working memory snapshot

## 7. 晋升短期记忆到长期记忆

```python
promoted = memory.api.session.promote(session["id"])
print(promoted["results"])
```

适合在以下场景调用：

- 一轮任务结束后
- 发现会话里出现高价值、可复用信息
- 需要把短期结论沉淀为长期记忆

## 8. 写入知识库

```python
document = memory.api.knowledge.add(
    "上下文压缩策略",
    "AIMemory 使用本地算法对会话做压缩、去重和检索。",
    owner_agent_id="agent.assistant",
    subject_type="human",
    subject_id="user-1",
    source_name="demo-doc",
)

result = memory.api.knowledge.search(
    "压缩策略",
    owner_agent_id="agent.assistant",
    subject_type="human",
    subject_id="user-1",
)
```

写入时会自动：

- 创建文档记录
- 按策略切块
- 建立知识索引
- 写入对象存储

### 8.1 写入全局知识库

```python
global_doc = memory.api.knowledge.add(
    title="全局规则",
    text="所有 agent 在资源不足时都应优先检索全局知识库。",
    global_scope=True,
)
```

## 9. 写入技能

```python
skill = memory.api.skill.add(
    "context_compactor",
    "把长上下文压缩成简洁步骤。",
    owner_agent_id="agent.assistant",
    subject_type="agent",
    subject_id="agent.assistant",
    tools=["search", "summarize"],
    topics=["compression", "memory"],
)

result = memory.api.skill.search(
    "压缩长上下文",
    owner_agent_id="agent.assistant",
    subject_type="agent",
    subject_id="agent.assistant",
)
```

技能适合保存：

- 可复用 prompt 模板
- 工作流
- 工具组合
- 成功经验

## 10. 做归档

```python
archive = memory.api.session.archive(session["id"])
print(archive["archive"])
```

归档会：

- 把会话内容压缩成摘要
- 把完整 payload 保存到对象存储
- 建立归档摘要索引
- 为后续低成本唤起保留线索

### 10.1 手动归档与归档压缩

```python
archive = memory.api.archive.add(
    summary="归档：当前用户偏好简洁、列表化、低 token 输出。",
    owner_agent_id="agent.assistant",
    subject_type="human",
    subject_id="user-1",
)

compressed = memory.api.archive.compress(
    owner_agent_id="agent.assistant",
    subject_type="human",
    subject_id="user-1",
)
```

## 11. 面向团队多智能体平台的 scoped 用法

如果同一 Agent 会频繁在某个固定作用域下工作，推荐先绑定 scoped 句柄：

```python
scoped = memory.scoped(
    workspace_id="ws.alpha",
    team_id="team.memory",
    owner_agent_id="agent.planner",
    subject_type="agent",
    subject_id="agent.executor",
    interaction_type="agent_agent",
    project_id="mission-42",
)

session = scoped.api.session.create(title="planner-executor sync")
scoped.api.session.append(session["id"], "assistant", "总结最近执行偏差。")
scoped.api.long_term.add("executor 擅长从长计划提炼执行步骤。")

result = scoped.api.recall.query("executor 擅长什么")
print(result["results"])
```

这样做的好处：

- 不必每次手动传 `owner_agent_id`
- 不必每次重复传 `workspace_id / team_id / project_id`
- 自动生成稳定的 `namespace_key`
- 统一作用于存储、检索和归档

## 12. 查看存储布局

```python
layout = scoped.storage_layout()
print(layout)
```

## 13.4 域级 MCP 工具

```python
adapter = scoped.create_mcp_adapter()

print(adapter.litellm_config())
print([tool["name"] for tool in adapter.tool_specs()[:8]])

result = adapter.call_tool(
    "long_term_memory_list",
    {
        "limit": 10,
    },
)
```

这个接口适合：

- 平台调试
- 可视化存储域
- 校验当前 namespace 路径前缀

## 13. MCP 集成

### 13.1 导出工具描述

```python
adapter = memory.create_mcp_adapter(
    scope={
        "workspace_id": "ws.alpha",
        "team_id": "team.memory",
        "owner_agent_id": "agent.planner",
    }
)

tools = adapter.tool_specs()
print([tool["name"] for tool in tools])
```

### 13.2 本地直接调用

```python
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
```

### 13.3 如安装了 `mcp`，绑定到 `FastMCP`

```python
server = adapter.bind_fastmcp()
```

## 14. 推荐接入顺序

如果你是在做团队多智能体协同平台，推荐按下面顺序集成：

1. 先接 `AIMemoryConfig`
2. 再接 `memory.scoped(...)`
3. 用 `memory.api.long_term` / `memory.api.session` / `memory.api.knowledge` / `memory.api.skill`
4. 用 `memory.api.recall.query()` 做统一召回
5. 视场景加上 `memory.api.session.archive()` / `memory.api.session.compress()`
6. 最后再接 `create_mcp_adapter()`

## 15. 常见建议

### 建议 1：长期和短期不要混用

- 长期记忆写稳定信息
- 短期记忆留当前会话的临时状态

### 建议 2：多智能体场景优先使用 scoped

这样更不容易发生跨团队、跨 workspace、跨 Agent 混查。

### 建议 3：知识和技能要分别存

- 知识库适合“事实 / 文档 / 说明”
- 技能适合“流程 / 方法 / 模板 / 工具组合”

### 建议 4：定期做归档和晋升

这样可以同时降低上下文成本和提高长期记忆质量。
