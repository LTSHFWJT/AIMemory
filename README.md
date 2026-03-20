# AIMemory

`AIMemory` 是一个面向 AI Agent 的轻量全域存储 Python 库，目标场景不是单个聊天机器人，而是多人、多智能体协同平台里的统一记忆内核。

它服务两类主链路：

- 人与 agent 的连续交互
- agent 与 agent 的协作、交接、反思、再召回

当前实现已经具备多 scope 隔离、统一 CRUD、版本链、ACL、上下文产物、handoff pack、reflection memory、平台事件联动，以及插件式平台 LLM 压缩接入。

## 设计目标

- 本地优先：核心数据面落本地数据库，不依赖外部记忆服务
- 多主体协作：天然支持 `human -> agent` 和 `agent -> agent`
- 统一 API：统一从 `memory.api.*` 访问，不把平台集成绑死在 LangChain 或 MCP 上
- 插件压缩：高级上下文压缩接平台自己的 LLM，通过插件注册，不走 MCP
- 轻量存储：优先 SQLite + LanceDB，只有大文本和 skill 包才外置对象存储

## 当前架构

```text
Platform / Multi-Agent Runtime
        |
        |  session / run / handoff / event callback
        v
   AIMemory facade
        |
        +-- memory.api.* / scoped.api.*
        +-- memory.events.*
        +-- bind_platform_llm(...) / plugin registry
        |
        +-- Local algorithms
        |     - memory extraction
        |     - retrieval / rerank
        |     - session compression
        |
        +-- Platform LLM plugin
        |     - build_context
        |     - build_handoff_pack
        |     - reflect_session / reflect_run
        |
        +-- Storage plane
              - SQLite: source of truth
              - LanceDB: semantic index
              - LocalObjectStore: large text / skill package
              - LMDB: compatibility / historical bundle read path
```

## 核心能力

- 多域存储：`long_term`、`short_term`、`knowledge`、`skill`、`archive`、`session`、`execution`
- 协作产物：`context`、`handoff`、`reflection`
- 统一检索：跨 memory / interaction / knowledge / skill / archive / execution / context / handoff / reflection
- 记忆治理：去重、晋升、压缩、审计、版本替代、低价值清理
- 作用域隔离：`platform_id / workspace_id / team_id / project_id / owner_agent_id / subject_type / subject_id / interaction_type / namespace_key`
- ACL：`read / write / manage`
- 平台事件：`turn_end / agent_end / handoff / session_close`
- 平台 LLM 插件：用于高级上下文压缩，不要求 MCP

## 存储设计

当前实现并没有把所有数据都写成“本地文档文件”。主存储设计如下：

| 层 | 当前实现 | 主要内容 |
| --- | --- | --- |
| 事务与元数据 | SQLite | memory、knowledge、skill、archive、session、execution、ACL、artifact、audit、bundle |
| 向量索引 | LanceDB | memory / knowledge chunk / skill / archive / context / handoff / reflection 检索索引 |
| 对象存储 | `LocalObjectStore` | 大知识正文、skill package、reference/script/asset 文件 |
| 兼容层 | LMDB | 历史 bundle / archive payload 兼容读取 |

因此，`aimemory` 当前是“数据库优先，文件外置为辅”的轻量数据面，而不是“本地文档堆积式存储”。

## 平台 LLM 插件化接入

推荐方式是注册平台 LLM 插件，然后通过配置或运行时绑定启用。

```python
from aimemory import AIMemory, register_platform_llm_plugin


class PlatformCompressor:
    provider = "my-platform"
    model = "ctx-compressor-v1"

    def __init__(self, endpoint: str, token: str):
        self.endpoint = endpoint
        self.token = token

    def compress(self, *, task_type, records, budget_chars, scope, metadata=None):
        return {
            "summary": f"{task_type} summary",
            "highlights": ["关键上下文", "开放任务"],
            "steps": ["继续执行", "必要时交接"],
            "constraints": ["保持轻量"],
            "facts": [item["text"][:80] for item in records[:2]],
            "provider": self.provider,
            "model": self.model,
        }


register_platform_llm_plugin(
    "platform.llm",
    lambda config: PlatformCompressor(
        endpoint=str(config["endpoint"]),
        token=str(config["token"]),
    ),
)

memory = AIMemory(
    {
        "root_dir": ".aimemory",
        "platform_llm_plugin": {
            "name": "platform.llm",
            "endpoint": "https://platform.internal/llm",
            "token": "demo-token",
        },
    }
)
```

运行时也可以后绑：

```python
memory.bind_platform_llm(
    plugin_name="platform.llm",
    settings={"endpoint": "https://platform.internal/llm", "token": "demo-token"},
)
```

直接注入 `platform_llm=` 仍然支持，但现在推荐插件注册方式，便于协同平台做统一装配、灰度和多租户配置。

## 最小示例

```python
from aimemory import AIMemory

memory = AIMemory({"root_dir": ".aimemory-demo"})

scoped = memory.scoped(
    owner_agent_id="agent.planner",
    subject_type="human",
    subject_id="user-1",
    interaction_type="human_agent",
    workspace_id="ws.alpha",
    team_id="team.alpha",
)

session = scoped.api.session.create(user_id="user-1", title="release-plan")
scoped.api.session.append(session["id"], "user", "请记住我喜欢先结论后步骤。")
scoped.api.long_term.add("用户偏好先结论后步骤。", memory_type="preference", importance=0.9)

context = scoped.api.context.build(
    "用户偏好与当前执行约束",
    session_id=session["id"],
    use_platform_llm=False,
)

print(context["artifact"]["id"])
```

## 什么时候压缩

这是多智能体平台接入时最关心的部分：

| 场景 | 入口 | 默认压缩方式 | 是否可接平台 LLM |
| --- | --- | --- | --- |
| 会话窗口变长 | `api.session.append()` 触发阈值后 `api.session.compress()` | 本地算法压缩，写 `working_memory_snapshots` | 否 |
| 构建 prompt 上下文 | `api.context.build()` | 优先平台 LLM，失败回退本地压缩 | 是 |
| 生成交接包 | `api.handoff.build()` | 优先平台 LLM，失败回退本地压缩 | 是 |
| 会话 / run 反思 | `api.reflection.session()` / `api.reflection.run()` | 优先平台 LLM，失败回退本地压缩 | 是 |
| 单文档或域级压缩 | `compress_document()`、`api.long_term.compress()` 等 | 本地算法压缩 | 否 |

简化理解：

- 运行时 working memory 压缩走本地算法，保证稳定和低依赖
- 面向 prompt、handoff、reflection 的高级语义压缩走平台 LLM 插件

## 多主体与 ACL

`AIMemory` 的 scope 不是只有 `user_id`。当前默认把协作上下文拆成：

- `owner_agent_id`
- `subject_type`
- `subject_id`
- `interaction_type`
- `platform_id`
- `workspace_id`
- `team_id`
- `project_id`
- `namespace_key`

ACL 基于 `namespace_key + resource_type + resource_scope + principal` 工作。现在不仅 memory id 入口会检查，更多修改型接口内部也有 `write / manage` 校验。

## 推荐公共入口

建议平台侧只直接依赖这些对象：

- `AIMemory`
- `ScopedAIMemory`
- `AsyncAIMemory`
- `register_platform_llm_plugin(...)`
- `list_platform_llm_plugins()`
- `PlatformEventAdapter`

推荐调用方式：

- `memory.api.long_term.*`
- `memory.api.short_term.*`
- `memory.api.knowledge.*`
- `memory.api.skill.*`
- `memory.api.archive.*`
- `memory.api.session.*`
- `memory.api.execution.*`
- `memory.api.recall.*`
- `memory.api.context.*`
- `memory.api.handoff.*`
- `memory.api.reflection.*`
- `memory.api.acl.*`
- `memory.events.*`

## 文档

- [Quickstart](doc/QUICKSTART.md)
- [API Reference](doc/API_REFERENCE.md)
- [Facade API](doc/facade-api.md)
- [Service & Worker API](doc/service-worker-api.md)

## MCP

仓库仍保留 `AIMemoryMCPAdapter`，用于把 `aimemory` 暴露成工具面。

但这只是可选能力：

- 平台 LLM 压缩接入不依赖 MCP
- 多智能体协同平台的主接入方式应该是 Python API + 插件注册
- MCP 更适合把 `aimemory` 暴露给外部 agent 工具链，而不是作为平台内部压缩总线
