# M11 完成说明

Isolate 接入 C++ `run_source` / `run_compiled`；`.env` 引导爬虫 Cookie；健康检查 `M11`。

## 能力

| 项 | 说明 |
|----|------|
| **Isolate 运行** | `DULIU_USE_ISOLATE=true` 且 PATH 有 `isolate` 时，**C++ 已编译二进制** 经 `isolate` 执行 |
| **回退** | 无 isolate 或未开启 → 原 subprocess |
| **Python/Java** | 仍为 subprocess（后续可扩展 `--share-dir`） |
| **`.env` Cookie** | `DULIU_CF_COOKIE` / `DULIU_LUOGU_COOKIE` / `DULIU_POLYGON_COOKIE` 在 API 启动时写入 workspace（仅当 DB 尚无该 secret） |
| **Runner 状态** | `GET /api/runner/sandbox-status` 含 `cpp_via_isolate` |

## 环境变量

见 [.env.example](../.env.example)。

## 冒烟

```bash
bash scripts/m11-smoke-test.sh
```

可选：宿主机安装 `isolate` 并 `DULIU_USE_ISOLATE=true` 后，`sandbox-status.mode` 应为 `isolate`。

## 后续

- WebSocket + 三节点 dispatch 图：见 [M12-COMPLETE.md](./M12-COMPLETE.md)
- 仍待 M13+：Python/Java isolate、LLM 阶段 Agent、Polygon 自动上传
