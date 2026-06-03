#!/usr/bin/env bash
# 修复 WSL 在 Clash/TUN 下无法拉取 Docker 镜像（DNS 超时）
set -euo pipefail

echo "==> 配置 WSL DNS（需 sudo）"

sudo tee /etc/wsl.conf >/dev/null <<'EOF'
[network]
generateResolvConf = false
EOF

sudo tee /etc/resolv.conf >/dev/null <<'EOF'
nameserver 223.5.5.5
nameserver 114.114.114.114
nameserver 8.8.8.8
EOF

sudo chattr +i /etc/resolv.conf 2>/dev/null || true

echo "已写入 /etc/wsl.conf 与 /etc/resolv.conf"
echo "请在 Windows PowerShell 执行: wsl --shutdown"
echo "然后重新打开 WSL，再运行: bash scripts/wsl-setup-docker.sh"
