# Duliu HITL：Web 主界面 + CLI 预留

> 主路径：**Web**；运行架构见 [architecture-runtime.md](./architecture-runtime.md)。

## 1. 架构（修订）

```
浏览器
  ├─ 【监控中心】事件时间线、Job 进度、stdout/stderr 详查、筛选导出
  ├─ 【Session 助手】唯一人机对话（Session Agent）
  ├─ 三级树、阶段 Gate、工件编辑器
  └─ WebSocket/REST → duliu-api（仅 Facade，不直连 LangGraph）

duliu-api → SessionFacade / PipelineFacade / MonitorFacade / JobFacade
         → Pipeline Engine（阶段多 Agent，封装）
         → Job Worker（Linux Runner stress/compile）
```

**IDE**：可选导出；非主路径。

## 2. Web 功能模块

| 模块 | 功能 |
|------|------|
| **导航树** | L1 工作区 → L2 套题 → L3 单题 |
| **监控中心** | 实时事件；按 stage/agent/job 过滤；展开 payload；拉取完整 Runner 日志 |
| **Session 聊天** | 长期助手；NL special_design；dispatch；与监控联动查 WA |
| **阶段条** | S0~S9；Approve / Reject |
| **工件编辑** | 题面、标程、gen、checker（保存 → DB 新版本） |
| **任务卡片** | 当前 stress/compile Job 状态、取消、进度 |
| **设置** | 按 Agent 配置 LLM（decisions.md） |

阶段 Agent **不在**聊天窗回复；其动作仅出现在监控时间线（`source=pipeline`）。

## 3. Session Agent（Web 入口）

- 后端 `SessionFacade.chat`；工具白名单，**不能**直接写题面/标程文件。
- 会话：Postgres `sessions` / `session_messages`。
- 改题：`dispatch_stage` 或引导用户到工件编辑器。

## 4. 监控 API（前端消费）

| 端点 | 用途 |
|------|------|
| `WS /api/monitor/stream?problem_id=` | 订阅事件 |
| `GET /api/monitor/events` | 分页历史、筛选 |
| `GET /api/jobs/{id}` | Job 状态与进度 |
| `GET /api/jobs/{id}/logs` | 完整 stdout/stderr |

## 5. CLI 预留

```bash
duliu compose up          # 启动 api + worker + postgres + web
duliu approve STRESS -p <uuid>
duliu run stress -p <uuid>
```

## 6. 里程碑

| 阶段 | Web 交付 |
|------|----------|
| M1 | 监控时间线 + Runner 日志详查 + Gate + 工件编辑 |
| M2 | Session 聊天 + dispatch + 与监控联动 |
| M4 | 套题级监控仪表盘 |
| M5 | 日志导出、Job 取消、run_id 时间线折叠 |
