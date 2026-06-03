# Duliu

算法竞赛出题 AI Agent 系统 — 人机协同、阶段验收、ICPC/OI 双工作流。

## 文档

| 文件 | 说明 |
|------|------|
| [PLAN.md](./PLAN.md) | **主规划**：需求、架构、阶段、LangGraph、沙箱、路线图 |
| [TECHNICAL.md](./TECHNICAL.md) | **技术说明**：架构、实现现状、技术栈与前置知识索引 |
| [docs/stages.yaml](./docs/stages.yaml) | 单题阶段定义与驳回路由 |
| [docs/workflow_icpc.yaml](./docs/workflow_icpc.yaml) | ICPC 工作流参数（默认 13 题/套） |
| [docs/workflow_oi.yaml](./docs/workflow_oi.yaml) | OI 工作流参数（默认 4 题/套） |
| [schemas/](./schemas/) | `contest.yaml` / `spec.yaml` 结构说明 |
| [docs/hitl-web.md](./docs/hitl-web.md) | **HITL 主规范**：Web + Session Agent |
| [docs/hitl-cli.md](./docs/hitl-cli.md) | CLI 预留（CI/脚本） |
| [docs/data-model.md](./docs/data-model.md) | Postgres 三级树、单题隔离 |
| [docs/polygon.md](./docs/polygon.md) | Polygon 平台与题包结构 |
| [docs/architecture-runtime.md](./docs/architecture-runtime.md) | **运行架构**：监控、Session、Facade、Worker |
| [docs/decisions.md](./docs/decisions.md) | 已确认决策、LLM 说明 |
| [docs/integrations.md](./docs/integrations.md) | LLM 调用方式、LangGraph、爬虫与 Web 配 Key |
| [docs/web-editor-and-sandbox.md](./docs/web-editor-and-sandbox.md) | Monaco 编辑、一键对拍与沙箱分工 |
| [docs/non-original-workflow.md](./docs/non-original-workflow.md) | 非原创：网络标程、对拍、原题提交 |
| [docs/wsl-windows.md](./docs/wsl-windows.md) | **Windows 主机：WSL2 + Docker** |
| [docs/M1-quickstart.md](./docs/M1-quickstart.md) | M1 启动与验收 |

## 需求摘要（v0.4 已锁定）

1. 题目来源：原创 / 半原创（人机 idea）| 非原创（爬虫，仅学习）
2. 风格：ICPC 与 OI 两套工作流
3. 组织：套题（13/4 默认）或单题
4. 题型：传统、提交答案、交互、通信（支持 SPJ）
5. 每阶段结束需人工验收
6. HITL：Web **监控（详日志）** + **Session Agent** 专人机交互；CLI 预留
7. **Postgres** 三级树存题，单题隔离，工件版本回退
8. 后端 **Facade** 封装 Pipeline 多 Agent；**Worker** 跑对拍/编译
9. LangGraph 编排（封装在 pipeline 包内）
10. 标程/暴力：C++、Python、Java
11. 对抗评估 Agent（只评不出）
12. 套题评估 Agent（难度曲线）
13. CF 难度配置
14. Linux Docker + Isolate；严格比 out 或 SPJ
15. Polygon package 导出

实现按 [PLAN.md §16](./PLAN.md#16-实施路线图) 里程碑推进。

## M7–M17 ✅ 已完成

- [M7](docs/M7-COMPLETE.md) … [M15](docs/M15-COMPLETE.md) · [M16 IMPORT/Polygon UI](docs/M16-COMPLETE.md) · [M17 套题 LangGraph + 工具面板](docs/M17-COMPLETE.md)

## M6 ✅ 已完成

详见 [docs/M6-COMPLETE.md](./docs/M6-COMPLETE.md)。非原创 IMPORT、import_check、原题提交 Gate、流水线图 API。

## M5 ✅ 已完成

详见 [docs/M5-COMPLETE.md](./docs/M5-COMPLETE.md)。爬虫导入、CLI、`docker compose up`（api+worker）。

## M4 ✅ 已完成

详见 [docs/M4-COMPLETE.md](./docs/M4-COMPLETE.md)。套题树、Set Evaluator、难度曲线仪表盘。

## M3 ✅ 已完成

详见 [docs/M3-COMPLETE.md](./docs/M3-COMPLETE.md)。

## M2 ✅ 已完成

详见 [docs/M2-COMPLETE.md](./docs/M2-COMPLETE.md)。M1 能力保留。

## M1 ✅ 已完成

详见 [docs/M1-COMPLETE.md](./docs/M1-COMPLETE.md)。

**Windows 用户**：在 **WSL2** 中执行（[docs/wsl-windows.md](./docs/wsl-windows.md)）。

```bash
# WSL 首次配置 Docker
bash scripts/wsl-setup-docker.sh && source ~/.bashrc
# 若拉镜像 DNS 超时（Clash）：bash scripts/wsl-fix-dns.sh → Windows 执行 wsl --shutdown → 重开 WSL

docker compose up --build
# → http://localhost:8000
```

详见 [docs/M1-quickstart.md](./docs/M1-quickstart.md)。
