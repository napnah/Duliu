# M4 完成说明

**里程碑**：套题 13/4 槽位模型 + Set Evaluator + Web 套题仪表盘 + 难度曲线

## 交付物

| 模块 | 说明 |
|------|------|
| `ContestSet.status` / `set_eval_json` | 套题生命周期与评估报告持久化 |
| `agents/set_evaluator.py` | 规则化套题评估：槽位填充、DONE 检查、难度曲线、chart 数据 |
| `facade/contest.py` | 套题详情、槽位绑定/建题、评估、评估 Gate |
| API | `GET/POST /api/contest-sets/*`、evaluate、approve-eval、事件按 `contest_set_id` 筛选 |
| Web | 套题树点击、仪表盘、槽位表、难度柱状图、评估/通过按钮 |
| Session | `套题评估` / `通过套题` / `套题状态`（需 `contest_set_id`） |
| 种子 | `M4 Demo ICPC Mini`（4 槽 A–D，递增 CF rating） |

## 运行

```bash
docker compose -f docker-compose.m1.yml up -d
bash scripts/m4-smoke-test.sh http://localhost:8000
```

浏览器打开 `http://localhost:8000/`，侧栏选择 **M4 Demo ICPC Mini**，查看难度曲线与槽位表。

## 套题评估流程

1. 各槽位绑定或新建题目，`spec.difficulty.rating` 建议递增。
2. `POST /api/contest-sets/{id}/evaluate` → `SET_EVAL_PENDING` + `set_eval_json`。
3. `POST /api/contest-sets/{id}/approve-eval` → `SET_EVAL_APPROVED`。

ICPC 新建套题默认 **13** 槽；OI 默认 **4** 槽（与 PLAN 一致）。

## 与 M3 关系

M4 在 M3 单题流水线之上增加套题维度；单题编辑、对拍、Polygon、交互题仍沿用 M3 能力。
