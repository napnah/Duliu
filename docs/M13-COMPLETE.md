# M13 完成说明

Python/Java isolate 运行 + Polygon 上传准备 API。

## 能力

| 项 | 说明 |
|----|------|
| **Python/Java isolate** | `DULIU_USE_ISOLATE=true` 时经 `isolate -d` 共享 `/usr` 等目录运行解释器 |
| **sandbox-status** | `python_java_via_isolate` 反映解释器沙箱是否可用 |
| **Polygon 准备上传** | `POST /api/problems/{id}/polygon/prepare-upload` 导出 zip 并写入 `spec_json.polygon_upload` |
| **上传状态** | `GET .../polygon/upload-status` |
| **Web** | 编辑器「准备 Polygon 上传」；流水线显示包路径 |

Polygon **无官方稳定上传 API**；`cookie_ready` 仅表示已存 Cookie，仍需在 Polygon 网页手动上传。

## 冒烟

```bash
bash scripts/m13-smoke-test.sh
```

## 后续

- 阶段 LLM Agent、Job WS：见 [M14-COMPLETE.md](./M14-COMPLETE.md)
