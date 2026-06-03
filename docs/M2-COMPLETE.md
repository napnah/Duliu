# M2 完成清单

> 状态：**M2 已实现**

## 验收项

| # | 项 | 实现 |
|---|-----|------|
| 1 | OI 工作流 | `docs/workflow_oi.yaml` + 默认 4 槽 OI 套题 + **M2 Demo OI A+B** |
| 2 | SPJ | `checker` 工件 + `use_checker` 运行 + stress 可选 SPJ |
| 3 | 三语言 Runner | C++ / Python3 / Java（`artifact.language`） |
| 4 | S6 对抗评估 | 阶段 `ADVERSARIAL_REVIEW` + `dispatch` + 规则 Agent 报告 |
| 5 | Web Session Agent | `/api/sessions` 聊天 + 规则工具（dispatch/approve/stress/状态/事件） |
| 6 | LLM 配置 | `PUT /api/workspace/secrets` + 可选 OpenAI |
| 7 | dispatch API | `POST /api/problems/{id}/dispatch` |
| 8 | 运行增强 | 期望输出 AC/WA、`run/compare`、仅编译 |
| 9 | 监控 run_id | `events.run_id` + 筛选 |
| 10 | 演示数据 | OI 题、SPJ 题、Adv Ready 题 |

## 启动

```bash
docker compose -f docker-compose.m1.yml up -d --build
bash scripts/m2-smoke-test.sh
```

可选环境变量：`OPENAI_API_KEY`（Session 增强回复）

## 数据库升级

已有 M1 卷时，启动时会 `ALTER TABLE events ADD COLUMN IF NOT EXISTS run_id`，并 `ensure_m2_stages()` 补 ADVERSARIAL_REVIEW 阶段。

## 未包含（M3+）

- 完整 LangGraph ProblemGraph / 阶段 LLM Agent
- Isolate 沙箱
- WebSocket 实时推送
- 交互题 interactor 运行

## 目录新增

```
packages/duliu/
  workflow/     # ICPC/OI YAML 加载
  session/      # Session Agent
  agents/       # 对抗评估（规则）
  facade/secrets.py
docs/M2-COMPLETE.md
scripts/m2-smoke-test.sh
```
