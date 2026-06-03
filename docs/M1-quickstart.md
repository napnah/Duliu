# M1 快速启动

## 范围（已实现骨架）

- Postgres 三级树（workspace / contest_set / problem）
- Web：导航、Monaco 编辑、阶段 Gate、监控事件
- **按输入运行**（`run_single`）与 **快速对拍**（`stress`，字节比较）
- API + Worker + Runner（Linux 容器内 `g++`）
- 演示题「M1 Demo A+B」首次启动自动种子

## 启动

### Windows 主机 → 使用 WSL2（必读 [wsl-windows.md](./wsl-windows.md)）

在 **WSL Ubuntu** 内（项目建议放在 `~/Duliu`，勿依赖 `/mnt/f` 跑 Docker）：

```bash
cd ~/Duliu
docker compose up --build
```

需已安装 **Docker Desktop（WSL2 引擎 + 集成）** 或 WSL 内 Docker。

### Linux / macOS

```bash
cd Duliu
docker compose up --build
```

浏览器（Windows 或 WSL）：**http://localhost:8000**

## 本地开发（可选）

**Windows**：请在 **WSL** 内安装 `g++` 与 venv，见 [wsl-windows.md](./wsl-windows.md) §5。不要在 PowerShell 下直接跑 Worker 对拍。

```bash
pip install hatchling && pip install -e .
uvicorn duliu.api.main:app --reload   # 终端 1
python -m duliu.worker                # 终端 2（WSL/Linux only）
```

## 验收步骤

1. 左侧选择 **M1 Demo A+B**
2. 打开 `std`，点 **运行**（样例输入 `3 4`）→ Output 显示 `7`
3. 点 **快速对拍** → 提示通过
4. 当前阶段 **SPEC** → **通过当前阶段** → 阶段推进到 STATEMENT
5. 下方 **监控** 出现 `runner.*` / `gate.*` 事件

## M2 已完成

见 [M2-COMPLETE.md](./M2-COMPLETE.md)。`bash scripts/m2-smoke-test.sh`
