# M3 完成清单

> 状态：**M3 已实现**

## 验收项

| # | 项 | 实现 |
|---|-----|------|
| 1 | 交互题运行 | `POST /run/interactive` + Python interactor 驱动标程 |
| 2 | 通信题 | `COMMUNICATION` 题型 + `protocol` 工件 + 同交互运行器 |
| 3 | checker 运行 | `program=checker` 的 `POST /run` |
| 4 | S7 PACKAGE | 阶段 + `dispatch PACKAGE` + `polygon_manifest` 工件 |
| 5 | Polygon 导出 | `GET /polygon/export` zip；`POST` 异步 Job |
| 6 | S8 EDITORIAL | 阶段 + `dispatch EDITORIAL` 生成题解草稿 |
| 7 | 阶段链 | `M3_STAGE_ORDER` = M2 + PACKAGE + EDITORIAL |
| 8 | 演示数据 | M3 Demo Interactive / Communication / Package Ready |

## 启动

```bash
docker compose -f docker-compose.m1.yml restart duliu
bash scripts/m3-smoke-test.sh
```

## Interactor 约定

Interactor 为 Python，环境变量 `DULIU_SOLUTION_BIN` 指向已编译标程；退出码 0 为 AC。

## 未包含（M4+）

- 完整 testlib 三方交互协议
- Polygon 自动上传
- Isolate 沙箱
- LangGraph 阶段 LLM Agent
