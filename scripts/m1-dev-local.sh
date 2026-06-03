#!/usr/bin/env bash
# M1 本地开发：仅 Postgres 用 Docker，API+Worker 在 WSL 本机（需 g++）
# 用法: bash scripts/m1-dev-local.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v g++ >/dev/null 2>&1; then
  echo "需要 g++: sudo apt-get update && sudo apt-get install -y g++"
  exit 1
fi

export PYTHONPATH="${ROOT}/packages"
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://duliu:duliu@127.0.0.1:5432/duliu}"
export DULIU_RUNNER_WORK_DIR="${DULIU_RUNNER_WORK_DIR:-/tmp/duliu-runner}"
export JOB_POLL_SECONDS="${JOB_POLL_SECONDS:-1}"
export CORS_ORIGINS="${CORS_ORIGINS:-*}"

echo "==> 启动 Postgres（Docker）"
docker compose -f docker-compose.m1.yml up -d postgres

echo "==> 等待 Postgres 就绪"
for _ in $(seq 1 40); do
  if docker compose -f docker-compose.m1.yml exec -T postgres pg_isready -U duliu >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "==> 安装 Python 依赖"
  pip3 install -q -r requirements.txt
fi

cleanup() {
  kill "$WORKER_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "==> Worker"
python3 -m duliu.worker &
WORKER_PID=$!

echo "==> API http://localhost:8000"
exec python3 -m uvicorn duliu.api.main:app --host 0.0.0.0 --port 8000
