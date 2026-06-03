# Duliu 技术说明

> 本文档从技术层面描述 Duliu 系统架构、实现现状与关键技术栈，并附各技术的前置背景知识索引。  
> 对应规划见 [PLAN.md](./PLAN.md)；里程碑见 [docs/M1-COMPLETE.md](./docs/M1-COMPLETE.md) ~ [docs/M12-COMPLETE.md](./docs/M12-COMPLETE.md)。

---

## 一、系统定位

Duliu 是一套**人机协同（HITL）的算法竞赛出题平台**。技术目标是把「出题」拆成可编排、可验收、可审计的阶段流水线：Agent 或规则引擎负责生成/检查工件，人类在每个 **Gate** 闸口审批；验题侧通过 **Job Worker** 在 Linux 容器内编译运行 C++/Python/Java 程序，完成单点运行、对拍、SPJ 判题、交互题驱动等任务。

**当前代码里程碑**：**M12 已实现**（…M11 isolate/`.env` Cookie → **M12 WebSocket 监控 + LangGraph prepare/dispatch/finalize 三节点图**）。**LLM 阶段 Agent 真实现、Python/Java isolate、Polygon 自动上传** 仍在 M13+ 规划中。

---

## 二、总体架构

```
┌─────────────────────────────────────────────────────────────┐
│  Web 薄客户端（静态 HTML/JS + Monaco Editor）                  │
│  监控事件 · Session 聊天 · Gate · 工件编辑 · 套题仪表盘        │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST HTTP
┌──────────────────────────▼──────────────────────────────────┐
│  duliu-api（FastAPI + Uvicorn）                              │
│  路由 / 鉴权预留 / CORS · 仅调用 Facade 层                    │
└───────┬────────────────────┬────────────────────────────────┘
        │                    │
        ▼                    ▼
┌───────────────┐    ┌────────────────────────────────────────┐
│ Session Agent │    │ PipelineFacade / JobFacade / Contest…  │
│ (规则+OpenAI) │    │ 阶段 dispatch · approve · 套题评估      │
└───────────────┘    └──────────────────┬─────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
            ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
            │ Stage Agents│    │ Job Worker  │    │  Events     │
            │ (规则 stub) │    │ 轮询 DB 任务 │    │  监控日志   │
            └─────────────┘    └──────┬──────┘    └─────────────┘
                                      │
                                      ▼
                            Runner（subprocess 编译/运行）
                                      │
                                      ▼
                         PostgreSQL（状态 + 工件 + 任务 + 事件）
```

### 核心设计原则

- **API / Worker 分离**：HTTP 请求不阻塞长任务；对拍、编译、Polygon 导出走 `runner_jobs` 异步队列。
- **Facade 封装**：`duliu.facade.*` 是对外唯一业务入口，隐藏 Pipeline、Runner、DB 细节。
- **单题隔离**：阶段、工件、Job、Event 均以 `problem_id` 为边界，Runner 工作目录按 `problem_id/job_id` 隔离。
- **前端不嵌入 Agent 图**：Web 只调 REST，不直接 import LangGraph。

---

## 三、服务与部署

| 服务 | 职责 | 技术 |
|------|------|------|
| `postgres` | 持久化 | PostgreSQL 16 Alpine |
| `api` | REST + 静态资源托管 | FastAPI, Uvicorn |
| `worker` | 轮询 `runner_jobs` 并执行 | asyncio 循环 + `handlers.py` |

**部署方式**：`docker compose up`（三服务）或 `docker-compose.m1.yml` 单容器一体模式。Windows 开发机通过 **WSL2** 跑 Docker。

**配置**：环境变量 + `.env` 注入（`DATABASE_URL`、`DULIU_RUNNER_WORK_DIR`、`OPENAI_API_KEY` 等），由 **Pydantic Settings** 加载（`packages/duliu/config.py`）。

---

## 四、数据模型（PostgreSQL + SQLAlchemy async）

### 4.1 三级树

```
Workspace（租户根）
 └── ContestSet（套题，ICPC 默认 13 槽 / OI 默认 4 槽）
      └── Problem（单题，隔离单元）
```

`Problem` 也可挂在 Workspace 下作为独立单题（`contest_set_id = NULL`）。详见 [docs/data-model.md](./docs/data-model.md)。

### 4.2 核心表

| 表 | 作用 |
|----|------|
| `workspaces` | 全局配置、`config_json`（JSONB） |
| `contest_sets` / `contest_slots` | 套题元数据、槽位与题目绑定 |
| `problems` | 题型、风格、当前阶段、`spec_json` |
| `artifacts` | 工件（statement/std/brute/gen/checker/interactor/protocol…），**版本递增** |
| `problem_stages` | 每阶段状态：`PENDING → AGENT_WORKING → AWAITING_HUMAN → APPROVED/REJECTED` |
| `runner_jobs` | 异步任务：`run_single` / `stress` / `compile` / `run_compare` / `interactive_run` / `polygon_export` |
| `events` | 结构化监控事件，可按 `problem_id`、`contest_set_id`、`run_id` 筛选 |
| `sessions` / `session_messages` | Session Agent 对话线程 |
| `workspace_secrets` | API Key 等敏感配置 |

ORM 使用 **SQLAlchemy 2.0 声明式模型 + Mapped 类型注解**，数据库驱动为 **asyncpg**。

---

## 五、出题流水线（阶段状态机）

### 5.1 阶段链（M3 完整链）

```
SPEC → STATEMENT → SOLUTION → GENERATOR → STRESS
  → ADVERSARIAL_REVIEW → PACKAGE → EDITORIAL
```

| 阶段 | 说明 |
|------|------|
| SPEC | 题意规格（难度、限制、样例等，存 `spec_json`） |
| STATEMENT / SOLUTION / GENERATOR | 题面、标程、数据生成器 |
| STRESS | 对拍验题 Gate |
| ADVERSARIAL_REVIEW | 对抗评估（规则 Agent 检查工件完整性） |
| PACKAGE | 生成 Polygon manifest，触发导出 |
| EDITORIAL | 题解草稿生成 |

### 5.2 工作流参数

ICPC / OI 差异由 YAML 配置驱动（`docs/workflow_icpc.yaml`、`docs/workflow_oi.yaml`），`workflow.loader` 在运行时加载，影响默认槽位数、评分策略、检查项等。

### 5.3 PipelineFacade

- `dispatch(problem, stage)`：触发对应 Stage Agent（当前多为**规则 stub**，完整 LLM + LangGraph 在后续里程碑）
- `approve_stage` / `reject_stage`：人工 Gate，推进或驳回阶段
- 每次操作写入 `events` 供监控查询

---

## 六、Job Worker 与 Runner 子系统

### 6.1 任务模型

API 创建 `runner_jobs`（状态 `queued`）→ Worker 按 `JOB_POLL_SECONDS` 轮询 → 取任务执行 → 写回 `result_json`、发 `events`。

### 6.2 Runner 能力（已实现）

| 能力 | 实现要点 |
|------|----------|
| **多语言编译运行** | C++（g++）、Python3、Java（`runner/languages.py`） |
| **单点运行** | `POST /run`，stdin → stdout/stderr/verdict/用时 |
| **对拍（Stress）** | std vs brute 多组随机输入，字节比较或 SPJ |
| **SPJ** | Python checker，argv 为 `[input, user_out, answer]`，exit 0 = AC |
| **期望输出比对** | `run/compare`，AC/WA 判定 |
| **交互/通信题** | Python interactor 通过 `DULIU_SOLUTION_BIN` 驱动已编译标程 |
| **Polygon 导出** | 从 artifacts 组装 zip（problem.xml + 源码 + manifest） |

**执行方式**：Linux **subprocess** + 超时控制 + 按题隔离的工作目录（`/tmp/duliu-runner/{problem_id}/{job_id}`）。**Isolate/nsjail 沙箱尚未接入**。

### 6.3 判题语义

- **传统题**：严格比较输出文件（或 stress 字节 diff）
- **SPJ**：checker 脚本裁决
- **交互题**：interactor 进程 exit code 裁决

---

## 七、Agent 层

| 组件 | 现状 | 职责 |
|------|------|------|
| **Session Agent** | M2+ | Web 唯一人机对话入口；正则解析 + 工具调用（dispatch/approve/stress/查事件）；可选 **OpenAI API** 增强回复 |
| **Adversarial Agent** | M2 规则版 | 检查 statement/std/样例/子任务/interactor 等完整性 |
| **Editorial Agent** | M3 stub | 生成题解草稿 artifact |
| **Set Evaluator** | M4 规则版 | 套题槽位填充率、难度曲线、CF rating 单调性检查 |
| **阶段 LLM Agent** | 规划中 | 设计/实现/验题各阶段，拟用 LangGraph + Tool Calling |

**LLM 集成路径**：Web 配置 Key → `workspace_secrets` → Session/Agent 通过 **httpx** 调 OpenAI HTTP API；工具写 **Postgres artifacts**，不直接改本地文件。详见 [docs/integrations.md](./docs/integrations.md)。

---

## 八、Web 前端

- **技术栈**：原生 HTML/CSS/JS（无 React/Vue 框架）
- **Monaco Editor**：CDN 加载，编辑 statement/std/brute/checker 等工件，语法高亮按 `kind` 切换
- **功能**：三级树导航、阶段条、Gate 按钮、监控事件列表、Session 聊天面板、套题仪表盘（M4 难度柱状图）
- **通信**：REST 轮询 `GET /api/monitor/events`（WebSocket 尚未实现）

静态资源位于 `packages/duliu/web/static/`。

---

## 九、API 设计（FastAPI + Pydantic Schemas）

典型端点分组：

| 分组 | 示例 |
|------|------|
| 资源 CRUD | `/api/workspaces`、`/api/contest-sets`、`/api/problems` |
| 工件 | `GET/PUT /api/problems/{id}/artifacts/{kind}`（版本自增） |
| 运行/验题 | `POST /run`、`/stress/run`、`/run/compare`、`/run/interactive` |
| 流水线 | `POST .../dispatch`、`.../stages/{id}/approve` |
| 监控 | `GET /api/monitor/events` |
| Session | `POST /api/sessions`、`.../chat` |
| 套题 | `POST .../evaluate`、`.../approve-eval` |
| Polygon | `GET /polygon/export`（同步 zip）或异步 Job |

请求/响应体由 **Pydantic v2** 模型校验与序列化（`packages/duliu/api/schemas.py`）。

---

## 十、代码包结构（概要）

```
packages/duliu/
  api/          # FastAPI 入口与路由
  facade/       # Pipeline、Session、Job、Monitor、Contest、Secrets
  db/           # ORM 模型、bootstrap、异步 Session
  worker/       # Job 轮询与 handlers
  runner/       # 编译、运行、对拍、SPJ、交互
  session/      # Session Agent
  agents/       # 对抗评估、题解、套题评估
  workflow/     # ICPC/OI YAML 加载
  polygon/      # Polygon zip 导出
  web/static/   # 前端静态资源
```

---

## 十一、扩展与未实现项（架构预留）

| 项 | 状态 |
|----|------|
| LangGraph 多 Agent 图 + Postgres Checkpointer | 设计完成，代码 stub |
| Isolate 沙箱判题 | 规划 |
| WebSocket/SSE 实时事件 | **M12 WebSocket** + M10 SSE；监控页优先 WS |
| 爬虫采集非原创题 | 规划 |
| testlib 标准交互协议 | 规划 |
| Polygon 自动上传 | 规划 |

---

## 十二、简历用简述（可选）

**Duliu — 算法竞赛出题 AI Agent 系统。** 人机协同平台：FastAPI + Worker 分离，Postgres 存题与版本管理，Web 监控 + Session Agent + Monaco 编辑，阶段 Gate 验收；支持 ICPC/OI 工作流、三语言对拍与 SPJ 验题，Docker 部署。

**技术栈一行**：Python · FastAPI · SQLAlchemy (async) · PostgreSQL · Pydantic · Docker Compose · Monaco Editor · OpenAI API · REST API · HITL 工作流

---

# 附录：技术名词与前置背景知识

以下按技术/概念列出。**★ 已实现** / **☆ 规划或部分实现** 表示在本项目中的落地程度。

---

## A. 编程语言与运行时

| 技术 | 前置背景知识 | 项目中 |
|------|--------------|--------|
| **Python 3.11+** | 基础语法；`async`/`await` 协程；类型注解；包结构与 `venv` | ★ 全栈主语言 |
| **C++** | 编译型语言；g++ 编译流程；stdin/stdout IO；竞赛常用 STL | ★ 标程/暴力默认语言 |
| **Java** | JVM；`javac`/`java` 编译运行；类与 main 入口 | ★ Runner 支持 |
| **JavaScript** | DOM 操作；`fetch` API；事件驱动；ES6+ 语法 | ★ Web 前端 |
| **SQL** | 关系型数据库；SELECT/INSERT/UPDATE；JOIN；索引；事务 ACID | ★ Postgres 查询与建模 |
| **YAML** | 键值/层级配置格式；与 JSON 互转 | ★ 工作流配置 |
| **XML** | 标签结构；Polygon `problem.xml` 格式 | ★ Polygon 导出 |

---

## B. Web 与 API 层

| 技术 | 前置背景知识 | 项目中 |
|------|--------------|--------|
| **HTTP/REST** | 请求方法（GET/POST/PUT）；状态码；无状态 API；资源路径设计 | ★ 前后端通信 |
| **FastAPI** | Python Web 框架；路由装饰器；依赖注入（`Depends`）；OpenAPI 自动生成 | ★ API 服务 |
| **Uvicorn** | ASGI 服务器；与 WSGI 区别；异步请求处理 | ★ 运行 FastAPI |
| **CORS** | 浏览器同源策略；跨域预检；`Access-Control-*` 头 | ★ 开发环境放开 |
| **Pydantic** | 数据类校验；类型强制；JSON 序列化/反序列化 | ★ API Schema |
| **pydantic-settings** | 从环境变量/`.env` 加载配置；Settings 类模式 | ★ `config.py` |
| **httpx** | Python 异步 HTTP 客户端；调用外部 API | ★ OpenAI 调用 |
| **Monaco Editor** | VS Code 同款编辑器内核；AMD `require` 加载；Model/Language 切换 | ★ 工件编辑 |
| **WebSocket / SSE** | 全双工/单向推送；与 REST 轮询对比 | ☆ 规划中的实时监控 |

---

## C. 数据库与 ORM

| 技术 | 前置背景知识 | 项目中 |
|------|--------------|--------|
| **PostgreSQL** | 关系型 DB；UUID/JSONB 类型；迁移与 schema 演进 | ★ 主存储 |
| **JSONB** | Postgres 二进制 JSON 字段；灵活 schema；索引与查询 | ★ `spec_json`、`config_json` |
| **SQLAlchemy 2.0** | Python ORM；Declarative Base；Relationship；Session 生命周期 | ★ 数据访问 |
| **SQLAlchemy asyncio** | 异步 Session；`async with session`；避免阻塞事件循环 | ★ 全异步 DB |
| **asyncpg** | PostgreSQL 异步驱动；连接池；与 SQLAlchemy 配合 | ★ DB 连接 |
| **数据库迁移** | schema 版本管理（Alembic 等）；本项目目前用 bootstrap 脚本建表 | ★ `init_db` / bootstrap |

---

## D. 架构与设计模式

| 技术 | 前置背景知识 | 项目中 |
|------|--------------|--------|
| **微服务/多进程分离** | API 与 Worker 解耦；共享 DB 作任务队列；水平扩展思路 | ★ api + worker |
| **Facade 模式** | 对外简化接口、隐藏子系统复杂度 | ★ `duliu.facade.*` |
| **Job Queue（DB 轮询）** | 生产者-消费者；任务状态机；幂等与重试 | ★ `runner_jobs` |
| **事件溯源/监控事件** | 结构化日志；`type + payload_json`；可审计 | ★ `events` 表 |
| **阶段状态机** | 有限状态；Gate 中断；approve/reject 流转 | ★ `problem_stages` |
| **HITL（Human-in-the-Loop）** | AI 系统人工审批点；interrupt 设计 | ★ 每阶段 Gate |
| **单题隔离** | 多租户/多资源边界；FK 约束；避免跨题写 | ★ `problem_id` 边界 |
| **版本化 Artifact** | 不可变版本链；回滚；content hash | ★ `artifacts.version` |

---

## E. AI / Agent

| 技术 | 前置背景知识 | 项目中 |
|------|--------------|--------|
| **LLM（大语言模型）** | Prompt；上下文窗口；temperature；API 计费 | ★ Session 可选增强 |
| **OpenAI API** | Chat Completions；API Key；模型名（如 gpt-4o-mini） | ★ 可选集成 |
| **Tool Calling / Function Calling** | 模型输出结构化工具调用；后端白名单工具执行 | ☆ Session 规则工具；完整 LLM 工具在规划 |
| **LangGraph** | 有状态 Agent 图；节点/边；Checkpointer；`interrupt_before` 人工闸口 | ☆ 架构设计，代码 stub |
| **LangChain** | LLM 应用框架；常与 LangGraph 配合 | ☆ 集成文档提及 |
| **Session Agent** | 长期对话；绑定 workspace/problem；工具编排 | ★ 规则 + 可选 LLM |
| **RAG / MCP** | 检索增强；Model Context Protocol（IDE 工具协议） | ☆ 文档明确默认不用 MCP |

---

## F. 容器与运维

| 技术 | 前置背景知识 | 项目中 |
|------|--------------|--------|
| **Docker** | 镜像/容器；Dockerfile；进程隔离；volume 持久化 | ★ 部署 Runner/API |
| **Docker Compose** | 多服务编排；`depends_on`；环境变量注入；网络 | ★ 本地/开发部署 |
| **Linux 进程管理** | subprocess；信号；超时 kill；文件描述符 | ★ Runner 核心 |
| **WSL2** | Windows 上 Linux 内核；与 Docker Desktop 集成 | ★ Windows 开发文档 |
| **环境变量配置** | 12-factor 配置；secrets 与 config 分离 | ★ `.env` + Settings |
| **Isolate** | 竞赛判题沙箱；cgroups；资源限制；每提交独立环境 | ☆ 规划 |
| **nsjail** | 另一种 Linux 沙箱方案 | ☆ 备选 |

---

## G. 算法竞赛领域概念

| 概念 | 前置背景知识 | 项目中 |
|------|--------------|--------|
| **ICPC** | 组队赛；多题；隐藏数据；严格时限；英文题面常见 | ★ 工作流之一 |
| **OI** | 信息学 Olympiad；子任务/部分分；中文题面常见 | ★ 工作流之一 |
| **标程（std）** | 官方/参考正确解；用于生成答案或验题 | ★ artifact kind |
| **暴力（brute）** | 小规模正确解；对拍时作 oracle | ★ stress 对比 |
| **对拍（Stress Test）** | 随机/构造数据；两程序输出比对；找 hack | ★ `stress` job |
| **SPJ / Checker** | 特殊判题；非唯一输出；checker 读 input/user/answer | ★ Python checker |
| **交互题（Interactive）** | interactor 与选手程序通信；非一次性 stdin | ★ Python interactor |
| **通信题（Communication）** | 多进程交互；protocol 描述 | ★ M3 支持 |
| **Polygon** | Codeforces 出题平台；题包 zip 结构；problem.xml | ★ 导出 |
| **CF Rating / 难度曲线** | Codeforces 难度分；套题递增检查 | ★ M4 Set Evaluator |
| **Gate / 阶段验收** | 人工 approve 后才进入下一阶段 | ★ HITL 核心 |
| **Verdict（AC/WA/TLE/CE/RTE）** | 判题结果语义 | ★ Runner 返回 |
| **testlib** | 竞赛交互/Checker 标准库（Polygon 生态） | ☆ 未完整接入 |

---

## H. 其他工具库

| 技术 | 前置背景知识 | 项目中 |
|------|--------------|--------|
| **asyncio** | Python 事件循环；`asyncio.run`；并发 IO | ★ Worker 主循环 |
| **PyYAML** | YAML 解析；`safe_load` | ★ 工作流加载 |
| **zipfile** | Python 标准库；内存 zip 打包 | ★ Polygon 导出 |
| **pytest** | Python 测试框架；fixture | ★ `tests/` |
| **Hatchling** | Python 打包/build backend | ★ `pyproject.toml` |
| **UUID** | 全局唯一标识；主键设计 | ★ 实体 ID |
| **SHA256** | 内容哈希；工件完整性 | ★ artifact 校验 |

---

## 学习路径建议（若从零补背景）

1. **Python 异步 + FastAPI + Pydantic** → 读懂 API 层  
2. **SQL + PostgreSQL + SQLAlchemy async** → 读懂数据模型与 Facade  
3. **Docker Compose 基础** → 本地跑通系统  
4. **算法竞赛验题概念（对拍、SPJ、交互题）** → 读懂 Runner/Worker  
5. **LLM API + Agent 工具调用** → 读懂 Session Agent 与后续 LangGraph 扩展  

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [PLAN.md](./PLAN.md) | 主规划与路线图 |
| [docs/architecture-runtime.md](./docs/architecture-runtime.md) | 运行架构详述 |
| [docs/data-model.md](./docs/data-model.md) | 数据模型 |
| [docs/integrations.md](./docs/integrations.md) | LLM、LangGraph 集成说明 |
| [docs/hitl-web.md](./docs/hitl-web.md) | HITL Web 规范 |
