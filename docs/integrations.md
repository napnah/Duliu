# Duliu 集成说明：LLM 调用、LangGraph、爬虫与前端配置

> 回答「配好 Key 是否自动改文件」「MCP 还是 CLI」「LangGraph 谁安装」「爬虫 token」等实现期问题。

---

## 1. LLM API 如何调用？会不会自动改文件？用 MCP 还是 CLI？

### 1.1 结论（一句话）

**在 Web 配好 API Key 之后**，后端 Agent 可在授权下**自动出题**（写数据库里的题面/代码、触发对拍），但路径是 **Duliu 后端 Python 工具（Tool Calling）→ Facade → DB/Worker**，**不是** Cursor MCP，也**不是**用 CLI 去改你磁盘上的任意文件。

### 1.2 调用链

```
Web 设置页保存 API Key（加密存库）
    ↓
duliu-api 启动时加载 workspace_secrets
    ↓
Session Agent / 阶段 Agent（LangGraph 节点内）
    ↓ 官方 SDK HTTP 调用
OpenAI / Anthropic / … API
    ↓ 模型返回 tool_calls
Agent 内置工具（白名单），例如：
  - save_artifact(problem_id, kind, content)  → Postgres
  - dispatch_stage(problem_id, STAGE)
  - enqueue_stress(problem_id)
  - query_events(problem_id)
    ↓
Monitor 事件流 → 前端监控中心可见
```

### 1.3 与 MCP、CLI 的区别

| 方式 | Duliu 是否采用 | 说明 |
|------|----------------|------|
| **MCP（Model Context Protocol）** | **默认不采用** | MCP 是 IDE（如 Cursor）连外部工具的协议；Duliu 是独立 Web 服务，用 **自有 Tool 定义**（函数 schema + Python 实现）即可 |
| **CLI（duliu 命令）** | **给人/CI 用** | 例如 `duliu approve`、`duliu compose up`；**不是** LLM 执行工具的路径 |
| **后端 Tool Calling** | **采用（主路径）** | LangChain/LangGraph 标准 `bind_tools`；与 OpenAI/Anthropic function calling 对齐 |

可选远期：提供 **MCP Server** 暴露 `dispatch`/`status` 给 Cursor 联动——**非 M1**，不阻塞主流程。

### 1.4 「自动对文件操作」指什么？

| 操作 | 实现 |
|------|------|
| 改题面、标程、gen | 写入 **`artifacts` 表**（新版本）；Web 编辑器读写的也是 API 同源数据 |
| 编译、对拍 | **Job Worker** + Linux Runner 容器，**不经过 LLM 直接 exec** |
| 改你本机 Cursor 里打开的文件 | **不会**自动改；除非你用「导出到目录」后自己同步 |

`control_mode=HUMAN` 时，阶段 Agent **暂停自动写入**；Session 只建议，或由你在 Web 编辑器保存。

### 1.5 前端配置 API Key（已锁定）

**设置 → 密钥与集成** 单页（workspace 级）：

| 配置项 | 存储 | 用途 |
|--------|------|------|
| 各 Agent LLM Key（可继承「默认 Key」） | `workspace_secrets` 加密 | Session / Solver / … |
| 默认 Provider + Model | `workspace.config` | 见 `agents.llm.yaml` |

- 保存后 **无需重启终端**；API 热加载或下次请求读取。
- **不需要**每次启动在命令行输入 Key。
- Key **不出现在**前端 DOM/日志；仅显示 `sk-...****` 掩码。

---

## 2. LangGraph 具体怎么用？要装开发工具吗？

### 2.1 LangGraph 是什么

**Python 库**（`pip install langgraph`），用于定义 **有状态、可中断、可循环** 的 Agent 工作流（出题阶段图、Session 小图）。

### 2.2 谁安装、在哪运行

| 角色 | 需要做什么 |
|------|------------|
| **最终用户（你）** | `docker compose up` 即可；镜像内已含 Python 依赖 + LangGraph |
| **开发者** | 克隆仓库 → Docker 构建；可选本地 `uv sync` 跑测试 |
| **实现阶段** | 由项目在 `packages/duliu/pipeline/`、`session/` **编写图代码**（可在 Cursor 里由 AI 辅助完成） |

**你不需要**单独安装 LangGraph Studio 才能用 Duliu。  
**可选**：LangGraph Studio / `langgraph dev` 仅用于开发调试 Pipeline 图（M2+ 文档补充）。

### 2.3 在 Duliu 中的位置

```python
# 概念结构（实现期）
from langgraph.graph import StateGraph
from langgraph.checkpoint.postgres import PostgresSaver

builder = StateGraph(ProblemState)
builder.add_node("SOLUTION", run_solver_agent)
builder.add_node("GATE", human_gate_interrupt)
builder.add_edge(...)
graph = builder.compile(checkpointer=postgres_saver)
# 仅 PipelineFacade.invoke(graph, problem_id=...)
```

- **Checkpoint** 存 Postgres → 支持阶段中断、Gate 等待、`rollback`。
- **与 Web 关系**：Web 只调 Facade；**不嵌入** LangGraph 运行时到浏览器。

### 2.4 是否需要「你来完成」

- **规划与文档**：已就绪。  
- **代码实现**：按 PLAN 里程碑 M1 起在仓库中落地；你本地跑 compose 验证。  
- 你无需成为 LangGraph 专家；只需会启动 Docker 与使用 Web。

---

## 3. 爬虫稳定性、登录 Token、前端配置

### 3.1 架构

```
Web 配置爬虫 Token / Cookie
    ↓
workspace_secrets（加密）+ crawler_profiles 表（按站点）
    ↓
Job Worker · crawl job（独立 Crawler 容器，出站网络）
    ↓
规范化 → problems / artifacts（IMPORT 阶段）
    ↓
events 日志 → 监控中心
```

仅 **NON_ORIGINAL** 且 **源站在白名单** 时启用（M5）。

### 3.2 稳定性手段

| 手段 | 说明 |
|------|------|
| **队列 + Worker** | 爬虫不阻塞 API；失败可重试（指数退避，上限 3~5 次） |
| **限速** | 每域名 QPS 上限、随机 jitter |
| **熔断** | 连续失败暂停该 profile，前端提示「检查 Token」 |
| **超时** | 单请求/单任务总超时 |
| **结构化日志** | 每次请求 status、耗时写入 `events`；不记录完整 Cookie 明文 |
| **解析器版本化** | `crawler_profiles.parser_version`，站点改版可切换 |
| **健康检查** | 定时 `HEAD`/样例 URL 探测（可选） |

### 3.3 需要登录的网站

**是**：若源站必须登录（如部分 OJ 私有题库），需要用户在 **Web 设置** 提供：

| 类型 | 示例字段 | 存储 |
|------|----------|------|
| **API Token** | `Authorization: Bearer …` | 加密 secret |
| **Session Cookie** | 导出 Cookie 字符串或 `cf_clearance` 等 | 加密 secret |
| **账号密码** | **不推荐**存明文；优先 Cookie/Token | — |

按 **站点 profile** 配置（如 `codeforces_robot`、`atcoder_session`），Worker 发请求时注入 Header/Cookie。

**用户责任**：Token 过期需在前端更新；系统检测 401/403 时事件告警「凭证失效」。

### 3.4 前端「简单配置」页（已锁定）

**设置 → 密钥与集成** 统一入口：

```
┌─ LLM ─────────────────────────────────┐
│ 默认 Provider: [Anthropic ▼]         │
│ 默认 API Key:  [••••••] [测试连接]   │
│ ▶ 按 Agent 覆盖（Session / Solver…） │
└──────────────────────────────────────┘
┌─ 爬虫（NON_ORIGINAL）────────────────┐
│ [+] 添加站点 Profile                  │
│  Codeforces  Cookie: [••••] [测试]    │
│  AtCoder     Token:  [••••] [测试]    │
└──────────────────────────────────────┘
```

- **[测试连接]**：后端发探测请求，结果显示在 Monitor。
- 所有密钥 **加密-at-rest**（应用层 AES 或 Postgres pgcrypto + 主密钥 env）。

### 3.5 合规

- 默认仅 **个人学习**、**用户自有凭证**、**白名单域名**。
- 不提供绕过 CAPTCHA/付费墙的通用能力；ToS 由用户在设置页确认勾选。

---

## 4. 决策 ID（写入 decisions.md）

| ID | 决策 |
|----|------|
| D-10 | LLM 工具路径 = 后端 Tool Calling + Facade；**非 MCP、非 CLI** |
| D-11 | LangGraph = 后端 Python 依赖，Docker 交付；用户不单独安装 |
| D-12 | API Key + 爬虫 Token/Cookie = **Web 设置页** 加密存储；登录站由用户提供凭证 |
