# M18 完成说明

Polygon 表单自动上传（实验）、LangGraph checkpoint 历史可视化、扩展 Session 工具。

## 能力

| 项 | 说明 |
|----|------|
| **Polygon 自动上传** | `POST /api/problems/{id}/polygon/auto-upload`：解析页面 multipart 表单并 POST zip（无表单则回退手动指引） |
| **Checkpoint 历史** | `GET .../langgraph/history`（单题 + 套题）；Web 流水线/套题页展示 |
| **Session Tools** | `prepare_polygon_upload`、`langgraph_history` |
| **Web** | 编辑器「Polygon 自动上传」；套题/流水线 Checkpoint 列表 |
| **健康检查** | `milestone: M18`，`polygon_form_upload: true` |

说明：Polygon 无稳定官方上传 API；自动上传为 **best-effort** 表单探测，失败时仍须手动上传。

## 冒烟

```bash
bash scripts/m18-smoke-test.sh
```

## 仍待（M19+）

- Polygon API（`problem.buildPackage` 等）深度集成、STRESS LLM 增强
