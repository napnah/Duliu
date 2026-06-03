# Duliu 运行架构：前端监控 + 会话层 / 后端封装流水线

> 版本：0.1 · 对应用户期望：前端可详查日志 + Session 负责人机交互；后端稳定多 Agent 出题、**高度封装**。

## 1. 总览

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend（Web，薄客户端）                                        │
│  ├─ 监控中心：日志/事件/任务/对拍进度（可筛选、可展开原始输出）      │
│  ├─ Session Agent 聊天：唯一人机对话入口                          │
│  ├─ 阶段 Gate、工件编辑、三级树                                   │
│  └─ 仅调用公开 REST + WebSocket（不嵌入 LangGraph）               │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  API Gateway（duliu-api）                                        │
│  路由、鉴权、限流；转发至下层 Facade；聚合 Monitor 订阅            │
└─────┬──────────────────┬──────────────────┬───────────────────┘
      │                  │                  │
      ▼                  ▼                  ▼
┌─────────────┐  ┌───────────────┐  ┌─────────────────────────────┐
│ Session     │  │ Pipeline      │  │ Job Worker                  │
│ Service     │  │ Engine        │  │ (Runner/Crawler/Stress)     │
│             │  │               │  │                             │
│ Session     │  │ LangGraph     │  │ Linux Docker + Isolate      │
│ Agent only  │  │ 阶段多 Agent  │  │ 长任务、可重试、与 API 解耦   │
│             │  │ **对外仅     │  │                             │
│             │  │  PipelineFacade│ │                             │
└─────────────┘  └───────────────┘  └─────────────────────────────┘
      │                  │                  │
      └──────────────────┴──────────────────┘
                         ▼
              Postgres + Object Storage
              events | runner_jobs | checkpoints | artifacts
```

**已锁定运行方式（D-08）**：**API + Pipeline Engine + Job Worker** 分离；前端不负责跑图，后端流水线 **高度封装、对外少量 Facade**。

---

## 2. 前端职责（你要的「监控 + 会话」）

### 2.1 监控中心（Monitor）

| 能力 | 说明 |
|------|------|
| **实时事件流** | WebSocket 订阅 `problem_id` / `job_id`；展示阶段切换、Agent 工具调用、Runner 行 |
| **分级日志** | `DEBUG` / `INFO` / `WARN` / `ERROR`；来源标签：`session`、`pipeline`、`runner`、`system` |
| **任务视图** | 对拍/编译/爬虫 Job：状态 `queued→running→done/failed`、进度条、耗时 |
| **详查** | 点击事件 → 展开 `payload`（工具参数摘要）、链接 **完整 stdout/stderr**（对象存储或分页 API） |
| **过滤** | 按阶段、Agent id、时间范围、关键字 |
| **导出** | 单次 stress 日志打包下载（debug 用） |

前端 **不** 直接读 LangGraph 内部 state；只读 `GET /api/monitor/events`、`GET /api/jobs/{id}/logs`。

### 2.2 Session Agent 面板（人机交互）

| 能力 | 说明 |
|------|------|
| 长期对话 | 绑定 `session_id` + 当前 `problem_id` / `contest_set_id` |
| 解释与指挥 | 自然语言 → 后端 `SessionFacade` → 可能触发 `PipelineFacade.dispatch` |
| 与监控联动 | 聊天中可插入「刚才是哪一步 WA？」→ Session 工具查询 `events` 摘要回复 |
| 与 Gate 联动 | 按钮 Approve/Reject；口语「通过 STRESS」→ Session 调 `approve_stage` |

**原则**：阶段 Agent（Design/Solver/…）**不出现在聊天窗口**；它们的动作只在监控里以结构化事件显示。

---

## 3. 后端职责（稳定出题流水线 + 高度封装）

### 3.1 封装分层

| 层 | 包/服务 | 对外暴露 | 内部 |
|----|---------|----------|------|
| **L0 Facade** | `duliu.facade.*` | `PipelineFacade`, `SessionFacade`, `MonitorFacade`, `JobFacade` | 仅此层被 API 调用 |
| **L1 Pipeline Engine** | `duliu.pipeline` | 无（仅 Facade） | LangGraph 图、阶段路由、Gate interrupt |
| **L2 Stage Agents** | `duliu.agents.*` | 无 | 各 Agent prompt + 工具；工具只能写本题 DB |
| **L3 Execution** | `duliu.runner`, `duliu.worker` | 无 | 编译、对拍、爬虫；只接收 Job 描述 |

**禁止**：Web 路由 `from duliu.agents.solver import ...`；禁止 Stage Agent 调 Session；禁止绕过 `PipelineFacade` 改 `current_stage`。

### 3.2 PipelineFacade（流水线唯一入口）

```python
# 概念 API（实现期）
class PipelineFacade:
    async def dispatch(problem_id, stage: StageId, *, reason: str) -> RunHandle
    async def resume_after_gate(problem_id, stage: StageId, decision: Approve|Reject) -> None
    async def get_status(problem_id) -> PipelineStatus  # 阶段、control_mode、pending_gate
    async def rollback(problem_id, *, to_stage: StageId | to_checkpoint: str) -> None
```

- 内部启动 LangGraph `ProblemGraph`，checkpointer 写 Postgres。
- 阶段失败 **自动重试策略** 在 Engine 内配置（次数上限、退避），不泄漏到前端。
- 长阶段（如 STRESS）→ `JobFacade.enqueue_stress` 而非阻塞 API 线程。

### 3.3 SessionFacade（会话唯一入口）

```python
class SessionFacade:
    async def chat(session_id, message: str, *, context: Context) -> AsyncIterator[ChatChunk]
    async def set_control_mode(problem_id, mode: ControlMode) -> None
    async def enqueue_special_design(problem_id, text: str) -> None
```

- Session Agent 工具 **白名单**：仅 Facade 方法 + `MonitorFacade.query_recent_events`。
- Session **不能** 直接写 `artifacts` 表（除 `special_design` 元数据）；改题走 `dispatch` 或提示人类用 Web 编辑器。

### 3.4 Job Worker（稳定执行）

| Job 类型 | 执行体 | 稳定性措施 |
|----------|--------|------------|
| `compile` | Runner 容器 | 超时、OOM 记录、失败归档 |
| `stress` | Runner 容器 | 进度事件每 N 轮写入 `events`；可 cancel；断线可恢复查询 |
| `crawl` | Crawler 容器 | 独立镜像、限速 |

Worker 与 Pipeline Engine 通过 **队列**（Postgres `job_queue` 或 Redis）通信；Pipeline 等待 Job 完成时订阅 Job 事件，**不** 阻塞 HTTP worker。

---

## 4. 日志与可观测性（支撑前端监控）

### 4.1 统一事件模型

每条写入 `events` 表（及可选结构化日志流）：

```json
{
  "id": "uuid",
  "ts": "ISO8601",
  "level": "INFO",
  "source": "pipeline|session|runner|system",
  "problem_id": "uuid",
  "contest_set_id": "uuid|null",
  "stage_id": "STRESS|null",
  "agent_id": "solver|null",
  "job_id": "uuid|null",
  "type": "agent.tool_call|runner.stdout|gate.awaiting_human|...",
  "message": "human readable one-liner",
  "payload": {},
  "log_ref": "s3://.../jobs/xxx/stderr.log|null"
}
```

### 4.2 大日志处理

- Runner stdout/stderr **不落 PG 大字段**；写对象存储，`log_ref` 指向。
- 前端 Monitor：列表读 `events`；详查拉 `GET /api/jobs/{id}/logs?stream=stderr`。

### 4.3 相关性

- 同一 `run_id`（一次 dispatch）关联多条 event，前端可按 run 折叠时间线。

---

## 5. 进程 / 部署（Docker Compose）

```yaml
# 逻辑服务
services:
  api:          # FastAPI，仅 Facade + WebSocket fanout
  pipeline:     # 可选：与 api 同镜像不同 command，专跑 LangGraph 消费
  worker:       # Job 执行，水平扩展
  runner:       # 无状态 Linux 评测镜像（或 worker 内嵌调用）
  postgres:
  minio:        # 大日志、测试点 blob
  web:          # 静态前端或 nginx 反代
```

**最小生产形态**：`api` + `worker` + `postgres` + `minio` + `web`；`pipeline` 逻辑可在 api 进程内异步任务队列消费，但 **stress 必须在 worker**。

---

## 6. 与 LangGraph 的关系

| 组件 | 位置 |
|------|------|
| `ContestSetGraph` / `ProblemGraph` | `duliu.pipeline` 私有 |
| `SessionGraph`（仅 Session Agent） | `duliu.session`；与 Pipeline **进程可同可异**，逻辑分离 |
| HumanGate | Pipeline 内 `interrupt` → API 写 `gate.awaiting_human` event → 前端展示 |

---

## 7. 稳定性原则（后端）

1. **幂等**：同一 `dispatch` 带 `idempotency_key`，避免 double stress。  
2. **单题锁**：同一 `problem_id` 同时只允许一个 Pipeline run（PG advisory lock）。  
3. **失败分类**：LLM 失败 / Runner WA / Gate reject — 不同重试与事件 `type`。  
4. **版本不变式**：阶段 Agent 写入必须新增 `artifact.version`，禁止原地覆盖无版本号。  
5. **封装测试**：Facade 层契约测试 + Pipeline 集成测试；Stage Agent 单元测试 mock Runner。

---

## 8. 里程碑对齐

| 里程碑 | 交付 |
|--------|------|
| M1 | Monitor 基础时间线 + Runner 日志详查；PipelineFacade + Worker stress |
| M2 | SessionFacade + Web 聊天；事件按 `run_id` 折叠 |
| M4 | 套题级 Monitor 仪表盘 |
| M5 | Worker 水平扩展、日志导出、Pipeline 自动重试策略可配置 |
