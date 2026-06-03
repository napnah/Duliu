#!/usr/bin/env bash
# Duliu — 在 WSL 中配置 Docker（配合 Windows Docker Desktop）
set -euo pipefail

DOCKER_BIN="/mnt/c/Program Files/Docker/Docker/resources/bin"
MARKER="# >>> duliu docker (Docker Desktop WSL) >>>"
BLOCK="$MARKER
export PATH=\"$DOCKER_BIN:\$PATH\"
alias docker='docker.exe'
alias docker-compose='docker-compose.exe'
# <<< duliu docker <<<
"

echo "==> Duliu WSL Docker 配置"

if [[ ! -f "$DOCKER_BIN/docker.exe" ]]; then
  echo "错误: 未找到 Docker Desktop，请先安装:"
  echo "  https://docs.docker.com/desktop/setup/install/windows-install/"
  exit 1
fi

# 写入 ~/.bashrc（避免重复）
if ! grep -q "duliu docker" ~/.bashrc 2>/dev/null; then
  echo "" >> ~/.bashrc
  echo "$BLOCK" >> ~/.bashrc
  echo "已写入 ~/.bashrc"
else
  echo "~/.bashrc 已包含 Duliu Docker 配置，跳过"
fi

export PATH="$DOCKER_BIN:$PATH"
alias docker='docker.exe' 2>/dev/null || true
alias docker-compose='docker-compose.exe' 2>/dev/null || true

echo ""
echo "等待 Docker Desktop 引擎就绪（最多 90 秒）..."
for i in $(seq 1 45); do
  if docker.exe info >/dev/null 2>&1; then
    echo "Docker 引擎已就绪。"
    docker.exe version --format 'Client: {{.Client.Version}}'
    break
  fi
  sleep 2
  printf "."
done

if ! docker.exe info >/dev/null 2>&1; then
  echo ""
  echo "警告: Docker 引擎仍未响应。请在 Windows 中:"
  echo "  1. 打开 Docker Desktop，等待托盘图标稳定（Running）"
  echo "  2. Settings → General → Use the WSL 2 based engine"
  echo "  3. Settings → Resources → WSL integration → 开启当前 Ubuntu"
  echo "  4. 重新打开 WSL 终端，执行: source ~/.bashrc && docker info"
  exit 1
fi

echo ""
echo "配置完成。请执行:"
echo "  source ~/.bashrc"
echo "  cd ~/Duliu   # 或 cd /mnt/f/AI_Agent/Duliu"
echo "  docker compose up --build"
