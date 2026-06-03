# Duliu

算法竞赛出题 AI Agent 系统 — 人机协同、阶段验收、ICPC/OI 双工作流。

## 文档

| 文件 | 说明 |
|------|------|
| [PLAN.md](./PLAN.md) | **主规划**：需求、架构、阶段、LangGraph、沙箱、路线图 |
| [docs/stages.yaml](./docs/stages.yaml) | 单题阶段定义与驳回路由 |
| [docs/workflow_icpc.yaml](./docs/workflow_icpc.yaml) | ICPC 工作流参数（默认 13 题/套） |
| [docs/workflow_oi.yaml](./docs/workflow_oi.yaml) | OI 工作流参数（默认 4 题/套） |
| [schemas/](./schemas/) | `contest.yaml` / `spec.yaml` 结构说明 |

## 需求摘要（v0.1 已锁定）

1. 题目来源：原创 / 半原创（人机 idea）| 非原创（爬虫，仅学习）
2. 风格：ICPC 与 OI 两套工作流
3. 组织：套题（13/4 默认）或单题
4. 题型：传统、提交答案、交互、通信（支持 SPJ）
5. 每阶段结束需人工验收
6. 全程 HITL：可观测、人机切换、自然语言特殊设计
7. Git 管理工件，支持回退
8. LangGraph 编排
9. 标程/暴力：C++、Python、Java
10. 对抗评估 Agent（只评不出）
11. 套题完成后套题评估 Agent（难度曲线）
12. CF 标准难度范围配置
13. Docker + Isolate 沙箱隔离

实现按 [PLAN.md §16](./PLAN.md#16-实施路线图) 里程碑推进。
