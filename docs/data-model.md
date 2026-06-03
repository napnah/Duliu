# Duliu 数据模型：三级树 + Postgres 单题隔离

## 1. 逻辑层级（三级树）

```
根（Workspace / 租户根）
 └── 套题（ContestSet）
      └── 单题（Problem）  ← 隔离边界：状态机、工件、Runner、权限
```

| 层级 | 实体 | 说明 |
|------|------|------|
| **L1 根** | `workspace` | 一个 Duliu 部署实例的逻辑根；配置默认 LLM、Runner 地址、全局策略 |
| **L2 套题** | `contest_set` | ICPC(13) / OI(4) 槽位、难度分布、套级评估 |
| **L3 单题** | `problem` | **隔离单元**：阶段、control_mode、工件、对拍记录互不影响 |

单题可挂在套题槽位下，也可在根下 **独立单题**（`contest_set_id = NULL`）。

## 2. 单题隔离原则

- 所有 **阶段状态**、**LangGraph thread_id**、**工件版本**、**stress 任务** 均以 `problem_id` 为 FK，禁止跨题 JOIN 写。
- Runner 调用必须带 `problem_id`，容器内只挂载该题沙箱目录。
- Session 对话可切换当前 `problem_id`，但持久化线程按「会话 + 当前题」分表。

## 3. Postgres 核心表（概要）

```sql
-- L1
workspaces (id, name, config_json, created_at)

-- L2
contest_sets (
  id, workspace_id, name, contest_style,
  originality_policy, target_difficulty_json,
  slot_count, created_at
)
contest_slots (
  id, contest_set_id, slot_label, problem_id NULL, status
)

-- L3
problems (
  id, workspace_id, contest_set_id NULL, slot_id NULL,
  title, originality, problem_type, contest_style,
  control_mode, current_stage, spec_json, created_at
)

-- 工件（大对象可走 object_storage_key）
artifacts (
  id, problem_id, kind,  -- statement|std|gen|report|...
  version, content_text OR storage_key,
  sha256, author, created_at
)

artifact_versions -- 可选：完整版本链，支持回退

problem_stages (
  problem_id, stage_id, status, approved_by, approved_at, note
)

langgraph_checkpoints (
  thread_id, problem_id, checkpoint_blob, updated_at
)

sessions (
  id, workspace_id, user_id, summary_text, active_contest_set_id, active_problem_id
)
session_messages (...)

runner_jobs (
  id, problem_id, kind, status, log_storage_key, created_at
)

events (
  id, problem_id NULL, contest_set_id NULL, type, payload_json, created_at
)
```

## 4. 与 Git 的关系（修订）

- **主真相源**：Postgres `artifacts` + 版本表；回退 = 恢复某 `artifact.version` 或 checkpoint。
- **Git（可选）**：按 `problem_id` 导出镜像到 `export/<problem_id>/` 供 Polygon 打包或人工 rsync；**非**主存储。
- 规划 §8「Git 管理」改为 **数据库版本 + 可选导出**。

## 5. 与 Web / CLI 的 API

- `GET /api/workspaces/{ws}/contest-sets` — L2 列表
- `GET /api/problems/{id}` — L3 详情 + 阶段
- `PATCH /api/problems/{id}/artifacts/{kind}` — 人类/Web 编辑器保存
- Web 左侧树：**根 → 套题 → 单题** 与上表一致。
