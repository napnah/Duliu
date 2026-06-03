# M19 完成说明

Polygon 官方 API 集成（含 `problem.buildPackage`）与 STRESS LLM 预检增强。

## 能力

| 项 | 说明 |
|----|------|
| **Polygon API 客户端** | key/secret 签名；`problem.info`、`problem.packages`、`problem.commitChanges`、`problem.buildPackage` |
| **API 路由** | `GET /api/polygon/api/status`；`POST .../polygon/api/link|sync|build-package` |
| **配置** | 设置页 / `DULIU_POLYGON_API_KEY` + `DULIU_POLYGON_API_SECRET` |
| **STRESS LLM** | `dispatch STRESS` 前 LLM/规则预检，推荐 `quick` / `import_check` 并写入 `spec_json.last_stress.preflight` |
| **Session Tools** | `polygon_api_sync`、`polygon_api_build_package`、`stress_preflight` |
| **健康检查** | `milestone: M19`，`polygon_api`、`stress_llm` |

## 冒烟

```bash
bash scripts/m19-smoke-test.sh
```

## 后续

见 [M20-COMPLETE.md](./M20-COMPLETE.md)。
