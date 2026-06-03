# 在 Cursor / VS Code 中使用 Duliu 出题全流程

> 目标：**不依赖 Web 前端**，在 IDE 里编辑文件、在集成终端里跑与 Web 相同的 API/流水线，并让 Cursor Agent 可读可改本地工件。

## 1. 为什么需要 IDE 路径

| 问题 | Web 路径 | IDE + CLI 路径 |
|------|----------|----------------|
| 模型无法点浏览器 | 难以代你调试 UI | 终端输出、JSON、本地文件均可读 |
| 题面/标程编辑 | Monaco / Editor.md | 直接用 VS Code/Cursor 编辑器 |
| 观测流水线 | 监控页 | `duliu watch`、`duliu job` |
| Agent 对话 | 右侧聊天 | `duliu chat` / `duliu chat-repl` |
| 五步出题（找题→题面→解法→数据→题解） | Agent 芯片 | `duliu workflow run …` 或对话「找题」等 |

**原则**：业务逻辑仍走 **同一套 HTTP API**（`packages/duliu/api`），不 fork 一套后端；只增加 **CLI + 本地工件目录 + IDE 配置**。

五步创作流程说明见 [problem-creation-workflow.md](./problem-creation-workflow.md)。

## 2. 推荐架构（复用现有代码）

```
┌─────────────────────────────────────────────────────────────┐
│  Cursor / VS Code                                            │
│  · 打开 Duliu 仓库根目录                                       │
│  · 编辑 .duliu/problems/<uuid>/*.md / *.cpp                  │
│  · 集成终端：duliu …（与 Web 同 API）                          │
│  · Cursor Rule：.cursor/rules/duliu-workflow.mdc              │
│  · 任务：.vscode/tasks.json（一键 dispatch / run / pull）      │
└───────────────────────────┬─────────────────────────────────┘
                            │ DULIU_API=http://localhost:8000
┌───────────────────────────▼─────────────────────────────────┐
│  docker compose -f docker-compose.m1.yml up -d                 │
│  · API + Worker + Postgres（现有）                             │
└─────────────────────────────────────────────────────────────┘
```

工件权威存储仍在 **Postgres `artifacts` 表**；本地目录是 **镜像**，便于 IDE 编辑：

- `duliu pull <problem_id>` → 从 API 拉到 `.duliu/problems/<id>/`
- 在 IDE 修改后 `duliu push <problem_id>` → 写回 API

## 3. 环境准备（一次）

```bash
cd /path/to/Duliu
docker compose -f docker-compose.m1.yml up -d

export DULIU_API=http://localhost:8000
export PYTHONPATH=$PWD/packages

python -m duliu.cli health   # 应返回 status ok
python -m duliu.cli tree
```

在 VS Code / Cursor 用户设置或 `.vscode/settings.json`：

```json
{
  "terminal.integrated.env.linux": {
    "DULIU_API": "http://localhost:8000",
    "PYTHONPATH": "${workspaceFolder}/packages"
  }
}
```

## 4. 日常工作流（单题）

### 4.1 绑定当前题

```bash
# 导入非原创题
python -m duliu.cli crawl "https://codeforces.com/problemset/problem/1/A" --wait

# 记下 problem_id，设为当前题（写入 .duliu/active.json）
python -m duliu.cli use <problem-uuid>
```

之后多数命令可省略 `problem_id`（读取 `active`）。

### 4.2 拉取工件到 IDE

```bash
python -m duliu.cli pull          # 当前 active 题
# 或
python -m duliu.cli pull <uuid>
```

打开目录：`.duliu/problems/<uuid>/`

| 文件 | 对应 artifact |
|------|----------------|
| `statement.md` | 题面 |
| `editorial.md` | 题解 |
| `std.cpp` / `std.py` | 标程 |
| `brute.cpp` | 暴力 |
| `checker.py` | SPJ |

### 4.3 编辑 → 推回 → 运行

```bash
# 保存本地修改到服务端
python -m duliu.cli push

# 编译 / 运行（与 Web 相同 Runner）
python -m duliu.cli compile --program std
python -m duliu.cli run --input "1 2\n" --wait

# 对拍
python -m duliu.cli stress --mode quick --wait
```

### 4.4 流水线阶段（与 Web「调度 / 通过 Gate」一致）

```bash
python -m duliu.cli status
python -m duliu.cli dispatch --stage STATEMENT
python -m duliu.cli approve --stage STATEMENT

python -m duliu.cli import-check --wait    # 非原创 IMPORT
python -m duliu.cli confirm-submission --url "https://..."
```

### 4.5 Session Agent（终端里对话）

```bash
# 单条
python -m duliu.cli chat "对拍失败了，帮我看状态" 

# 交互 REPL（Enter 发送，/quit 退出）
python -m duliu.cli chat-repl
```

### 4.6 观测事件流

```bash
python -m duliu.cli watch              # 尾随当前题的 SSE 事件
python -m duliu.cli job <job-uuid> --wait
```

## 5. Cursor Agent 怎么用

1. 仓库已含 **`.cursor/rules/duliu-workflow.mdc`**：告诉 Agent 用 `python -m duliu.cli`，不要猜 Web DOM。
2. 你：「把当前题标程改成读入 a,b 输出 a+b，push 后 run 样例 1 2」
3. Agent 应执行：
   - 改 `.duliu/problems/<id>/std.cpp`
   - `duliu push`
   - `duliu run --input "1 2\n" --wait`
   - 把 `job.result_json` / verdict 贴回对话

**禁止**：让 Agent 直接改 Postgres 或绕过 Runner 在本地 `g++`（除非明确做本地调试）。

## 6. VS Code Tasks

打开命令面板 → **Tasks: Run Task**：

| 任务 | 作用 |
|------|------|
| Duliu: Health | 检查 API |
| Duliu: Tree | 列出题目 |
| Duliu: Pull Active Problem | 拉工件 |
| Duliu: Push Active Problem | 推工件 |
| Duliu: Status | 阶段状态 |
| Duliu: Dispatch Current Stage | 调度当前阶段 |
| Duliu: Approve Current Stage | 通过 Gate |
| Duliu: Run (stdin 1 2) | 运行标程 |
| Duliu: Watch Events | 事件流 |
| Duliu: Chat REPL | Agent 对话 |

## 7. 分阶段落地（建议里程碑）

| 阶段 | 内容 | 状态 |
|------|------|------|
| **M22a** | CLI 扩展：`use` `pull` `push` `run` `compile` `stress` `watch` `chat-repl` + `.vscode/tasks` + Cursor Rule + 本文档 | 本次 |
| **M22b** | `duliu init` 检测 Docker/g++；`pull` 时写 `meta.json` + 样例 `samples/` | 可选 |
| **M22c** | 文件监听 `duliu watch-files` 自动 push（保存即同步） | 可选 |
| **M22d** | 薄 VS Code 扩展：侧边栏显示 stage、一键 approve | 可选 |

**不必先做**：独立 Daemon、与 Web 双轨的后端——API 已足够。

## 8. 与 [hitl-cli.md](./hitl-cli.md) 的关系

- `hitl-cli.md` 是早期「CLI 主路径 + 磁盘 `problems/p_001/`」愿景。
- 当前实现以 **API + `.duliu/problems/` 镜像** 落地，与 DB 工件模型一致。
- Web 仍可用于可视化监控；**IDE 适合人类 + Cursor 结对调试**。

## 9. 故障排查

| 现象 | 处理 |
|------|------|
| `Connection refused` | `docker compose -f docker-compose.m1.yml up -d` |
| g++ 未安装 | 见 README / `docker/install-runner-deps.sh`，重启容器 |
| `pull` 后无 `std.cpp` | 先 `dispatch SOLUTION` 或 Web/CLI 保存标程 |
| Agent 改文件不生效 | 必须 `duliu push` 后才会进入 Runner |
