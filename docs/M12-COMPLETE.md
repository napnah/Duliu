# M12 完成说明

WebSocket 监控通道 + LangGraph 三节点 dispatch 图（prepare → dispatch → finalize）。

## 能力

| 项 | 说明 |
|----|------|
| **WebSocket** | `WS /api/monitor/events/ws?problem_id=&contest_set_id=`，与 SSE 同源 DB 轮询 |
| **Web 监控** | 优先 WebSocket，失败回退 SSE，再回退 REST 轮询 |
| **LangGraph** | 节点 `prepare` → `dispatch` → `finalize`；dispatch 结果含 `graph` / `finalized` |
| **元数据** | `GET /api/langgraph/dispatch-graph`；`langgraph/status` 含 `graph` |
| **健康检查** | `milestone: M12`，`monitor_transport: websocket+sse` |

## 冒烟

```bash
bash scripts/m12-smoke-test.sh
```

## 仍待（M13+）

- Python/Java isolate、LLM 阶段 Agent 真实现
- Polygon 自动上传、Runner Job WebSocket 进度
