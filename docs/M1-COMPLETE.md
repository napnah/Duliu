# M1 完成清单

> 状态：**M1 已实现**（代码骨架 + Web + Runner + Gate）

## 验收项

| # | 项 | 实现 |
|---|-----|------|
| 1 | Postgres 三级树 | `workspaces` / `contest_sets` / `problems` |
| 2 | 单题隔离 | `problem_id` FK；工件/Job/Event |
| 3 | Web 导航 | 工作区、套题列表、单题列表 |
| 4 | Monaco 编辑工件 | `std` / `brute` / `statement` 等 |
| 5 | 保存工件版本 | `PUT /artifacts/{kind}` → version++ |
| 6 | stdin 一键运行 | `POST /run` → Worker → g++ 沙箱 |
| 7 | 快速对拍 | `POST /stress/run` → std vs brute 字节比较 |
| 8 | 阶段 Gate | `POST .../stages/{id}/approve` |
| 9 | 监控事件 | `GET /api/monitor/events` |
| 10 | 演示数据 | M1 Demo A+B + M1 Demo ICPC Set |

## 启动

```bash
source ~/.bashrc   # WSL + Docker 已配置
cd ~/Duliu   # 推荐；/mnt/f 上 git/docker 可能更慢

# 方式 A：M1 单容器（API+Worker 一体）
docker compose -f docker-compose.m1.yml up -d --build

# 方式 B：镜像构建 apt 失败时 — 仅 DB 用 Docker，本机跑 API+Worker（需 WSL 内 g++）
bash scripts/m1-dev-local.sh

# 方式 C：完整三服务
# docker compose up -d --build
```

构建仍失败时可在项目根设置镜像源后重试：

```bash
export APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
docker compose -f docker-compose.m1.yml build --no-cache
```

冒烟（可选）：

```bash
bash scripts/m1-smoke-test.sh
```

## 未包含（M2+）

- LangGraph / LLM 阶段 Agent
- Session Agent 聊天
- Isolate 沙箱（M1 为容器内 subprocess）
- 非原创爬虫、Polygon 导出、对抗评估

## 目录

```
packages/duliu/
  api/       FastAPI + 静态 Web
  db/        SQLAlchemy 模型
  facade/    Pipeline / Job / Event
  runner/    compile + run + stress
  worker/    Job 队列消费
  web/static Monaco UI
```
