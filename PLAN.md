# Duliu — 全自动算法竞赛出题 AI Agent 系统规划

> 版本：v0.4  
> 状态：**M9 已实现**（见 [docs/M7-COMPLETE.md](./docs/M7-COMPLETE.md)～[M9-COMPLETE.md](./docs/M9-COMPLETE.md)）  
> 技术栈：LangGraph · **Postgres** · Docker(Linux) · Isolate · **Facade 封装流水线** · Web 监控+Session · Worker  
> 决策记录：[docs/decisions.md](./docs/decisions.md) · 运行架构：[docs/architecture-runtime.md](./docs/architecture-runtime.md)

---

## 1. 项目目标

Duliu 是一套**人机协同**的算法竞赛出题系统：Agent 负责检索、设计、实现、验题、打包与题解生成；人类在每个**阶段闸口**验收，并可在任意环节接管或通过自然语言下达特殊设计指令。

**存储（已锁定）**：题目与工件以 **Postgres 为主**，**单题隔离**；逻辑组织为三级树 **根（Workspace）→ 套题 → 单题**，见 [docs/data-model.md](./docs/data-model.md)。

**人机界面（已锁定）**：**Web** = **监控中心（详日志）** + **Session Agent 聊天（唯一人机对话）** + Gate/编辑器；**CLI 预留**。阶段 Agent 仅在后端流水线内运行，不在聊天窗露面。详见 [docs/hitl-web.md](./docs/hitl-web.md)、[docs/architecture-runtime.md](./docs/architecture-runtime.md)。

**运行方式（已锁定）**：前端薄客户端；后端 **Pipeline Engine（多 Agent 出题图）+ Job Worker（对拍/编译）** 分离，对外仅 **Facade** 封装（D-08/D-09）。

**运行环境（已锁定）**：开发与验题均在 **Linux + Docker**；**Windows 开发机使用 WSL2** 运行 Docker Compose（见 [docs/wsl-windows.md](./docs/wsl-windows.md)）。判题时传统题 **严格比较输出文件**，或 **SPJ/checker**（见 §13.3）。

系统支持 **ICPC** 与 **OI** 两套工作流，支持 **套题 / 单题** 两种组织方式，覆盖 **传统 / 提交答案 / 交互 / 通信** 四类题型（含 SPJ），并通过独立**对抗评估 Agent** 与**套题评估 Agent** 降低题面歧义与难度偏离风险。

---

## 2. 题目来源分类（原创性维度）

| 类型 | 代号 | 定义 | Idea 来源 | 合规说明 |
|------|------|------|-----------|----------|
| **原创** | `ORIGINAL` | 无公开题库直接对应的新题 | 出题人 + Agent 协同头脑风暴 → `idea.yaml` | 需相似题检索报告；可用于对外发布（若后续开放） |
| **半原创** | `SEMI_ORIGINAL` | 在公开题/经典模型上做实质变体 | 出题人指定母题/算法骨架 + Agent 变体设计 | 必须记录母题引用与变更点 |
| **非原创** | `NON_ORIGINAL` | 直接使用外部题库题目 | **爬虫**采集题面/数据/标程（学习用途） | **仅个人学习**；系统默认禁止进入公开发布流水线 |

### 2.1 Idea 协同流程（原创 / 半原创）

```
出题人输入（主题、难度、算法标签、禁忌项）
    → Search Agent（可选：检索参考，不抄题面）
    → Ideation Agent（生成 2~3 个 idea 草案）
    → 人机对话精修（自然语言 special_design）
    → idea.yaml 定稿 + 人工 Gate：IDEA_APPROVED
```

### 2.2 非原创采集流程

```
爬虫任务配置（平台、难度区间、标签、排除已做）
    → Crawler Worker（Docker 内，限速、robots/ToS 配置）
    → 标准化为 Duliu 题包草稿（statement + 元数据 + 若可获取则标程）
    → 人工 Gate：IMPORT_APPROVED
    → 进入后续「改编 / 验题 / 本地化」阶段（不走原创 ideation）
```

---

## 3. 竞赛风格：ICPC 与 OI 双工作流

两套工作流在 **阶段划分、题面规范、数据策略、评分方式** 上不同，由创建套题/单题时选择的 `contest_style` 决定。

| 维度 | ICPC (`ICPC`) | OI (`OI`) |
|------|---------------|-----------|
| 默认套题规模 | **13** 题/套 | **4** 题/套 |
| 题面语言 | 通常英文为主，可附中文 | 中文为主常见 |
| 数据形态 | 多测试点、隐藏数据、时限紧 | 子任务 / 部分分 / 梯度数据常见 |
| 交互/通信 | 支持，场内需 interactor | 支持，通信题更常见 |
| 验题重点 | 对拍 + hack + 时限压力 | 子任务正确性 + 部分分逻辑 + 梯度覆盖 |
| Polygon/场务 | 偏 CF/Polygon package | 偏国内 OI 习惯（仍可导出 package） |

实现方式：LangGraph 顶层 `ContestStyleRouter` 加载 **`workflow_icpc.yaml`** 或 **`workflow_oi.yaml`**，子图节点相同但参数、检查项、模板不同。

---

## 4. 组织方式：套题与单题

### 4.1 创建入口

| 模式 | 说明 |
|------|------|
| **套题** (`CONTEST_SET`) | 创建一套题，绑定 `contest_style`，默认题数为 ICPC=13 / OI=4，可人工调整 |
| **单题** (`SINGLE_PROBLEM`) | 独立一题，或从已有套题中「拆出」做单题深化 |

### 4.2 三级树与数据库（Postgres）

| 层级 | 表/实体 | 关系 |
|------|---------|------|
| L1 根 | `workspace` | 实例根、全局配置 |
| L2 套题 | `contest_set` + `contest_slots` | 默认 ICPC 13 / OI 4 槽位 |
| L3 单题 | `problem` | **隔离单元**；`contest_set_id` 可 NULL（独立单题） |

套题元数据存 `contest_sets` 行 + JSON 字段（等价原 `contest.yaml`）：

```yaml
# 逻辑字段（存 DB JSON，非主存储文件）
name: "Duliu Practice Set #1"
contest_style: ICPC | OI
originality_policy: ORIGINAL | SEMI_ORIGINAL | NON_ORIGINAL
target_difficulty: { min_rating, max_rating, distribution: [...] }
```

单题元数据在 `problems` + `artifacts`；Web 左侧树与 API 按三级展示。详见 [docs/data-model.md](./docs/data-model.md)。

### 4.3 套内单题工作流

套题创建后，按槽位（A/B/C/… 或 P1~P4）逐个进入 **单题状态机**；单题可暂停、换槽、回退，不影响套题其他槽位。

套题全部单题到达 `PROBLEM_DONE` 后，触发 **套题评估 Agent**（§11），通过 `SET_EVAL_APPROVED` 后套题才算完成。

---

## 5. 题型与技术要求

| 题型 | 代号 | 必需组件 | SPJ |
|------|------|----------|-----|
| 传统题 | `TRADITIONAL` | std, brute(可选), gen, validator | 可选 checker |
| 提交答案题 | `SUBMIT_ANSWER` | 多答案校验逻辑 / 打包提交格式 | **必须** SPJ 或 custom checker |
| 交互题 | `INTERACTIVE` | std, **interactor**, gen | interactor + 可选 SPJ |
| 通信题 | `COMMUNICATION` | 多进程/多文件通信协议, interactor | 协议验证 + SPJ |

所有题型可导出 **Polygon 兼容 package**（见 [docs/polygon.md](./docs/polygon.md)）。Runner 在 **Linux** Docker + Isolate 中编译运行 **C++ / Python / Java** 标程与暴力（见 §9、§13.3）。

---

## 6. 单题出题阶段（人工验收闸口）

每一道题独立走 **阶段状态机**；**每个阶段结束必须 `human_approve(stage)` 才能进入下一阶段**（LangGraph `interrupt_before` 或 explicit `HumanGate` 节点）。

### 6.1 标准阶段（原创 / 半原创）

| 序号 | 阶段 ID | 名称 | 主要产出 | 负责 Agent / 模块 |
|------|---------|------|----------|-------------------|
| S0 | `IDEA` | 创意与规格 | `idea.yaml`, 相似题报告 | Ideation / Search |
| S1 | `SPEC` | 形式化规格 | `spec.yaml`（约束、复杂度、题型） | Design |
| S2 | `STATEMENT` | 题面 | `statement.md`（中/英）, 样例 | Design |
| S3 | `SOLUTION` | 标程与暴力 | `solutions/std.*`, `brute.*` | Solver |
| S4 | `GENERATOR` | 数据生成 | `scripts/gen.*`, `validator.*` | Solver + Runner |
| S5 | `STRESS` | 对拍验题 | `reports/stress.json`, 反例库 | Stress Harness（确定性） |
| S6 | `ADVERSARIAL_REVIEW` | 对抗评估 | `reports/adversarial.json` | **Adversarial Agent（只评不出）** |
| S7 | `PACKAGE` | 题包与 Polygon | `package/` | Polygon Adapter |
| S8 | `EDITORIAL` | 题解 | `editorial.md` | Editorialist |
| S9 | `DONE` | 完成 | — | — |

**非原创**路径：`IMPORT`（网络题面 + 可选网络标程 + `import_check` 对拍）→ 须 **原题提交确认** → 简化 gen/stress，仍严格判定。详见 [docs/non-original-workflow.md](./docs/non-original-workflow.md)。

### 6.2 阶段 Gate 规则

- 状态字段：`problem.stages[stage_id].status = PENDING | AGENT_WORKING | AWAITING_HUMAN | APPROVED | REJECTED`
- `REJECTED`：人类附注原因 → Agent 或人类修复 → 重新提交该阶段验收
- 审计日志：每阶段输入/输出工件 hash、操作者（`agent` | `human:<user>`）、时间戳

### 6.3 ICPC vs OI 阶段差异（配置层）

| 阶段 | ICPC 额外检查 | OI 额外检查 |
|------|---------------|-------------|
| S2 STATEMENT | 英文题面完整性、样例与限制一致 | 子任务描述（若有）、部分分说明 |
| S4 GENERATOR | 时限压力下数据规模 | 梯度/子任务绑定的数据分组 |
| S5 STRESS | 多组数据 TLE 筛查 | 子任务逐档通过报告 |
| S6 ADVERSARIAL | 交互/通信协议边界 | 部分分边界与误导数据 |

---

## 7. 人机交互接口（HITL）：Web 主路径 + CLI 预留

> 主规范：[docs/hitl-web.md](./docs/hitl-web.md) · CLI 预留：[docs/hitl-cli.md](./docs/hitl-cli.md)

### 7.1 已锁定形态（前后端分离）

| 层 | 载体 | 职责 |
|----|------|------|
| **Web · 监控中心** | 浏览器 | 事件时间线、Job 进度、**详查** stdout/stderr、筛选/导出；见架构文档 §2.1 |
| **Web · Session** | 聊天侧栏 | **唯一人机对话**；解释状态、NL 设计、dispatch、Gate 协助 |
| **Web · 其他** | 同站 | 三级树、工件编辑、阶段审批、LLM 设置 |
| **API Gateway** | `duliu-api` | 仅暴露 Facade；WebSocket 扇出 `events` |
| **Pipeline Engine** | 后端服务 | LangGraph 阶段多 Agent；**高度封装**，仅 `PipelineFacade` |
| **Job Worker** | 后端服务 | stress/compile/crawl；Linux Docker；进度写 `events` |
| **CLI** | 预留 | 调同一 REST；`compose up` / `approve` / `export` |
| **IDE** | 可选 | 导出离线改 |

启动：在 **WSL2** 内 `docker compose up`（api、worker、postgres）。Windows 主机勿直接裸跑 Worker。**禁止**前端 import 阶段 Agent 或 LangGraph 图。

### 7.2 Session Agent（会话 Agent）

| 属性 | 说明 |
|------|------|
| 入口 | Web「助手」面板；CLI `duliu chat` 为预留 |
| 记忆 | Postgres `sessions` / `session_messages` + 周期 `summary` |
| 能做 | 同前：`dispatch_stage`、`enqueue_special_design`、`approve_stage`（Web 按钮等价） |
| 不能做 | 绕过 Gate / 对抗评估；`HUMAN` 模式下覆盖用户未保存的 Web 草稿 |

阶段 Agent 写入 **DB 工件版本**；人类在 Web 编辑器保存 → 新版本行。

### 7.3 设计原则

- **全程可观测**：统一 `events` 表 + 大日志对象存储；监控中心可展开 payload 与完整 Runner 日志
- **交互单一**：人类只与 Session Agent 对话；阶段 Agent 动作只在监控中可见
- **后端封装**：`PipelineFacade` / `SessionFacade` / `MonitorFacade` / `JobFacade`（见 [architecture-runtime.md](./docs/architecture-runtime.md) §3）
- **控制权**：`control_mode` 在 Web 或 Session 工具切换
- **special_design**：仅 Session → `special_design_queue` → 下阶段 prompt

### 7.4 API（Web + CLI 共用）

| 接口 | 用途 |
|------|------|
| REST | 三级树 CRUD、artifacts、approve/reject |
| WebSocket/SSE | 事件流、Runner 进度 |
| LangGraph `interrupt` | 待审批 → Web 展示 Gate |
| CLI | 调用同一 REST（token/本地） |

### 7.5 LLM 与工具调用（D-10）

各 Agent 独立 `provider` / `model`（`config/agents.llm.yaml`）。API Key 在 **Web 设置页** 配置（推荐），或 env / `.duliu/secrets.yaml`。

- LLM 通过 **后端 Tool Calling** 调用 `save_artifact`、`dispatch_stage` 等；**不是 MCP，不是 CLI**。
- 工件写入 **Postgres**，非直接改 Cursor 本地文件。详见 [docs/integrations.md](./docs/integrations.md) §1。

### 7.5b 爬虫凭证（D-12）

登录类站点由用户在 Web 填写 **Token/Cookie**（加密存储）；爬虫在 Worker 容器执行，失败进 Monitor。详见 [docs/integrations.md](./docs/integrations.md) §3。

### 7.7 Web 编辑、单点运行与一键对拍（D-13 / D-14 / D-16）

- **工件编辑**：浏览器 **Monaco Editor** 修改任意 `artifacts`（题面/标程/gen/…），语法高亮；内容存 Postgres，**不是沙箱能力**。
- **沙箱**：仅 **Runner** 编译/运行；**不在浏览器执行代码**。
- **按输入一键运行（D-16）**：Web 输入 stdin → `POST /api/problems/{id}/run` → Job `run_single` → Isolate 运行 std/brute → **stdout/stderr/verdict/用时** 返回页面（可选「当前草稿运行」）。
- **一键对拍（D-14）**：保存后 **stress/run**（quick/full）；结果进监控中心；正式 **S5 Gate** 仍须 full + 人工 approve。详见 [docs/web-editor-and-sandbox.md](./docs/web-editor-and-sandbox.md)。

### 7.8 非原创题（D-15）

- 可使用 **网络标程**（爬取或粘贴）作起点，**必须** 配备 **brute** + **严格对拍**（默认简化 gen、较少轮次用于 IMPORT 校验）。
- **强制原题提交**：UI 展示 `problem_url`；用户勾选「已在原题平台提交/核对」后方可过 IMPORT 与后续阶段。详见 [docs/non-original-workflow.md](./docs/non-original-workflow.md)。

### 7.6 后台服务（D-08 已锁定）

| 服务 | 职责 |
|------|------|
| **api** | FastAPI + Facade + Monitor WebSocket；不接长对拍 |
| **pipeline** | LangGraph 消费（可与 api 同镜像异 command） |
| **worker** | Runner stress/compile；可水平扩展 |
| **postgres / minio** | 状态、事件、大日志 |

长任务 **不得** 阻塞 API 请求线程；Pipeline 通过 `JobFacade` 提交 Worker 并订阅完成事件。

---

## 8. 版本管理与回退（数据库为主）

### 8.1 工件版本

- 主存储：`artifacts` + `artifact_versions`（按 `problem_id` 隔离）
- 每次 Agent/人类保存 → 新版本 + `sha256`；Gate 通过可记 `problem_stages.approved_at`

### 8.2 回退

- **题级回退**：恢复指定 `artifact.version` 或 LangGraph `checkpoint_id`（Postgres）
- **可选导出**：`duliu export problem <id>` 生成目录树供 Polygon / 离线 IDE

### 8.3 与 LangGraph

- Checkpointer：**Postgres**（与业务库可同实例不同 schema）
- 恢复：Web 选择历史版本 / checkpoint → 从对应阶段重跑

---

## 9. 编程语言支持

Runner 与编译矩阵（Docker 镜像内预装）：

| 语言 | 标程/暴力/交互 | 数据生成 | 备注 |
|------|----------------|----------|------|
| **C++17** | ✓ | — | 默认；testlib |
| **Python 3** | ✓ | ✓ gen | 注意 pypy/cpython 时限差异配置 |
| **Java** | ✓ | — | 明确 JVM 时限倍率 |

`spec.yaml` 字段 `solution_languages: [cpp, python, java]` 限制该题可用语言；对拍至少 **std 与 brute 各一种**（可跨语言对拍，Runner 统一比较输出）。

---

## 10. 对抗评估 Agent（Adversarial Reviewer）

### 10.1 定位

- **不参与出题**：无写题面/写标程权限（工具层只读 + 运行测试）
- **目标**：尽可能找出 **题面歧义、逻辑漏洞、数据弱点、协议 hole、SPJ 漏洞**
- 在 **S6 ADVERSARIAL_REVIEW** 强制执行，未通过不得进入 PACKAGE

### 10.2 能力清单

| 类别 | 手段 |
|------|------|
| 题面 | 多角色复述题意、抽取约束，检查矛盾/遗漏 |
| 逻辑 | 构造边界输入、假说反例交给 Runner |
| 数据 | 尝试 hack 标程（小数据手造 + gen 变异） |
| 交互/通信 | 协议状态机枚举、非法操作序列 |
| SPJ | 对拍多解、浮点、格式陷阱 |
| 输出 | `adversarial.json`：severity、复现步骤、建议修复 |

### 10.3 与人类 Gate

- Agent 报告 **必须** 经人类阅读确认：接受风险 / 打回修复
- 打回 → 路由到 S2/S3/S4/S5 之一（由 Orchestrator 根据 issue 类型分类）

---

## 11. 套题评估 Agent（Set Evaluator）

触发条件：套内所有题 `stage >= DONE`（或配置为允许带草稿评估）。

| 评估项 | 说明 |
|--------|------|
| 难度曲线 | 各题 CF rating 估计 vs `contest.yaml.target_difficulty.distribution` |
| 区分度 | 预估通过率梯度、是否与套题定位一致 |
| 题型搭配 | ICPC：有无交互/通信是否合理；OI：子任务结构是否协调 |
| 原创性套级 | 非原创套题标注仅供学习 |
| 冗余 | 算法标签是否过度重复 |

产出：`set_evaluation.json` + 可视化难度条形图数据 → 人工 Gate：`SET_EVAL_APPROVED`。

---

## 12. Codeforces 标准难度配置

### 12.1 配置项（`difficulty.yaml` 或写入 `spec.yaml`）

```yaml
difficulty_model: codeforces  # 预留 atcoder、custom
rating:
  target: 1500              # 单题目标
  tolerance: 100            # 可接受偏差
  bounds: [800, 3500]
estimation_inputs:           # 供评估 Agent
  required_tags: [dp, graphs]
  reference_problems: []     # 可选 CF 题号
```

### 12.2 使用方式

- **出题前**：套题/单题设置目标 difficulty band
- **S5 后**：根据 stress 轮数、hack 成功率、标程复杂度启发式修正估计
- **S6/S11**：Adversarial / Set Evaluator 引用 CF 尺度输出偏差报告

（实现注：CF rating 为估计量，系统标明 **非官方 rating**，仅供内部对齐。）

---

## 13. 沙箱与 Docker 隔离

### 13.1 分层

```
┌─────────────────────────────────────────┐
│  Duliu API / LangGraph Orchestrator      │  （无题解代码执行）
├─────────────────────────────────────────┤
│  Docker: duliu-runner image              │
│  ├─ 编译：g++, javac, python             │
│  ├─ 执行：Isolate（或 nsjail）每提交一次  │
│  │     cpu/time/memory/pids/fs 限制       │
│  ├─ 网络：默认 OFF（爬虫独立容器）         │
│  └─ 挂载：只读题目录 + 临时 output vol    │
├─────────────────────────────────────────┤
│  Docker: duliu-crawler（可选）           │  仅 NON_ORIGINAL，限速、代理配置
└─────────────────────────────────────────┘
```

### 13.2 强制策略

- **验题与评测仅在 Linux 容器内执行**（开发机可用 Docker Desktop，但 Runner 镜像必须为 Linux）
- Agent **禁止**在宿主机直接 `exec` 用户代码
- 所有 compile/run/stress 经 **Runner Service**（HTTP/gRPC）
- 镜像固定版本、无 root、只读根文件系统 + tmpfs
- 爬虫与 Runner **镜像分离**

### 13.3 输出判定（严格）

| 场景 | 规则 |
|------|------|
| 传统题、单解 | 选手输出与 `.out` **逐字节一致**（或 testlib `checker` 等价全对） |
| 多解 / 浮点 / 提交答案 | **必须** SPJ / `checker.cpp`（testlib） |
| 交互 / 通信 | interactor 协议 + 必要时 SPJ |
| 对拍 | `std` vs `brute` 同样规则；WA 必须归档反例至 DB/对象存储 |

禁止「目测日志认为正确」替代文件对比或 checker 返回值。

---

## 14. LangGraph 架构

### 14.1 图层次

```
SessionGraph（Web/CLI 共用，长期会话，见 docs/hitl-web.md）
  ├─ SessionAgentNode（ReAct / 工具：dispatch, approve, special_design, …）
  └─ dispatch ─────────────────────────────────────────────┐
                                                           ▼
TopGraph: ContestSetGraph
  ├─ CreateSetNode
  ├─ For each slot → SubGraph: ProblemGraph(contest_style, problem_type)
  │     ├─ Stage nodes S0..S9（阶段 Agent，无多轮人类聊天）
  │     ├─ HumanGateNode (interrupt) ← duliu approve / Session approve_stage
  │     └─ AdversarialSubGraph (read-only tools)
  └─ SetEvaluatorNode → HumanGateNode
```

**交互规则**：人类 ↔ **仅 Session Agent**；Session ↔ Orchestrator ↔ 阶段 Agent。

### 14.2 状态 Schema（核心字段）

```python
class ProblemState(TypedDict):
    problem_id: str
    contest_style: Literal["ICPC", "OI"]
    originality: Literal["ORIGINAL", "SEMI_ORIGINAL", "NON_ORIGINAL"]
    problem_type: Literal["TRADITIONAL", "SUBMIT_ANSWER", "INTERACTIVE", "COMMUNICATION"]
    control_mode: Literal["AGENT", "HUMAN", "HYBRID"]
    current_stage: str
    stages: dict[str, StageRecord]
    special_design_queue: list[str]
    git_ref: str
    checkpoint_id: str
```

### 14.3 路由

- `contest_style` → 加载边条件与 checklist
- `originality` → 跳过/插入 S0 vs IMPORT
- `problem_type` → 注入 interactor/SPJ 模板节点
- `adversarial.severity == critical` → 回退边到 S2/S3/S4/S5

### 14.4 持久化

- LangGraph Checkpointer：**Postgres**（必选）
- 业务数据：**Postgres**（三级树、artifacts、sessions）
- 大测试点 / 日志：**对象存储**（MinIO/S3 或 PG bytea + 外链）

---

## 15. 仓库目录规划（实现期）

```
Duliu/
  PLAN.md                 # 本文档
  docs/
    decisions.md          # ADR、Daemon 释义、LLM 密钥
    data-model.md         # 三级树 + Postgres
    polygon.md            # Polygon 说明
    hitl-web.md           # Web 主 HITL
    hitl-cli.md           # CLI 预留
    workflow_icpc.yaml
    workflow_oi.yaml
    stages.yaml
    agents.yaml
  packages/
    duliu/
      facade/             # Pipeline/Session/Monitor/Job Facade（唯一对外 SDK）
      api/                # HTTP + WebSocket
      web/                # 监控中心 + Session 聊天 + 编辑器
      cli/                # 预留
      session/            # SessionGraph + Session Agent
      pipeline/           # ProblemGraph（私有，仅 Facade 调用）
      agents/             # 阶段 Agent（包内私有）
      worker/             # Job 消费
      db/
      runner/
      crawler/
      polygon/
  docker/
    Dockerfile.api
    Dockerfile.runner
    docker-compose.yml    # api + postgres + runner + minio
  config/
    agents.llm.yaml.example
  templates/
  schemas/
```

---

## 16. 实施路线图

| 里程碑 | 范围 | 验收标准 |
|--------|------|----------|
| **M1** ✅ | 单题 · PG · Web Gate · Runner · **stdin 一键运行** · 严格对拍 | 见 [docs/M1-COMPLETE.md](./docs/M1-COMPLETE.md)、`scripts/m1-smoke-test.sh` |
| **M2** ✅ | + OI + SPJ + 三语言 + S6 + Web Session Agent | 见 [docs/M2-COMPLETE.md](./docs/M2-COMPLETE.md)、`scripts/m2-smoke-test.sh` |
| **M3** ✅ | + 交互/通信 + Polygon 导出 + S7~S8 | [docs/M3-COMPLETE.md](./docs/M3-COMPLETE.md)、`scripts/m3-smoke-test.sh` |
| **M4** ✅ | 套题 13/4 + Set Evaluator | [docs/M4-COMPLETE.md](./docs/M4-COMPLETE.md) |
| **M5** ✅ | 爬虫 + Worker 分离 + CLI | [docs/M5-COMPLETE.md](./docs/M5-COMPLETE.md) |
| **M6** ✅ | NON_ORIGINAL IMPORT + import_check + 提交 Gate | [docs/M6-COMPLETE.md](./docs/M6-COMPLETE.md) |
| **M7** ✅ | LangGraph dispatch 图 | [docs/M7-COMPLETE.md](./docs/M7-COMPLETE.md) |
| **M8** ✅ | 工件回退 + 监控分组 + Job retry | [docs/M8-COMPLETE.md](./docs/M8-COMPLETE.md) |
| **M9** ✅ | Isolate 探测 + Worker/Crawler 分离 | [docs/M9-COMPLETE.md](./docs/M9-COMPLETE.md) |
| **M10** ✅ | Postgres checkpointer + SSE + CF AC 标程 | [docs/M10-COMPLETE.md](./docs/M10-COMPLETE.md) |
| **M11** ✅ | Isolate 接入 C++ Runner + `.env` Cookie 引导 | [docs/M11-COMPLETE.md](./docs/M11-COMPLETE.md) |
| **M12** ✅ | WebSocket 监控 + LangGraph 三节点 dispatch | [docs/M12-COMPLETE.md](./docs/M12-COMPLETE.md) |
| **M13** ✅ | Python/Java isolate + Polygon 上传准备 | [docs/M13-COMPLETE.md](./docs/M13-COMPLETE.md) |

---

## 17. 需求追溯矩阵

| # | 需求摘要 | 本文档章节 |
|---|----------|------------|
| 1 | 原创/半原创/非原创 | §2 |
| 2 | ICPC / OI 双工作流 | §3, §6.3 |
| 3 | 套题 / 单题，默认 13/4 | §4 |
| 4 | 四类题型 + SPJ | §5 |
| 5 | 分阶段 + 人工验收 | §6 |
| 6 | 全程 HITL + NL 特殊设计 | §7, [hitl-web.md](./docs/hitl-web.md) |
| 6b | Session Agent 长期会话助手 | §7.2, §14.1 |
| 7 | 版本管理与回退（DB） | §8 |
| 14 | Postgres + 三级树单题隔离 | §4.2, [data-model.md](./docs/data-model.md) |
| 15 | Linux Docker 验题 + 严格判定 | §13.3 |
| 8 | LangGraph | §14 |
| 9 | C++ / Python / Java | §9 |
| 10 | 对抗评估 Agent | §10 |
| 11 | 套题评估 Agent | §11 |
| 12 | CF 难度配置 | §12 |
| 13 | Docker + 沙箱 | §13 |

---

## 18. 开放决策（实现前确认）

| 状态 | 议题 | 结论/位置 |
|------|------|-----------|
| ✅ | 题目存储 | Postgres，三级树，单题隔离 → [data-model.md](./docs/data-model.md) |
| ✅ | 状态库 | Postgres |
| ✅ | 运行环境 | Linux Docker；严格 out 或 SPJ → §13.3 |
| ✅ | HITL | Web 主，CLI 预留 → [hitl-web.md](./docs/hitl-web.md) |
| ✅ | LLM | Tool Calling + Web 配 Key；见 [integrations.md](./docs/integrations.md) |
| ✅ | LangGraph | Docker 内 Python 库，用户 compose 即可 → [integrations.md](./docs/integrations.md) §2 |
| ✅ | 爬虫凭证 | Web 配 Token/Cookie，Worker 稳定队列+重试 → [integrations.md](./docs/integrations.md) §3 |
| ✅ | Web 编辑 + 运行 + 对拍 | Monaco；`run` 单点 + `stress` 对拍均走 Runner → [web-editor-and-sandbox.md](./docs/web-editor-and-sandbox.md) |
| ✅ | 非原创 | 网络标程 + 严格对拍 + 强制原题提交 → [non-original-workflow.md](./docs/non-original-workflow.md) |
| ✅ | **D-08/D-09 运行架构** | 前端监控+Session；后端 Facade+Pipeline+Worker → [architecture-runtime.md](./docs/architecture-runtime.md) |
| ⏳ | 爬虫源站白名单 | M5 |
| ⏳ | Polygon 自动上传网页 | 默认仅本地 package → [polygon.md](./docs/polygon.md) |

---

*本文档为 Duliu 实现的一级规划；后续细化为 `docs/workflow_*.yaml`、`schemas/*.json` 与 LangGraph 节点实现。*
