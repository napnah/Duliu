# Docker 故障排查（Windows + WSL）

## 已配置内容

| 脚本 | 作用 |
|------|------|
| `scripts/install-docker-desktop.ps1` | Windows 启动 Docker Desktop |
| `scripts/wsl-setup-docker.sh` | WSL 将 `docker.exe` 加入 PATH，等待引擎就绪 |
| `scripts/wsl-duliu-up.sh` | 启动 `docker compose up --build` |
| `scripts/wsl-fix-dns.sh` | Clash 导致 `auth.docker.io` DNS 超时时修复 WSL DNS |

## 常见错误

### 1. WSL 里找不到 `docker`

```bash
bash /mnt/f/AI_Agent/Duliu/scripts/wsl-setup-docker.sh
source ~/.bashrc
```

### 2. `npipe docker_engine` / daemon not running

在 Windows 打开 **Docker Desktop**，等到状态 **Running**。

### 3. `auth.docker.io` DNS 超时（你当前环境，常与 Clash 有关）

`systeminfo` 里有 **Clash Wintun**，DNS 可能指向 `10.255.255.254`。

**处理：**

```bash
bash scripts/wsl-fix-dns.sh
```

然后在 **PowerShell（管理员）**：

```powershell
wsl --shutdown
```

重新打开 WSL，再：

```bash
source ~/.bashrc
cd /mnt/f/AI_Agent/Duliu
docker compose up --build
```

或在 Clash 中：**绕过 Docker / 关闭 TUN 对 WSL 的影响**，或为 `docker.io`、`auth.docker.io` 设直连。

### 4. Docker Desktop WSL 集成（可选，更省心）

Settings → Resources → **WSL integration** → 开启 Ubuntu  

开启后 WSL 内可能自带 `docker` 命令，可不依赖 `docker.exe` 别名。

## 验证

```bash
docker info
docker pull hello-world
cd /mnt/f/AI_Agent/Duliu && docker compose build
```
