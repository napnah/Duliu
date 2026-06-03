# M15 完成说明

STRESS 阶段 Agent + Session OpenAI Tool Calling。

## 能力

| 项 | 说明 |
|----|------|
| **STRESS Agent** | `dispatch STRESS` 检查 std/brute、可种子 brute、排队 `stress` job |
| **Session Tools** | `OPENAI_API_KEY` + `DULIU_SESSION_TOOLS_ENABLED` 时用 function calling |
| **工具** | `dispatch_stage` `approve_stage` `enqueue_stress` `problem_status` `recent_events` |
| **回退** | 无 Key / 工具失败时仍走 M2 正则规则 |
| **API** | `GET /api/session/tools`；`GET /api/agents/stages` 含 `stress_agent` |

## 环境变量

- `DULIU_SESSION_TOOLS_ENABLED`（默认 true）

## 冒烟

```bash
bash scripts/m15-smoke-test.sh
```

## 后续

- IMPORT Agent、Polygon 探活、聊天 Tool UI：见 [M16-COMPLETE.md](./M16-COMPLETE.md)
