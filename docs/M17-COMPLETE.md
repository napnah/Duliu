# M17 完成说明

套题评估 LangGraph、Session `evaluate_contest_set` 工具、Agent 工具面板与相关 API。

## 能力

| 项 | 说明 |
|----|------|
| **Contest LangGraph** | `scan_slots → evaluate → finalize`；`DULIU_USE_LANGGRAPH=1` 时 `evaluate_set` 走图 |
| **API** | `GET /api/contest-sets/langgraph/graph`、`GET /api/contest-sets/{id}/langgraph/status` |
| **Session Tool** | `evaluate_contest_set`（需 `contest_set_id` 上下文） |
| **Web** | Agent 侧栏 **工具面板**（注册工具列表 + 本会话最近调用） |
| **健康检查** | `milestone: M17`，`contest_langgraph` 随 LangGraph 开关 |

## 冒烟

```bash
bash scripts/m17-smoke-test.sh
```

## 后续

见 [M18-COMPLETE.md](./M18-COMPLETE.md)。
