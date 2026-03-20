# AIMemory Facade API

这份文档只讲 façade 层，也就是协同平台最应该直接接入的部分。

结论先说：

- 平台主接入面应该是 `AIMemory` / `ScopedAIMemory` / `AsyncAIMemory`
- 高级上下文压缩应该通过平台 LLM 插件接入
- MCP 是可选工具暴露层，不是平台内部压缩总线

## 1. 推荐调用路径

推荐顺序：

1. `memory.api.*`
2. `memory.events.*`
3. `scoped.api.*`
4. `async_memory.api.*`
5. `AIMemoryMCPAdapter` 仅在需要工具面时使用

## 2. `AIMemory`

### 初始化

```python
from aimemory import AIMemory

memory = AIMemory({"root_dir": ".aimemory"})
```

也支持显式注入：

```python
memory = AIMemory(
    {"root_dir": ".aimemory"},
    platform_llm=my_llm_adapter,
    platform_events=my_event_adapter,
)
```

但当前更推荐插件注册 + 配置解析。

### 根对象常用方法

| 方法 / 属性 | 说明 |
| --- | --- |
| `api` | 结构化 API 根入口 |
| `events` | 平台事件适配器 |
| `scoped(**scope_kwargs)` | 创建 `ScopedAIMemory` |
| `bind_platform_llm(adapter=None, plugin_name=None, settings=None)` | 绑定平台 LLM |
| `describe_capabilities()` | 返回能力矩阵 |
| `storage_layout(**scope_kwargs)` | 返回当前作用域下的存储布局 |
| `litellm_config()` | 返回 provider 配置 |
| `compress_text(...)` | 本地文本压缩 |
| `compress_document(...)` | 单文档本地压缩 |
| `create_mcp_adapter(scope=None)` | 创建可选 MCP adapter |
| `close()` | 关闭资源 |

## 3. `ScopedAIMemory`

当同一个 agent、团队或项目会不断复用同一组 scope 时，用 `scoped(...)` 最合适。

```python
scoped = memory.scoped(
    workspace_id="ws.alpha",
    team_id="team.alpha",
    owner_agent_id="agent.planner",
    subject_type="agent",
    subject_id="agent.executor",
    interaction_type="agent_agent",
)
```

常用方法：

| 方法 | 说明 |
| --- | --- |
| `api` | 自动继承 scope 的结构化 API |
| `using(**scope_overrides)` | 派生子 scope |
| `scope_dict()` | 查看当前 scope |
| `storage_layout()` | 查看 scoped 布局 |
| `create_mcp_adapter()` | 创建带默认 scope 的 MCP adapter |

## 4. `AsyncAIMemory`

异步 façade 只做线程包装，公共语义与同步版一致。

```python
from aimemory import AsyncAIMemory

memory = AsyncAIMemory({"root_dir": ".aimemory-async"})
await memory.api.short_term.add("异步 runtime 也复用同一套 façade。")
await memory.close()
```

适合：

- async Web 服务
- async agent runtime
- 统一 `await` 风格的 orchestration 层

## 5. façade 层的高价值能力

### `api.session.*`

适合：

- 写 turn
- 生成 snapshot
- 晋升 session memory
- 运行治理流程

说明：

- `append(...)` 会把 turn、记忆抽取和 session 压缩串起来
- session 压缩使用本地算法，不依赖平台 LLM

### `api.recall.*`

适合：

- 多域统一召回
- recall routing
- explanation / debug

### `api.context.build(...)`

适合：

- 构建发给当前 agent 的最小 prompt context
- 统一引用 memory / interaction / knowledge / archive / execution / handoff / reflection
- 持久化为 `context_artifacts`

### `api.handoff.build(...)`

适合：

- planner -> executor
- agent -> agent 切换
- 保留任务摘要、约束、开放事项、关联 source refs

### `api.reflection.session(...)` / `api.reflection.run(...)`

适合：

- 会话后经验沉淀
- run 级过程复盘
- 把结果写成可检索的 reflection memories

### `api.acl.*`

适合：

- 跨 agent / 团队授权
- namespace 级资源读写管理

## 6. 平台 LLM 插件接入

### 注册

```python
from aimemory import register_platform_llm_plugin

register_platform_llm_plugin("platform.llm", factory)
```

`factory(config)` 需要返回一个实现了下列接口的对象：

```python
class PlatformLLM:
    provider = "platform"
    model = "compressor"

    def compress(self, *, task_type, records, budget_chars, scope, metadata=None):
        ...
```

### 配置驱动

```python
memory = AIMemory(
    {
        "root_dir": ".aimemory",
        "platform_llm_plugin": {
            "name": "platform.llm",
            "endpoint": "https://platform.internal/llm",
        },
    }
)
```

### 运行时绑定

```python
memory.bind_platform_llm(
    plugin_name="platform.llm",
    settings={"endpoint": "https://platform.internal/llm"},
)
```

### 实际生效位置

平台 LLM 只在高级语义压缩链路里生效：

- `api.context.build(...)`
- `api.handoff.build(...)`
- `api.reflection.session(...)`
- `api.reflection.run(...)`

如果平台 LLM 抛异常，系统会回退到本地压缩并把 job 标成 `degraded`。

## 7. `events` façade

默认 `memory.events` 已经是一层平台编排 façade：

| 方法 | 典型用途 |
| --- | --- |
| `on_turn_end(...)` | turn 结束后自动压缩、召回、生成 context |
| `on_agent_end(...)` | agent 结束后自动 context + reflection |
| `on_handoff(...)` | 自动构建 handoff 和可选 context |
| `on_session_close(...)` | 关闭会话时压缩、反思、清理 |

这层非常适合挂到协同平台的生命周期事件上。

## 8. `describe_capabilities()`

适合平台启动时做自检。当前会返回：

- 当前向量 / 图后端
- 当前 embedding 配置
- 当前平台插件列表与活跃 provider
- 当前 `memory_policy`
- 可选 MCP tool 列表

## 9. 什么时候不要直接下沉到 service

以下场景不建议绕过 façade：

- 你需要 ACL
- 你需要 scope 自动补全
- 你需要 context / handoff / reflection 持久化
- 你需要平台事件编排
- 你需要平台 LLM 压缩回退逻辑

只有在做内核二开、批处理 worker 或替换算法组件时，才建议直接进入 service / worker 层。

## 10. MCP 的定位

`create_mcp_adapter()` 仍然保留，但它的定位是：

- 让外部 agent 通过工具协议访问 `aimemory`
- 暴露 tool schema 和 manifest

它不是：

- 平台 LLM 注册机制
- 平台内部压缩调度机制
- 多智能体 runtime 的唯一接入方式
