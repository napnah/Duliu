#!/bin/sh
# 容器启动时补齐 C++/Python 运行依赖（镜像未正确构建或 apt 失败时）
set -e
need=0
command -v g++ >/dev/null 2>&1 || need=1
command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 || need=1

if [ "$need" -eq 0 ]; then
  echo "[duliu] Runner deps OK: g++=$(command -v g++) python=$(command -v python3 || command -v python)"
  exit 0
fi

if [ "${DULIU_SKIP_RUNNER_DEPS_INSTALL:-}" = "1" ]; then
  echo "[duliu] WARN: runner deps missing and DULIU_SKIP_RUNNER_DEPS_INSTALL=1" >&2
  exit 0
fi

echo "[duliu] Installing runner deps (g++, python3)..." >&2
export DEBIAN_FRONTEND=noninteractive
for mirror in "" "deb.debian.org" "mirrors.aliyun.com"; do
  if [ -n "$mirror" ]; then
    for f in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do
      [ -f "$f" ] && sed -i "s|deb.debian.org|${mirror}|g; s|mirrors.aliyun.com|${mirror}|g" "$f" 2>/dev/null || true
    done
  fi
  if apt-get update -qq && apt-get install -y -qq --no-install-recommends g++ python3; then
    echo "[duliu] Runner deps installed." >&2
    exit 0
  fi
  echo "[duliu] apt attempt failed, retry..." >&2
  sleep 3
done
echo "[duliu] ERROR: could not install g++/python3" >&2
exit 1
