# M10 完成说明

Postgres LangGraph checkpointer（可回退 memory）、监控 SSE、Codeforces AC 标程拉取。

## 能力

| 项 | 说明 |
|----|------|
| Checkpointer | `DULIU_LANGGRAPH_CHECKPOINT=postgres\|memory`；启动时 `get_checkpointer()`，Postgres 失败自动 memory |
| LangGraph | `GET /api/problems/{id}/langgraph/history`；dispatch 结果含 `checkpointer` |
| SSE | `GET /api/monitor/events/stream?problem_id=&contest_set_id=`；Web 监控页 `EventSource` |
| AC 标程 | `POST /api/problems/{id}/import/fetch-std`（需设置页 CF Cookie） |
| 健康检查 | `milestone: M10`，`langgraph_checkpoint` 字段 |

## 环境变量

- `DULIU_LANGGRAPH_CHECKPOINT` — 默认 `memory`；`docker-compose.m1.yml` 默认 `postgres`
- `DULIU_SSE_POLL_SECONDS` — SSE 轮询 DB 间隔，默认 `2`

## 依赖

`langgraph-checkpoint-postgres`、`psycopg[binary]`（见 `requirements.txt`）

## 冒烟

```bash
bash scripts/m10-smoke-test.sh
```

重建容器并挂载 `packages` 卷后执行。Postgres checkpointer 需镜像内安装新依赖或 `docker compose -f docker-compose.m1.yml build --no-cache`。

## 后续

- Isolate 接入 Runner：见 [M11-COMPLETE.md](./M11-COMPLETE.md)
- 仍待 M12+：完整 LangGraph 阶段图、WebSocket、Polygon 自动上传
