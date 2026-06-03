# M5 完成说明

**里程碑**：爬虫导入 + Worker 可选分离 + CLI + 设置页服务端配置

## 交付物

| 模块 | 说明 |
|------|------|
| `crawler/` | 白名单 URL、httpx 抓取、CF/Luogu/AtCoder 简易解析 |
| `JobKind.CRAWL_IMPORT` | Worker 异步导入题面到 `statement` 工件 |
| API | `POST /api/crawl/import`、`GET/PUT /api/workspace/crawler-config`、`POST /api/jobs/{id}/cancel`、`GET /api/monitor/events/export` |
| CLI | `python -m duliu.cli`：`health` `tree` `status` `approve` `dispatch` `crawl` `job` `chat` |
| Compose | `docker-compose.yml`：postgres + **api** + **worker** 分离 |
| Web 设置 | 爬取站点与 Cookie 保存到服务端（不再仅 localStorage） |

## 运行

```bash
# M5 标准栈（API + Worker 分离，挂载 packages 卷）
docker compose up -d --build

# 或继续 M1 单容器开发
docker compose -f docker-compose.m1.yml up -d --force-recreate duliu

bash scripts/m5-smoke-test.sh http://localhost:8000
```

## CLI 示例

```bash
export DULIU_API=http://localhost:8000
export PYTHONPATH=$PWD/packages

python -m duliu.cli health
python -m duliu.cli tree
python -m duliu.cli crawl "https://codeforces.com/problemset/problem/1/A" --wait
python -m duliu.cli status <problem-uuid>
python -m duliu.cli chat "状态" --problem-id <uuid>
```

## 爬虫白名单

- `codeforces.com`
- `atcoder.jp`
- `luogu.com.cn`

需在设置页配置对应 Cookie（登录站点）以提高抓取成功率。

## 未包含（已在 M6 补齐部分）

- `import_check`、IMPORT 阶段、提交 Gate → 见 [M6-COMPLETE.md](./M6-COMPLETE.md)
- 仍待：LangGraph 真图、Isolate、AC 标程自动拉取、独立 crawler 容器
