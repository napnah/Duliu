# M21 完成说明

Polygon zip 导入工件、对拍失败反例自动归档。

## 能力

| 项 | 说明 |
|----|------|
| **Polygon 包导入** | `POST .../polygon/import-package`：解压 zip → 写入 std/brute/statement/gen/checker/tests 等 |
| **反例归档** | 对拍失败时自动保存 `counterexample` 工件 + `spec_json.stress_counterexamples` |
| **API** | `GET .../counterexamples` 列表 |
| **Session Tools** | `import_polygon_package`、`list_counterexamples` |
| **Web** | 「导入 Polygon 包」「反例列表」 |
| **健康检查** | `milestone: M21`，`polygon_import`、`stress_counterexample_archive` |

## 冒烟

```bash
bash scripts/m21-smoke-test.sh
```

## 仍待（M22+）

- 反例一键载入编辑器、Polygon 双向工件 diff
