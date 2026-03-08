# AIMemory

AIMemory 是一个给本地 AI Agent 用的全域存储 Python 库。

你可以把它理解成一个“能直接嵌进代码里的记忆层”。  
它不是云平台，也不是 HTTP 服务，更像是一个本地可调用的存储内核：把记忆、会话上下文、执行过程、知识文档、技能信息和归档，放进同一套库里管理。

如果你正在做的是 OpenClaw 这一类智能体项目，这种形态通常会比较顺手：

- 直接在 Python 里调用，不用先搭服务
- 长期记忆和会话记忆都能管
- 知识、技能、执行轨迹也能一起存
- 底层后端可以替换，但上层记忆逻辑尽量保持稳定
- 默认就有召回、压缩、归档和治理能力

---

## 项目现在做到哪一步了

从当前仓库实现来看，AIMemory 已经不是一个只会“存几条记忆再做检索”的小样例了。  
它现在更接近一个轻量的 Agent Storage Kernel，核心能力已经比较完整：

- 对外统一入口：`AIMemory`、`AsyncAIMemory`
- 记忆智能写入：`add()` 默认经过 `MemoryIntelligencePipeline`
- 多域统一检索：可以在 `memory / knowledge / skill / archive / execution / interaction` 之间路由
- 插件化后端：索引后端、图后端、抽取器、规划器、重排器都做了抽象层
- 轻量治理：支持会话压缩、session memory 晋升、低价值记忆清理、综合治理

默认配置下，它会优先尝试：

- 索引后端：`lancedb`
- 图后端：`kuzu`

如果环境里没有这些依赖，也不会把整套库卡死，而是自动回退到 `sqlite`。

---

## 文档怎么读

这次文档拆成了几份，分工比较明确：

- `README.md`
  - 项目说明、架构概览、文档入口
- `QUICKSTART.md`
  - 快速开始、安装、配置、常见工作流、上手示例
- `facade-api.md`
  - `AIMemory` / `AsyncAIMemory` 的公开接口文档
- `service-worker-api.md`
  - 内部 service / worker 的接口文档和进阶用法
- `API_REFERENCE.md`
  - 一个简短的接口索引页，方便从旧入口跳转

如果你是第一次看这个项目，建议顺序是：

1. 先看 `QUICKSTART.md`
2. 再看 `facade-api.md`
3. 有需要时再看 `service-worker-api.md`

---

## 架构大意

可以先把它理解成下面这层结构：

```text
AIMemory / AsyncAIMemory
  ├─ MemoryIntelligencePipeline
  │   ├─ Vision Processor（当前是占位接口）
  │   ├─ Fact Extractor（规则抽取）
  │   ├─ Memory Planner（证据式动作规划）
  │   └─ Retrieval Service（召回与重排）
  ├─ Domain Services
  │   ├─ MemoryService
  │   ├─ InteractionService
  │   ├─ ExecutionService
  │   ├─ KnowledgeService
  │   ├─ SkillService
  │   └─ ArchiveService
  ├─ ProjectionService
  │   ├─ Index Backend
  │   └─ Graph Backend
  └─ Workers
      ├─ ProjectorWorker
      ├─ SessionCompactionWorker
      ├─ SessionMemoryPromoterWorker
      ├─ LowValueMemoryCleanerWorker
      └─ GovernanceAutomationWorker
```

主流程也不复杂：

1. 通过 facade 写入数据
2. 主数据先落到 SQLite
3. 再通过 outbox 投影到索引和图后端
4. 检索时由 recall planner 决定先查什么、再补什么

---

## 安装

最小安装：

```bash
pip install -e .
```

如果你想跑开发依赖：

```bash
pip install -e .[dev]
```

如果你想把默认偏好的后端也装上：

```bash
pip install -e .[lancedb,kuzu]
```

---

## 一个最短示例

```python
from aimemory import AIMemory

# 用 with 打开，结束时会自动关闭连接
with AIMemory({"root_dir": ".aimemory-demo"}) as store:
    # 显式写入一条长期记忆
    memory = store.memory_store(
        "用户偏好 Markdown 列表输出。",
        user_id="user-1",
        long_term=True,
        memory_type="preference",
    )

    # 搜索相关记忆
    result = store.search(
        "用户喜欢什么输出格式",
        user_id="user-1",
        top_k=5,
    )

    print(memory)
    print(result["results"])
```

更完整的上手说明，请直接看 `QUICKSTART.md`。

---

## 当前校验情况

这次文档改动没有动业务代码。  
我额外做了一次最小 smoke test，确认下面这条主路径能正常跑通：

- 创建 `AIMemory`
- 写入一条记忆
- 搜索这条记忆

如果你后面恢复了项目自己的测试目录，也可以再执行：

```bash
pytest -q
```
