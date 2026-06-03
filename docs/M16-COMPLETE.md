# M16 完成说明

IMPORT 阶段 Agent、Polygon Cookie 探活上传尝试、Agent 聊天工具条展示。

## 能力

| 项 | 说明 |
|----|------|
| **IMPORT Agent** | `dispatch IMPORT`（仅 NON_ORIGINAL）：种子 brute、生成 import 清单（LLM/规则） |
| **Polygon 探活** | `POST /api/problems/{id}/polygon/attempt-upload`：准备 zip + 用 Polygon Cookie 探活会话 |
| **Web** | Agent 回复下方显示 **tool chips**；编辑器「Polygon 探活」按钮 |
| **健康检查** | `milestone: M16`，`import_agent: true` |

说明：Polygon **无稳定自动上传 API**；探活成功后仍需在网页手动上传 zip。

## 冒烟

```bash
bash scripts/m16-smoke-test.sh
```

## 仍待（M17+）

- Polygon 真·表单上传、STRESS LLM 增强、套题 LangGraph
