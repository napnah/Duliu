# Windows 主机 + WSL2 开发指南

> Duliu 的 **验题、对拍、编译** 必须在 **Linux** 环境执行。在 Windows 上请通过 **WSL2** 运行 Docker 与 `docker compose`，不要在本机 Windows 直接跑 Worker/Runner。

## 1. 推荐架构

```
Windows 11/10
  └─ WSL2（Ubuntu 22.04+）
        ├─ 项目目录（放在 Linux 文件系统，如 ~/Duliu）
        ├─ Docker（Docker Desktop WSL 集成 或 WSL 内 docker-ce）
        └─ docker compose up → api + worker + postgres
  └─ 浏览器（Windows）→ http://localhost:8000
```

| 组件 | 运行位置 |
|------|----------|
| Postgres / API / Worker / g++ 评测 | **WSL2 内 Docker 容器（Linux）** |
| Web UI | 容器内提供，Windows 浏览器访问 |
| 在 `F:\` 上直接 `python -m duliu.worker` 跑对拍 | **不推荐**（无 Linux 评测链） |

## 2. 一次性安装

### 2.1 启用 WSL2

PowerShell（管理员）：

```powershell
wsl --install
# 或指定发行版
wsl --install -d Ubuntu-22.04
```

重启后进入 Ubuntu，创建 Linux 用户。

确认版本：

```powershell
wsl -l -v
# VERSION 应为 2
```

### 2.2 Docker

**方式 A（推荐）**：安装 [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)，设置中开启：

- **Use the WSL 2 based engine**
- **Resources → WSL integration** → 勾选你的 Ubuntu 发行版

**方式 B**：仅在 WSL 内安装 `docker-ce`（进阶，无 Desktop GUI）。

验证（在 **WSL Ubuntu** 终端）：

```bash
docker version
docker compose version
```

### 2.2b 一键配置（Duliu 脚本）

Windows 已装 Docker Desktop 但 WSL 里找不到 `docker` 时：

**PowerShell（启动 Desktop）：**

```powershell
cd F:\AI_Agent\Duliu
.\scripts\install-docker-desktop.ps1
```

**WSL：**

```bash
cd /mnt/f/AI_Agent/Duliu
bash scripts/wsl-setup-docker.sh
source ~/.bashrc
bash scripts/wsl-duliu-up.sh
```

脚本会把 `docker.exe` / `docker-compose.exe` 加入 PATH，并等待引擎就绪。

### 2.3 放置代码（重要）

为性能与文件监听，请把仓库放在 **WSL 家目录**，不要长期放在 `/mnt/f/...`：

```bash
# 在 WSL 内
cd ~
git clone https://github.com/napnah/Duliu.git
cd Duliu
```

若已在 Windows `F:\AI_Agent\Duliu` 开发，可拷贝或重新 clone 到 WSL：

```bash
cp -r /mnt/f/AI_Agent/Duliu ~/Duliu
cd ~/Duliu
```

## 3. 启动 Duliu

在 **WSL** 项目根目录：

```bash
cd ~/Duliu
docker compose up --build
```

浏览器（Windows 或 WSL 均可）打开：

**http://localhost:8000**

端口由 Docker Desktop 转发到 Windows localhost。

## 4. 常用命令（均在 WSL 执行）

```bash
# 后台运行
docker compose up -d --build

# 查看日志
docker compose logs -f api worker

# 停止
docker compose down

# 清空数据库卷（慎用）
docker compose down -v
```

## 5. 本地开发（不用 compose 时）

仍需 **WSL 内** 且安装 **g++**：

```bash
sudo apt update && sudo apt install -y g++ python3-pip python3-venv
cd ~/Duliu
python3 -m venv .venv && source .venv/bin/activate
pip install hatchling && pip install -e .

# 仅当本机有 Postgres 时（或用 compose 只起 postgres）
export DATABASE_URL=postgresql+asyncpg://duliu:duliu@localhost:5432/duliu

# 终端 1
uvicorn duliu.api.main:app --host 0.0.0.0 --port 8000
# 终端 2
python -m duliu.worker
```

Postgres 可单独起：

```bash
docker compose up -d postgres
```

## 6. 在 Cursor / VS Code 中开发

1. 安装扩展 **WSL**。
2. **Remote - WSL: Open Folder in WSL** → 选择 `\\wsl$\Ubuntu\home\<user>\Duliu` 或 `~/Duliu`。
3. 集成终端默认为 WSL Bash，在此执行 `docker compose`。

避免在 **PowerShell 项目根** 直接跑 Worker；评测逻辑依赖 Linux。

## 7. 故障排查

| 现象 | 处理 |
|------|------|
| `cannot connect to docker API` | 打开 Docker Desktop；确认 WSL 集成已启用 |
| `docker compose` 找不到 | Docker Desktop 新版用 `docker compose`；旧版 `docker-compose` |
| 页面打不开 localhost:8000 | `docker compose ps` 看 api 是否 Up；防火墙放行 |
| 对拍 CE / g++ not found | 确认用的是 **compose 的 worker 镜像**，不要在 Windows 裸跑 worker |
| `/mnt/f` 下 compose 很慢 | 项目移到 `~/Duliu` |

## 8. 与规划对齐

- **D-03**：Linux + Docker 验题 → Windows 用户通过 **WSL2 + Docker** 满足。
- **Isolate**：M1 为容器内 subprocess；M2 可再在 Runner 镜像中加 isolate。
