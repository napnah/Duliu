# Duliu HITL：CLI 预留（非主路径）

> 版本：0.2  
> **主界面已改为 Web**，见 [hitl-web.md](./hitl-web.md)。本文档保留 CLI 命令约定，供 CI、脚本与高级用户。

---

## 1. 设计目标

| 目标 | 实现方式 |
|------|----------|
| 在 VS Code / Cursor 中查看、编辑题面与代码 | 工作区直接打开 Duliu 仓库（`problems/<id>/`） |
| 与 Agent 长期对话、下达特殊设计 | **Session Agent**（会话 Agent） |
| 观测流水线、审批阶段 | `duliu` CLI（TUI / 流式日志） |
| 不重复造编辑器 | **不用** Web 题面编辑器作为主路径 |

---

## 2. 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│  VS Code / Cursor（工作区 = Duliu 根或某套题/单题目录）       │
│  · 人类编辑 statement / solutions / scripts                 │
│  · 查看 Git diff、测试点、报告 JSON                          │
└───────────────────────────┬─────────────────────────────────┘
                            │ 同一文件树
┌───────────────────────────▼─────────────────────────────────┐
│  duliu CLI（终端 / Cursor 集成终端）                          │
│  · Session Agent 对话（主交互入口）                          │
│  · watch / approve / reject / run / status                  │
│  · 事件流（SSE 或本地 socket）                               │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  Duliu Daemon（可选，本地单用户）                             │
│  · LangGraph Orchestrator + Checkpointer                    │
│  · Runner / Git / 阶段 Gate                                  │
└─────────────────────────────────────────────────────────────┘
```

**原则**：CLI 负责「对话 + 指挥 + 观测」；IDE 负责「读写在磁盘上的工件」；流水线 Agent 负责「按阶段自动执行」。

---

## 3. Session Agent（会话 Agent）

### 3.1 定位

| 维度 | Session Agent | 阶段 Agent（Design / Solver / …） |
|------|---------------|-----------------------------------|
| 生命周期 | **长期**，跨套题、多题、多阶段 | 按阶段唤起，任务结束即退出 |
| 与人类关系 | **唯一主对话接口** | 不直接对人类说话（产出写入文件/报告） |
| 是否写出题工件 | 默认 **否**；通过 `dispatch` 委托 | **是**（题面、标程、gen 等） |
| 记忆 | 会话线程 + 项目摘要 + 当前题/套上下文 | 仅本阶段 checkpoint |

### 3.2 职责

1. **理解意图**：自然语言 → `special_design`、改难度、换风格、暂停/继续某题  
2. **解释状态**：当前阶段、谁在控制（`AGENT`/`HUMAN`）、上次对拍结果、待审批 Gate  
3. **调度流水线**：`dispatch(stage_agent, task)`，不替代阶段 Agent 写题  
4. **协同 IDE**：提示「请打开 `problems/p_001/statement/statement.md`」；检测工作区未保存变更时提醒  
5. **Gate 协助**：汇总本阶段产出，生成 **审批摘要**；人类在 CLI `approve` 或在对话中说「通过本阶段」  
6. **控制权的显式切换**：`handoff human` / `handoff agent` → 更新 `control_mode`

### 3.3 禁止事项

- 在 `control_mode=HUMAN` 且人类未请求时，不得覆盖 IDE 中正在编辑的文件  
- 不得绕过 `ADVERSARIAL_REVIEW` 或阶段 Gate  
- 不得代替 Adversarial Agent 宣布「题目无漏洞」

### 3.4 工具（Session Agent 专用）

| 工具 | 说明 |
|------|------|
| `get_context` | 当前套题/单题、阶段、control_mode、git ref |
| `get_stage_artifacts` | 列出本阶段文件路径（供 IDE 打开） |
| `enqueue_special_design` | 写入 `special_design_queue`，合并进下一阶段 prompt |
| `dispatch_stage` | 触发 LangGraph 子图运行（如 `SOLUTION`） |
| `request_gate_summary` | 生成审批摘要 markdown → CLI 展示 |
| `set_control_mode` | `AGENT` \| `HUMAN` \| `HYBRID` |
| `approve_stage` / `reject_stage` | 等价 CLI，带 `reason` |
| `run_runner` | 触发 compile / stress（只经 Runner 服务） |
| `search_session_memory` | 检索本会话历史决策 |

### 3.5 持久化

```
.sessions/
  <session_id>/
    thread.jsonl          # 对话历史
    summary.md            # 周期压缩的项目记忆（Session Agent 维护）
    active_contest.yaml   # 当前绑定的套题/单题指针
```

LangGraph checkpoint 存 **编排状态**；Session 存 **人类意图与对话**，二者通过 `session_id` + `problem_id` 关联。

---

## 4. CLI（`duliu`）命令约定

### 4.1 安装与启动

```bash
# 在 Duliu 仓库根目录
duliu init                    # 检测 Docker/Runner、初始化 .duliu/
duliu daemon start            # 可选后台 daemon

# 进入会话（主入口）
duliu chat                      # 附着 Session Agent，REPL / 流式
duliu chat --session <id>       # 恢复历史会话
duliu chat --problem p_001      # 绑定到单题上下文
```

### 4.2 观测与审批

```bash
duliu status                    # 套题/单题/阶段一览
duliu watch [--problem p_001]   # 尾随事件流（Agent 工具、Runner、Git）
duliu approve STATEMENT         # 阶段 Gate 通过
duliu reject STRESS --reason "..." 
duliu control human|agent|hybrid
```

### 4.3 流水线

```bash
duliu run stage SOLUTION --problem p_001
duliu run stress --problem p_001 --rounds 100000
duliu contest new --style ICPC --slots 13
duliu problem use A               # 套内槽位 → 单题工作区
```

### 4.4 IDE 协同（Codex 式）

| 步骤 | 操作 |
|------|------|
| 1 | `git clone` / 打开本地 Duliu 仓库 |
| 2 | Cursor：**File → Open Folder** → `Duliu` 或 `Duliu/problems/p_xxx` |
| 3 | 集成终端：`duliu chat` |
| 4 | Session Agent 提示路径 → 人类在 IDE 编辑 → `git`/自动 commit |
| 5 | 对话：「标程我写好了，进入对拍」→ Session `dispatch_stage STRESS` |

**可选增强**（非 M1 阻塞）：

- `.vscode/tasks.json`：`Duliu: Watch`、`Duliu: Approve`  
- Cursor Rule（`.cursor/rules/duliu.mdc`）：说明工件目录与禁止手改 `reports/`  
- **不强制** Duliu 官方 VS Code 扩展；M1 仅文档约定 + CLI

---

## 5. 事件流（CLI 观测）

Daemon 将以下事件推送到 `duliu watch` / `duliu chat` 嵌入区：

| 事件类型 | 内容 |
|----------|------|
| `stage.started` / `stage.completed` | 阶段 Agent 名、problem_id |
| `agent.tool_call` | 工具名、参数摘要（路径可点击，终端 OSC8 或打印相对路径） |
| `runner.compile` / `runner.run` | 语言、时限、退出码 |
| `stress.progress` | 轮次、WA 反例路径 |
| `gate.awaiting_human` | 待审批阶段 + 摘要路径 |
| `git.commit` | hash、message |
| `control_mode.changed` | 新模式 |

---

## 6. 与 LangGraph 的关系

```
Session Agent（CLI 外层，可独立 LangGraph 小图或单节点 ReAct）
    │
    ├─ dispatch ──► ProblemGraph（S0..S9 阶段子图）
    │
    └─ interrupt ◄── HumanGateNode ◄── CLI approve / chat「通过」
```

- **ProblemGraph** 内节点 **不** 直接与人类多轮聊天  
- 人类多轮聊天 **只** 进 Session Agent  
- `special_design_queue` 由 Session 写入，Orchestrator 在下一阶段 prompt 注入

---

## 7. 里程碑对齐

| 里程碑 | HITL 交付 |
|--------|-----------|
| M1 | `duliu chat` + Session Agent 只读上下文 + `approve`/`watch`；IDE 手改 + Git |
| M2 | Session `dispatch_stage` + `enqueue_special_design` |
| M3 | 交互/通信题阶段摘要 + IDE 路径提示 |
| M4 | 套题级会话绑定、`contest status` |
| M5 | 会话记忆压缩、可选 VS Code tasks、daemon 稳定化 |

---

## 8. 明确不做

- 不做 Duliu 专用 Web 控制台（主路径）  
- 不让阶段 Agent 与人类抢同一终端会话  
- 不在 Session Agent 内直接 `g++` 编译（必须经 Runner）
