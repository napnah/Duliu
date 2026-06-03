# Duliu 已确认决策（ADR 摘要）

> 版本：0.4 · 与 PLAN.md 同步

## 已锁定

| ID | 决策 | 说明 |
|----|------|------|
| D-01 | **题目存 Postgres，单题隔离** | 不以目录树作为题面/数据主存储；三级逻辑树：根 → 套题 → 单题。见 [data-model.md](./data-model.md) |
| D-02 | **状态库 Postgres** | LangGraph checkpoint、阶段、会话、事件、配置均入 PG |
| D-03 | **Linux + Docker 运行** | 验题/评测在 Linux 容器内；**Windows 主机通过 WSL2 + Docker Desktop** 启动 compose，见 [wsl-windows.md](./wsl-windows.md) |
| D-04 | **判题严格性** | 传统题：**字节级**比较 `.out` 与选手输出（或 testlib 等价）；多解/提交答案/浮点：**必须**走 SPJ/checker |
| D-05 | **HITL 主界面 Web** | 浏览器：审批、Session 对话、观测、编辑工件；**CLI 预留**作自动化/脚本。见 [hitl-web.md](./hitl-web.md) |
| D-06 | **LLM 按 Agent 单独配置** | 各 Agent 可配不同 model/provider；密钥见下文 §LLM |
| D-07 | **Polygon** | 导出目标为 Polygon 兼容 package；见 [polygon.md](./polygon.md) |
| D-08 | **前后端分离 + Worker** | 前端：监控详日志 + Session 人机交互；后端：封装 Pipeline 多 Agent + Job Worker。见 [architecture-runtime.md](./architecture-runtime.md) |
| D-09 | **高度封装** | 对外仅 `PipelineFacade` / `SessionFacade` / `MonitorFacade` / `JobFacade`；Web 不得直连 LangGraph 或 Stage Agent |
| D-10 | **LLM 工具路径** | 后端 Tool Calling → Facade → DB/Worker；**非 MCP、非 CLI**；见 [integrations.md](./integrations.md) §1 |
| D-11 | **LangGraph 交付** | Python 库，随 Docker 镜像；用户 `compose up` 即可；图代码在 `pipeline/`/`session/` |
| D-12 | **前端密钥配置** | Web「设置」统一配置 LLM API Key + 爬虫 Token/Cookie（加密）；登录站由用户提供凭证 |
| D-13 | **Web 工件编辑** | Monaco 高亮；任意 artifact 可编辑；保存入 DB；见 [web-editor-and-sandbox.md](./web-editor-and-sandbox.md) |
| D-14 | **一键对拍** | `std` 等保存后 `POST .../stress/run` → Worker 沙箱；quick/full；见同上 |
| D-15 | **非原创** | 网络标程作草稿 + 必填 brute + 简化 stress + **强制原题提交确认**；见 [non-original-workflow.md](./non-original-workflow.md) |
| D-16 | **按输入一键运行** | Web 填 stdin → `POST .../run` → Worker/Isolate → stdout 等返回浏览器；见 [web-editor-and-sandbox.md](./web-editor-and-sandbox.md) §4 |

## ~~待你确认（Daemon）~~

已合并入 D-08/D-09。

## 仍开放

- 爬虫源站白名单（M5）
- Polygon 是否自动上传网页（默认仅本地 package）

---

## 运行方式摘要（D-08）

- **前端**：监控中心（事件流 + 大日志详查）+ Session 聊天；薄客户端。  
- **后端 API**：只调 Facade，转发 WebSocket 事件。  
- **Pipeline Engine**：LangGraph 阶段多 Agent，**不**对人类暴露。  
- **Job Worker**：对拍/编译/爬虫；长任务稳定执行，进度写入 `events`。  

`docker compose up` 启动 api、worker、postgres、minio、web。

---

## LLM 配置与 API Key

**不需要**每次「系统启动」都在终端交互输入 Key（不推荐）。

推荐方式（按优先级）：

1. **环境变量**：`DULIU_LLM__SESSION__API_KEY` 或通用 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`
2. **配置文件**（不入 Git）：`.duliu/secrets.yaml` 或 `~/.config/duliu/secrets.yaml`
3. **Web 设置页（推荐）**：设置 → 密钥与集成 → LLM Key + 爬虫 Token/Cookie → DB 加密（见 [integrations.md](./integrations.md)）

`config/agents.llm.yaml` 示例（无密钥，仅模型路由）：

```yaml
session:
  provider: anthropic
  model: claude-sonnet-4-20250514
solver:
  provider: openai
  model: gpt-4.1
adversarial:
  provider: anthropic
  model: claude-sonnet-4-20250514
```

启动时：`duliu serve` 读取 config + secrets；缺 Key 时 Web 首页提示「完成 LLM 配置」，**不阻塞**读-only 浏览。

---

## 修订历史

| 日期 | 变更 |
|------|------|
| v0.2 | D-01~07；HITL 从 CLI 主路径改为 Web 主路径 |
| v0.3 | D-08/D-09 运行架构：前端监控+Session，后端封装 Pipeline+Worker |
| v0.4 | D-10~12：LLM Tool Calling、LangGraph Docker、Web 密钥/爬虫配置 |
| v0.5 | D-13~15：Monaco 编辑、一键对拍、非原创原题提交 |
| v0.6 | D-16：浏览器输入一键沙箱运行并返回结果 |
