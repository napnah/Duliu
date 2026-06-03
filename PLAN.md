# Duliu — 全自动算法竞赛出题 AI Agent 系统规划

> 版本：v0.1  
> 状态：需求已锁定，待实现  
> 技术栈：LangGraph · Docker · Isolate · Git · Polygon Package

---

## 1. 项目目标

Duliu 是一套**人机协同**的算法竞赛出题系统：Agent 负责检索、设计、实现、验题、打包与题解生成；人类在每个**阶段闸口**验收，并可在任意环节接管或通过自然语言下达特殊设计指令。

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

### 4.2 套题元数据（`contest.yaml`）

```yaml
id: cs_20250603_001
name: "Duliu Practice Set #1"
contest_style: ICPC | OI
originality_policy: ORIGINAL | SEMI_ORIGINAL | NON_ORIGINAL  # 套级默认，单题可覆盖
target_difficulty:           # CF 标准，见 §12
  min_rating: 800
  max_rating: 2000
  distribution:              # 套题评估用
    expected: [800, 1200, 1600, ...]
problems:
  - slot: A
    problem_id: null          # 出题后填入
    status: EMPTY | IN_PROGRESS | DONE
defaults:
  icpc_problem_count: 13
  oi_problem_count: 4
```

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

所有题型统一产出 **Polygon 兼容 package**（或内部 Duliu package，再转换），Runner 在 Docker + Isolate 中编译运行 **C++ / Python / Java** 标程与暴力（见 §9）。

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

**非原创**路径：跳过 S0 或替换为 `IMPORT` → 从 S2 或 S3 开始（视爬取完整度），其余阶段相同。

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

## 7. 人机交互接口（HITL）

### 7.1 设计原则

- **全程可观测**：Agent 工具调用、编译、对拍、写文件事件 → SSE/WebSocket 推送至前端
- **控制权可切换**：`control_mode: AGENT | HUMAN | HYBRID`（单题粒度）
- **自然语言特殊设计**：`special_design` 指令注入当前阶段上下文，Orchestrator 解析后路由到对应 Agent 或人类待办

### 7.2 接口形态

| 接口 | 用途 |
|------|------|
| REST / GraphQL | 题/套 CRUD、阶段审批、配置 |
| WebSocket / SSE | 实时日志、Runner 输出、Agent 思维链（可配置脱敏） |
| CLI (`duliu`) | 本地开发与 CI 对齐 |
| LangGraph `interrupt` | 阶段末强制等待 `approve` / `reject` |

### 7.3 人类接管能力

- 直接编辑工件文件（题面、标程、gen）→ Git 提交
- 手动触发/停止对拍、单点运行某测试
- 从 Agent 会话中「抢锁」：设置 `control_mode=HUMAN` 后 Agent 暂停写操作

---

## 8. 版本管理（Git）

### 8.1 仓库结构

每道题（或每套题）对应独立 Git 仓库或 monorepo 子目录：

```
problems/<problem_id>/
  .duliu/meta.json          # 阶段状态、题型、风格
  idea.yaml | import.json
  spec.yaml
  statement/
  solutions/                # std, brute, wa, ac 等
  scripts/                  # gen, validator, checker, interactor
  tests/
  reports/
  package/
  editorial/
```

### 8.2 策略

- Agent 每次批量写入后 **自动 commit**（message 含 `agent:<stage>:<summary>`）
- 人类编辑后 commit（`human:<user>`）
- 支持 **tag** 标记阶段通过点：`gate/S5-STRESS/v3`
- **回退**：`git revert` / checkout tag → LangGraph state 从 DB 同步恢复 `checkpoint_id`

### 8.3 与 LangGraph 协同

- LangGraph checkpoint 存 **编排状态**（当前阶段、消息、路由）
- Git 存 **工件真相源**（source of truth）
- 恢复流程：选 tag → 检出 Git → 加载对应 checkpoint → 可选从某阶段重跑

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

- Agent **禁止**在宿主机直接 `exec` 用户代码
- 所有 compile/run/stress 经 **Runner Service** HTTP/gRPC
- 镜像固定版本、无 root、只读根文件系统 + tmpfs
- 爬虫与 Runner **镜像分离**，避免题解代码接触外网

---

## 14. LangGraph 架构

### 14.1 图层次

```
TopGraph: ContestSetGraph
  ├─ CreateSetNode
  ├─ For each slot → SubGraph: ProblemGraph(contest_style, problem_type)
  │     ├─ Stage nodes S0..S9
  │     ├─ HumanGateNode (interrupt)
  │     └─ AdversarialSubGraph (read-only tools)
  └─ SetEvaluatorNode → HumanGateNode
```

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

- LangGraph Checkpointer：Postgres（或 SQLite 开发）
- 工件：Git + 对象存储（大测试点）

---

## 15. 仓库目录规划（实现期）

```
Duliu/
  PLAN.md                 # 本文档
  docs/
    workflow_icpc.yaml
    workflow_oi.yaml
    stages.yaml
    hitl-api.md
  packages/               # Python 主包
    duliu/
      orchestrator/       # LangGraph 图定义
      agents/             # 各 Agent 提示词与工具
      runner/             # Docker+Isolate 执行
      crawler/            # 非原创爬虫
      polygon/            # package 构建
      git/                # 仓库管理封装
      api/                # HITL REST/WS
  docker/
    Dockerfile.runner
    Dockerfile.crawler
  templates/              # 题型模板（std/gen/interactor）
  schemas/                # yaml/json schema
  web/                    # 可选前端：观测+审批+NL 指令
```

---

## 16. 实施路线图

| 里程碑 | 范围 | 验收标准 |
|--------|------|----------|
| **M1** | 单题 · 传统题 · ORIGINAL · ICPC · S0~S5 · Git · Runner | 对拍 1e5 轮通过；阶段 Gate 可用 |
| **M2** | + OI 工作流 + SPJ + 三语言 + S6 Adversarial | 对抗报告 + 人工 Gate |
| **M3** | + 交互/通信 + Polygon package + S7~S8 | 导出可导入 package |
| **M4** | 套题 13/4 + Set Evaluator + CF difficulty | 套题评估报告 |
| **M5** | 半原创 + NON_ORIGINAL 爬虫 + 全 HITL UI | 端到端演示 |

---

## 17. 需求追溯矩阵

| # | 需求摘要 | 本文档章节 |
|---|----------|------------|
| 1 | 原创/半原创/非原创 | §2 |
| 2 | ICPC / OI 双工作流 | §3, §6.3 |
| 3 | 套题 / 单题，默认 13/4 | §4 |
| 4 | 四类题型 + SPJ | §5 |
| 5 | 分阶段 + 人工验收 | §6 |
| 6 | 全程 HITL + NL 特殊设计 | §7 |
| 7 | Git 管理与回退 | §8 |
| 8 | LangGraph | §14 |
| 9 | C++ / Python / Java | §9 |
| 10 | 对抗评估 Agent | §10 |
| 11 | 套题评估 Agent | §11 |
| 12 | CF 难度配置 | §12 |
| 13 | Docker + 沙箱 | §13 |

---

## 18. 开放决策（实现前确认）

1. **前端技术栈**：Web（React/Vue）还是仅 CLI + 可选简易面板？
2. **Monorepo vs 每题一仓库**：建议 monorepo `problems/*` + 子模块 tag
3. **数据库**：Postgres 必选若多用户；单机可 SQLite
4. **爬虫源站白名单**：Codeforces / AtCoder / 本地 PDF 等需合法合规清单
5. **LLM 提供商与密钥管理**：环境变量 + 不出沙箱

---

*本文档为 Duliu 实现的一级规划；后续细化为 `docs/workflow_*.yaml`、`schemas/*.json` 与 LangGraph 节点实现。*
