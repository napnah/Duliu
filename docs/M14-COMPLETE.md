# M14 完成说明

阶段 LLM/规则 Agent（SPEC/STATEMENT/SOLUTION/GENERATOR）+ Runner Job WebSocket 进度。

## 能力

| 项 | 说明 |
|----|------|
| **Stage Agent** | `dispatch` 上述阶段时调用 `run_stage_agent`；有 `OPENAI_API_KEY` 用 LLM，否则规则草稿 |
| **工件** | STATEMENT → `statement`；SOLUTION → `std`；GENERATOR → `gen`；SPEC 更新 `spec_json` |
| **配置** | `DULIU_STAGE_LLM_ENABLED`（默认 true） |
| **元数据** | `GET /api/agents/stages` |
| **Job WS** | `WS /api/jobs/{id}/ws` 推送 status 直至 done/failed |
| **Worker 事件** | `runner.job.running` / `runner.job.done` |
| **Web** | `pollJob` 优先 WebSocket |

## 冒烟

```bash
bash scripts/m14-smoke-test.sh
```

## 仍待（M15+）

- STRESS 专用 Agent、Tool-calling Session、Polygon 真自动上传
