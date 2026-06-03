# 五步出题流程

Duliu 将命题拆成五个可随时唤起的**创作工作流**，与流水线阶段（`SPEC` → `STATEMENT` → …）并行：工作流产出工件并写入 `spec_json.creation_workflows`，不必一次跑完整条流水线。

## 流程一览

| ID | 名称 | 需要题目 | 产出工件 |
|----|------|----------|----------|
| `find_problem` | 1 · 找题 / 想 idea | 否 | `find_report`（有题目时） |
| `write_statement` | 2 · 编写题面 | 是 | `statement` |
| `solution_analysis` | 3 · 数据范围与解法 | 是 | `solution_plan` |
| `generate_data` | 4 · 生成数据 | 是 | `gen` |
| `write_editorial` | 5 · 编写题解 | 是 | `editorial` |

### 1. 找题

- 约束：难度（rating）、知识点、赛制（OI / ICPC）
- OI：评估是否**易于划分部分分**，给出子任务建议
- 当前为 LLM 检索策略 + 候选列表；**不自动爬 CF/洛谷**，需自行打开链接核验

### 2. 题面

- 风格：`codeforces` 或 `noip`（参数 `style`）
- 无 LLM 时回退到规则阶段 Agent `STATEMENT`

### 3. 解法分析

- **OI**：正解、中间解法链、子任务表、造数据与验分清单
- **ICPC**：正解 + 常见错解及测试构造建议

### 4. 生成数据

- 生成 `gen` 工件（Python），注释含 testlib / 部分分验分提示
- 可选 `--run-stress`（API `params.run_stress`）在已有 std+brute 时排队对拍

### 5. 题解

- Markdown 题解；无 LLM 时回退 `run_editorial_draft`

## Agent 对话唤起

在 Session Agent 中直接说触发词或显式 ID：

- `找题`、`搜题`、`想 idea`
- `写题面`、`题面`
- `解法分析`、`部分分`、`数据范围`
- `生成数据`、`造数据`
- `写题解`、`题解`
- `workflow:find_problem` / `工作流:write_statement`

可带参数：`难度 2200`、`知识点 dp,图论`、`OI`、`codeforces`。

对话下方会出现五步快捷按钮（`suggested_actions`）。

## CLI

```bash
export DULIU_API=http://localhost:8000
python -m duliu.cli workflow list
python -m duliu.cli workflow run find_problem --difficulty 2200 --topics "dp,树" --contest-style OI
python -m duliu.cli use <problem-uuid>
python -m duliu.cli workflow run write_statement --style noip
python -m duliu.cli workflow run solution_analysis
python -m duliu.cli workflow run generate_data
python -m duliu.cli workflow run write_editorial
python -m duliu.cli chat "找题 难度2300 知识点 网络流 OI" --problem-id <uuid>
```

## HTTP API

```http
GET /api/creation-workflows
POST /api/creation-workflows/{workflow_id}/run?problem_id=<optional>
POST /api/problems/{problem_id}/creation-workflows/{workflow_id}/run
```

Body: `{"params": {"difficulty": 2200, "topics": ["dp"], "style": "codeforces"}}`

## 与 IDE 本地目录

`pull` 后主要编辑 `statement.md`、`std.cpp`；工作流写入 API 工件，需 `pull` 同步到 `.duliu/problems/<id>/`。

详见 [ide-workflow.md](./ide-workflow.md)。
