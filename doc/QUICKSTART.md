# AIMemory 快速开始

这份文档适合第一次接触 AIMemory 的人。

目标很简单：  
先把这个库“能干什么、怎么装、怎么初始化、常见工作流怎么写”讲明白。  
等你真正开始接代码，再去看 `facade-api.md` 和 `service-worker-api.md` 查细节。

---

## 1. 先用一句话理解 AIMemory

AIMemory 不是单纯的“记忆表 + 检索”，而是一套给智能体准备的本地存储层。

它管的不只是记忆，还包括：

- 会话上下文
- 执行过程
- 知识文档
- 技能配置
- 归档结果

所以更准确地说，它是一个面向 Agent 的本地全域存储库。

---

## 2. 这个项目当前的特点

结合现在的仓库结构和实现，可以把它的特点概括成几条：

- 对外就是 Python 库
  - 通过 `AIMemory` 和 `AsyncAIMemory` 直接调用
- 记忆写入不是死存
  - `add()` 默认会先经过记忆抽取和动作规划
- 检索不是只查 memory
  - 会根据问题在多个域之间路由
- 后端不是写死的
  - 抽取器、规划器、索引后端、图后端都可以替换
- 默认就带治理能力
  - 可以压缩会话、晋升 session memory、清理低价值记忆

如果你做的是本地优先的智能体项目，这种设计会比较实用。  
不需要先平台化，也不需要先把项目拆成服务。

---

## 3. 安装

最小安装：

```bash
pip install -e .
```

如果你还想装开发依赖：

```bash
pip install -e .[dev]
```

如果你想启用默认偏好的后端组合：

```bash
pip install -e .[lancedb,kuzu]
```

说明：

- 默认配置更偏向 `lancedb + kuzu`
- 如果这两个依赖没装，项目也能跑
- AIMemory 会自动回退到 `sqlite`

---

## 4. 最常见的初始化方式

### 4.1 最简单的写法

```python
from aimemory import AIMemory

# 只传 root_dir 就可以启动
with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    print("AIMemory 已启动")
```

### 4.2 稍微完整一点的配置

```python
from aimemory import AIMemory

# 这份配置更接近真实项目会写的样子
config = {
    "root_dir": ".aimemory-demo",
    "index_backend": "lancedb",
    "graph_backend": "kuzu",
    "providers": {
        "extractor": "rule",
        "planner": "evidence",
        "recall_planner": "lite",
        "reranker": "rule",
    },
    "memory_policy": {
        "conflict_threshold": 0.72,
        "merge_threshold": 0.88,
        "search_limit": 5,
        "auxiliary_search_limit": 3,
        "compression_turn_threshold": 14,
        "cleanup_importance_threshold": 0.34,
    },
}

with AIMemory(config) as store:
    print(store.describe_capabilities())
```

---

## 5. 一开始最值得关注的配置

不用急着把所有配置都记住。  
先理解下面这些字段，基本就够上手了。

### 5.1 路径相关

- `root_dir`
  - 工作目录根路径
- `sqlite_path`
  - 主数据库文件
- `object_store_path`
  - 对象存储目录
- `lancedb_path`
  - LanceDB 数据目录
- `kuzu_path`
  - Kuzu 数据目录或数据库路径

### 5.2 行为相关

- `auto_project`
  - 写入后是否自动投影到索引和图后端
- `intelligence_enabled`
  - 是否启用记忆智能管线
- `default_user_id`
  - 没传 `user_id` 时的默认用户

### 5.3 后端相关

- `index_backend`
  - 当前内置：`lancedb`、`sqlite`
- `graph_backend`
  - 当前内置：`kuzu`、`sqlite`、`none`

### 5.4 策略相关

- `conflict_threshold`
  - 新旧记忆冲突判定阈值
- `merge_threshold`
  - 记忆合并阈值
- `search_limit`
  - 主召回阶段默认条数
- `auxiliary_search_limit`
  - 辅助召回阶段默认条数
- `compression_turn_threshold`
  - 超过多少轮对话后建议压缩
- `cleanup_importance_threshold`
  - 低价值记忆清理阈值

---

## 6. 先记住这几个概念

### 6.1 存储域

AIMemory 不只管理 `memory`，还管理：

- `interaction`
- `execution`
- `knowledge`
- `skill`
- `archive`

### 6.2 记忆 scope

- `session`
  - 更偏会话期内的短期记忆
- `long-term`
  - 更偏稳定、可复用的长期记忆

### 6.3 strategy_scope

这是系统内部做治理和召回时使用的策略作用域：

- `user`
  - 更偏用户长期偏好和画像
- `agent`
  - 更偏 agent 的方法和工作习惯
- `run`
  - 更偏某次执行过程里的临时状态

### 6.4 记忆类型

- `semantic`
- `episodic`
- `procedural`
- `profile`
- `preference`
- `relationship_summary`

---

## 7. 第一个可运行示例

```python
from aimemory import AIMemory

# 用 with 打开，退出时会自动关闭数据库连接
with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    # 显式写入一条长期记忆
    memory = store.memory_store(
        "用户偏好中文回复，并且喜欢 Markdown 列表。",
        user_id="user-1",
        long_term=True,
        memory_type="preference",
        metadata={"topic": "style"},
    )

    # 搜索这条记忆
    result = store.search(
        "用户喜欢什么回复方式",
        user_id="user-1",
        top_k=5,
    )

    print(memory["id"])
    print(result["results"])
```

---

## 8. 最常见的工作流

### 8.1 对话直接进 `add()`

当你拿到的是一段聊天消息时，通常最自然的入口就是 `add()`。

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    # add() 会尝试从消息里自动抽取记忆
    result = store.add(
        [
            {"role": "user", "content": "用户偏好中文回复，并且喜欢结构化答案。"},
            {"role": "assistant", "content": "好的，我会尽量保持中文和结构化表达。"},
        ],
        user_id="user-1",
        session_id="session-1",
        infer=True,
    )

    print(result["facts"])
    print(result["results"])
```

### 8.2 明确知道要存什么，就用 `memory_store()`

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    # 当你已经明确知道这是一条用户偏好时，直接存更稳
    memory = store.memory_store(
        "用户偏好回答里先给结论，再给细节。",
        user_id="user-2",
        long_term=True,
        memory_type="preference",
        metadata={"topic": "answer-style"},
    )

    print(memory)
```

### 8.3 查记忆，用 `search()`

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    # 先准备一条记忆
    store.memory_store("用户偏好简洁回答。", user_id="user-3", long_term=True)

    # 再检索
    result = store.search(
        "用户喜欢什么风格",
        user_id="user-3",
        top_k=5,
        search_threshold=0.0,
    )

    # search() 不只返回结果，还会返回 relations 和 recall_plan
    print(result["results"])
    print(result["relations"])
    print(result["recall_plan"])
```

### 8.4 不确定该查哪个域，就用 `query()`

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    # 写入知识文档
    store.ingest_document(
        title="OpenClaw Notes",
        text="OpenClaw 需要 session memory、knowledge recall 和 archive fallback。",
        user_id="user-4",
        source_name="notes",
    )

    # 注册一个技能
    store.register_skill(
        name="memory_router",
        description="负责在记忆域和知识域之间做路由。",
        tools=["query", "search"],
        topics=["memory", "routing", "knowledge"],
        status="active",
    )

    # query() 会把多个域的结果合并后返回
    result = store.query(
        "OpenClaw 的记忆路由要查哪些域",
        user_id="user-4",
        limit=10,
    )

    print(result["route"])
    print(result["results"])
```

### 8.5 管理会话上下文

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    # 创建会话
    session = store.create_session(user_id="user-5", session_id="session-5")

    # 写入对话轮次
    store.append_turn("session-5", "user", "请帮我记录本轮工作目标。", user_id="user-5")
    store.append_turn("session-5", "assistant", "好的，我会记录下来。", user_id="user-5")

    # 查看当前 session 状态
    health = store.session_health("session-5")

    # 手动压缩上下文
    compact = store.compress_session_context(
        "session-5",
        min_turns=2,
        preserve_recent_turns=1,
    )

    print(session)
    print(health)
    print(compact)
```

### 8.6 记录执行过程

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    # 创建会话
    store.create_session(user_id="user-6", session_id="session-6")

    # 启动 run
    run = store.start_run(
        user_id="user-6",
        goal="实现 Agent 存储层",
        session_id="session-6",
        agent_id="agent-1",
    )

    # 创建任务
    task = store.execution.create_task(
        run_id=run["id"],
        title="设计数据库模式",
        session_id="session-6",
    )

    # 添加步骤
    step = store.execution.add_task_step(
        task_id=task["id"],
        run_id=run["id"],
        title="创建 memories 表",
    )

    # 记录 checkpoint
    checkpoint = store.execution.checkpoint(
        run_id=run["id"],
        session_id="session-6",
        snapshot={"step": step["title"]},
    )

    print(run)
    print(task)
    print(step)
    print(checkpoint)
```

---

## 9. 什么时候该用哪些接口

可以先这样记：

- 想自动抽取记忆
  - 用 `add()`
- 想稳定地写一条明确记忆
  - 用 `memory_store()`
- 想查记忆
  - 用 `search()` 或 `memory_search()`
- 不确定应该查 memory、knowledge 还是 archive
  - 用 `query()`
- 想看系统会怎么召回
  - 用 `explain_recall()`
- 想管理 session
  - 用 `create_session()`、`append_turn()`、`session_health()`
- 想做自动治理
  - 用 `govern_session()`

---

## 10. 后端怎么理解

默认情况下：

- 索引后端优先 `lancedb`
- 图后端优先 `kuzu`

但如果本地环境不完整，也不用紧张，因为：

- LanceDB 不可用会回退到 `sqlite`
- Kuzu 不可用会回退到 `sqlite`
- 如果你明确不想启用图后端，可以把 `graph_backend` 设成 `none`

可以这样查看实际生效状态：

```python
from aimemory import AIMemory

with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    # 配置里想用什么
    print(store.config.index_backend)
    print(store.config.graph_backend)

    # 实际运行时生效的是什么
    print(store.index_backend.active_backend)
    print(store.graph_backend.active_backend)
```

---

## 11. 接下来该看什么

如果你已经能跑通上面的示例，下一步建议直接看：

- `facade-api.md`
  - 查 `AIMemory` / `AsyncAIMemory` 的公开接口
- `service-worker-api.md`
  - 查内部 service / worker 的能力挂点

如果你只是想找旧入口，也可以看 `API_REFERENCE.md`，那里现在是一个简短的索引页。
