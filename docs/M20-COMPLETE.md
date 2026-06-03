# M20 完成说明

Polygon 包下载落盘、STRESS 对拍 LLM 解读、PACKAGE 与 Polygon API 双向同步。

## 能力

| 项 | 说明 |
|----|------|
| **problem.package 下载** | `POST .../polygon/api/download-package` → 落盘 `DULIU_PACKAGE_DIR/{problem_id}/polygon_api_*.zip` |
| **题包双向同步** | `POST .../package/sync-polygon`：本地 export + `commitChanges` + `buildPackage` + 下载 |
| **dispatch PACKAGE** | 自动尝试 Polygon 双向同步（未配置 API 则仅本地包） |
| **STRESS 解读** | Worker 对拍完成后写入 `interpretation`；`GET/POST .../stress/interpretation` |
| **Session Tools** | `polygon_api_download_package`、`package_sync_polygon`、`stress_interpret` |
| **健康检查** | `milestone: M20`，`stress_interpret`、`package_polygon_sync` |

## 冒烟

```bash
bash scripts/m20-smoke-test.sh
```

## 后续

见 [M21-COMPLETE.md](./M21-COMPLETE.md)。
