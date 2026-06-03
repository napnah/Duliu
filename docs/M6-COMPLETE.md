# M6 完成说明

**里程碑**：非原创 IMPORT 阶段 · import_check 对拍 · 原题提交 Gate · Pipeline 图快照

## 交付物

| 模块 | 说明 |
|------|------|
| `M6_NON_ORIGINAL_ORDER` | `IMPORT` + M3 阶段链 |
| `facade/import_gate.py` | approve/dispatch 前校验提交确认与 import_check |
| `facade/import_flow.py` | 确认提交、enqueue import_check、brute 种子 |
| `pipeline/orchestrator.py` | `PipelineOrchestrator.snapshot`（LangGraph 接入点） |
| Worker | `stress` 模式 `import_check`（200 轮） |
| API | `GET /pipeline-graph`、`POST /import/check`、`POST /import/confirm-submission` |
| Web | 流水线页非原创卡片：原题链接、import_check、提交确认 |
| 种子 | `M6 NON_ORIGINAL Demo`（IMPORT 阶段 + std/brute） |

## 非原创流程

1. `POST /api/crawl/import` → 题目 `current_stage=IMPORT`，爬取题面。
2. 有 `std` 时自动排队 `import_check`；否则在 Web 保存 std 后手动点 **import_check**。
3. 勾选「已在原题平台提交」并保存。
4. **通过 IMPORT Gate** → 进入 `SPEC` …

## 运行

```bash
docker compose -f docker-compose.m1.yml restart duliu
bash scripts/m6-smoke-test.sh http://localhost:8000
```

## CLI

```bash
python -m duliu.cli import-check <problem-uuid> --wait
python -m duliu.cli confirm-submission <problem-uuid> --url "https://..."
```

## 后续（M7–M9 已补齐部分能力）

见 [M7-COMPLETE.md](./M7-COMPLETE.md) … [M10-COMPLETE.md](./M10-COMPLETE.md)。仍待：生产级 Isolate、完整 LangGraph 阶段图。
