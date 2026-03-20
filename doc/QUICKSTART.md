# AIMemory Quickstart

这份文档按“平台接入最短路径”来写，目标是让多人多智能体协同平台尽快跑通：

1. 初始化本地存储
2. 固定一个协作 scope
3. 写入 session / memory / knowledge
4. 构建 context / handoff / reflection
5. 用插件接入平台 LLM 压缩

## 1. 初始化

```python
from aimemory import AIMemory

memory = AIMemory({"root_dir": ".aimemory-demo"})
```

初始化后会准备：

- SQLite 数据库
- LanceDB 向量索引目录
- 本地对象存储目录
- 运行时 schema、投影队列和检索索引

默认后端：

- relational: SQLite
- vector: LanceDB
- graph: disabled

## 2. 固定一个多主体 scope

多智能体平台里，不建议每次手写一组 scope 参数。先生成一个 `ScopedAIMemory`。

```python
scoped = memory.scoped(
    owner_agent_id="agent.planner",
    subject_type="human",
    subject_id="user-1",
    interaction_type="human_agent",
    platform_id="platform.demo",
    workspace_id="ws.alpha",
    team_id="team.alpha",
    project_id="proj.release",
)
```

后续 `scoped.api.*` 调用会自动继承这组作用域。

## 3. 创建 session，并让会话自动沉淀记忆

```python
session = scoped.api.session.create(user_id="user-1", title="release-plan")

scoped.api.session.append(
    session["id"],
    "user",
    "请记住我偏好先给结论，再给步骤，最后说明风险。",
)

scoped.api.session.append(
    session["id"],
    "assistant",
    "收到，我会优先保持简洁并保留可执行步骤。",
)
```

`session.append(...)` 默认会做几件事：

- 写入 `conversation_turns`
- 绑定参与者和会话上下文
- 通过 memory intelligence 尝试抽取短期记忆
- 达到阈值后触发本地会话压缩，写 `working_memory_snapshots`

## 4. 写长期记忆、知识、技能

### 长期记忆

```python
scoped.api.long_term.add(
    "用户偏好先给结论，再给步骤，最后说明风险。",
    memory_type="preference",
    importance=0.92,
)
```

### 知识文档

```python
scoped.api.knowledge.add(
    "发布回滚规范",
    "失败时先恢复数据库快照，再重启服务并验证健康检查。",
    source_name="release-playbook",
)
```

### Skill

```python
scoped.api.skill.add(
    "release_handoff",
    "为执行代理生成轻量交接包。",
    tools=["search", "summarize"],
    topics=["handoff", "release"],
    references={
        "references/checklist.md": "交接时必须说明约束、开放任务和回滚方案。",
    },
)
```

说明：

- memory 主记录落 SQLite
- knowledge 大文本按策略可外置到对象存储
- skill package / reference / script / asset 进入对象存储并可建立索引

## 5. 统一查询与 recall

```python
result = scoped.api.recall.query(
    "用户偏好和回滚规范是什么？",
    session_id=session["id"],
    domains=["memory", "knowledge", "interaction"],
    limit=8,
)

for item in result["results"]:
    print(item["domain"], item["score"], item["text"][:60])
```

如果不手工指定 `domains`，系统会用 router + recall planner 自动选域。

## 6. 构建 context / handoff / reflection

### Prompt context

```python
context = scoped.api.context.build(
    "给当前规划代理最小化上下文",
    session_id=session["id"],
    include_domains=["memory", "interaction", "knowledge"],
    use_platform_llm=False,
)
```

### Handoff pack

```python
handoff = scoped.api.handoff.build(
    "agent.executor",
    source_session_id=session["id"],
    source_agent_id="agent.planner",
    use_platform_llm=False,
)
```

### Reflection

```python
reflection = scoped.api.reflection.session(
    session["id"],
    mode="derived+invariant",
    use_platform_llm=False,
)
```

这三类产物都会持久化，而不是临时字符串：

- `context_artifacts`
- `handoff_packs`
- `reflection_memories`

## 7. 通过插件注册平台 LLM

高级上下文压缩不应该绑在 MCP 上，而应该直接绑平台自己的 LLM。

```python
from aimemory import AIMemory, register_platform_llm_plugin


class DemoPlatformLLM:
    provider = "demo-platform"
    model = "compressor-v1"

    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def compress(self, *, task_type, records, budget_chars, scope, metadata=None):
        return {
            "summary": f"{task_type} summary",
            "highlights": ["开放任务", "关键约束"],
            "steps": ["继续执行", "必要时交接"],
            "constraints": ["保持轻量"],
            "facts": [item["text"][:60] for item in records[:2]],
            "provider": self.provider,
            "model": self.model,
        }


register_platform_llm_plugin(
    "demo.platform.llm",
    lambda config: DemoPlatformLLM(endpoint=str(config["endpoint"])),
)

memory = AIMemory(
    {
        "root_dir": ".aimemory-demo",
        "platform_llm_plugin": {
            "name": "demo.platform.llm",
            "endpoint": "https://platform.internal/llm",
        },
    }
)
```

然后在高级压缩入口里打开 `use_platform_llm=True`：

```python
context = memory.api.context.build(
    "当前协作上下文",
    owner_agent_id="agent.planner",
    subject_type="human",
    subject_id="user-1",
    use_platform_llm=True,
)
```

如果平台 LLM 不可用，系统会自动回退本地压缩，并把 job 状态标成 `degraded`。

## 8. 运行时绑定平台 LLM

如果 `AIMemory` 由宿主平台统一创建，也可以在实例化后再绑定：

```python
memory.bind_platform_llm(
    plugin_name="demo.platform.llm",
    settings={"endpoint": "https://platform.internal/llm"},
)
```

也可以直接注入对象：

```python
memory.bind_platform_llm(DemoPlatformLLM(endpoint="https://platform.internal/llm"))
```

## 9. 平台事件联动

默认 `memory.events` 已经实现了一套面向协同平台的事件编排：

- `on_turn_end(...)`
- `on_agent_end(...)`
- `on_handoff(...)`
- `on_session_close(...)`

例如：

```python
result = memory.events.on_turn_end(
    session_id=session["id"],
    turn_id="turn-123",
    auto_recall=True,
    auto_context=True,
    use_platform_llm=True,
)
```

这类事件适合挂在平台 runtime 的生命周期钩子上。

## 10. ACL

多人多智能体协作下，建议显式授权，不要只依赖默认 owner 可见。

```python
scoped.api.acl.grant(
    resource_type="handoff",
    resource_scope="handoff",
    principal_type="agent",
    principal_id="agent.executor",
    permission="read",
)
```

修改型接口内部已经覆盖更多 `write / manage` 检查，不只是 memory id 入口。

## 11. MCP 仅为可选工具面

如果你需要把 `aimemory` 暴露给外部 agent 工具链，可以使用：

```python
adapter = scoped.create_mcp_adapter()
manifest = adapter.manifest()
```

但要区分两件事：

- `AIMemoryMCPAdapter` 是工具暴露层
- 平台 LLM 压缩接入应该用插件注册，不应该靠 MCP 调内部压缩
