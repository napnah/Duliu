# Duliu MCP

Duliu 的 **相对独立子项目**：为 Cursor / Claude Desktop 等 MCP 客户端提供出题与数据导出工具。

## 目录结构

```
mcp/duliu-mcp/
├── pyproject.toml          # 独立依赖与入口（不依赖根 pyproject）
├── .env.example
├── README.md
├── src/duliu_mcp/
│   ├── server.py           # FastMCP 入口
│   ├── config.py           # MCP 专用配置
│   ├── client/
│   │   └── duliu_api.py    # 通过 HTTP 调用 Duliu API（与主包解耦）
│   ├── tools/
│   │   ├── registry.py     # 统一注册所有 tool
│   │   ├── problems.py     # 题目查询
│   │   ├── artifacts.py    # 工件读取
│   │   └── export_data.py  # 出数据：测试点、Polygon package
│   ├── services/
│   │   └── polygon_exporter.py  # 导出逻辑（可逐步迁入主包实现）
│   └── schemas/
│       └── tool_inputs.py  # Pydantic 入参模型
├── tests/
└── examples/
    └── cursor-mcp.json     # Cursor 配置示例
```

## 设计原则

| 原则 | 说明 |
|------|------|
| **独立包** | 自有 `pyproject.toml`，可单独 `pip install -e .` |
| **API 边界** | 默认经 `DULIU_API_BASE_URL` 调主服务，不直接 import `duliu` |
| **工具分层** | `tools/` 薄封装 → `client/` HTTP → `services/` 复杂导出逻辑 |
| **可扩展** | 新增工具 = 新文件 + 在 `registry.py` 注册一行 |

## 快速开始

```bash
cd mcp/duliu-mcp
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/WSL: source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# 确保 Duliu API 已启动：docker compose up（根目录）

# stdio 模式（Cursor / Claude Desktop）
duliu-mcp
# 或
python -m duliu_mcp
```

## Cursor 配置

将 `examples/cursor-mcp.json` 合并到项目或用户级 MCP 配置，按本机路径修改 `command` / `cwd`。

## 已提供的 Tools（模板）

| Tool | 用途 |
|------|------|
| `duliu_list_problems` | 列出题目 |
| `duliu_get_problem` | 获取单题详情 |
| `duliu_list_artifacts` | 列出工件（题面、标程、gen 等） |
| `duliu_export_test_data` | 导出测试数据（.in/.out 或 zip） |
| `duliu_export_polygon_package` | 导出 Polygon 兼容题包目录 |

导出类工具在 `services/polygon_exporter.py` 中实现骨架；M2+ 可对接主包 `packages/duliu/polygon/` 或 DB。

## 与主仓库的关系

```
Duliu/                          # 主仓库
├── packages/duliu/             # 主应用（API、Worker、DB）
├── mcp/duliu-mcp/              # ← 本子项目（MCP 工具面）
└── pyproject.toml              # 主包，互不混装
```

主 README 可增加一行指向 `mcp/duliu-mcp/README.md`，无需把 MCP 依赖写进根 `pyproject.toml`。
