#!/usr/bin/env bash
# M1 冒烟测试（API 已启动时）
set -euo pipefail
BASE="${1:-http://localhost:8000}"

echo "==> M1 smoke @ $BASE"
curl -sf "$BASE/api/health" | grep -qE 'M1|M2'
echo "health OK"

TREE=$(curl -sf "$BASE/api/tree")
echo "$TREE" | grep -q "M1 Demo A+B"
echo "demo problem OK"

PID=$(echo "$TREE" | python3 -c "import sys,json; d=json.load(sys.stdin); print([p['id'] for p in d['problems'] if 'Demo' in p['title']][0])")

JOB=$(curl -sf -X POST "$BASE/api/problems/$PID/run" \
  -H "Content-Type: application/json" \
  -d '{"program":"std","input":"3 4\n"}')
JID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

for _ in $(seq 1 60); do
  R=$(curl -sf "$BASE/api/jobs/$JID")
  ST=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  if [ "$ST" = "done" ] || [ "$ST" = "failed" ]; then
    echo "$R" | python3 -c "import sys,json; r=json.load(sys.stdin).get('result_json') or {}; assert r.get('stdout','').strip()=='7', r; print('run_single OK', r.get('verdict'))"
    break
  fi
  sleep 1
done

echo "==> M1 smoke passed"
