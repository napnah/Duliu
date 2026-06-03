#!/usr/bin/env bash
# 在 WSL 中启动 Duliu（需已配置 docker）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1 && ! command -v docker.exe >/dev/null 2>&1; then
  echo "未找到 docker。先运行: bash scripts/wsl-setup-docker.sh"
  exit 1
fi

DOCKER="${DOCKER:-docker}"
if command -v docker.exe >/dev/null 2>&1; then
  DOCKER=docker.exe
fi

$DOCKER info >/dev/null 2>&1 || {
  echo "Docker 未运行。请在 Windows 启动 Docker Desktop。"
  exit 1
}

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.m1.yml}"
if [ ! -f "$ROOT/$COMPOSE_FILE" ]; then
  COMPOSE_FILE=docker-compose.yml
fi
echo "==> Duliu compose -f $COMPOSE_FILE up @ $ROOT"
$DOCKER compose -f "$COMPOSE_FILE" up --build "$@"
