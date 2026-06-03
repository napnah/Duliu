#!/usr/bin/env bash
# M5 冒烟测试（API + Worker 已启动）
set -euo pipefail
BASE="${1:-http://localhost:8000}"
export DULIU_API="$BASE"
export PYTHONPATH="${PYTHONPATH:-}:$(cd "$(dirname "$0")/.." && pwd)/packages"

echo "==> M5 smoke @ $BASE"
curl -sf "$BASE/api/health" | grep -q M5
echo "health OK"

CFG=$(curl -sf -X PUT "$BASE/api/workspace/crawler-config" \
  -H "Content-Type: application/json" \
  -d '{"crawl_sites":["https://codeforces.com/problemset/problem/1/A"],"cf_cookie":null}')
echo "$CFG" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'codeforces.com' in str(d.get('whitelist_hosts', [])), d
"
echo "crawler config OK"

curl -sf -X POST "$BASE/api/crawl/import" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://evil.example.com/p"}' \
  && exit 1 || true
echo "crawl whitelist reject OK"

OUT=$(curl -sf -X POST "$BASE/api/crawl/import" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://codeforces.com/problemset/problem/1/A","title":"M5 Smoke CF1A"}')
PID=$(echo "$OUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['problem']['id'])")
JID=$(echo "$OUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['job']['id'])")
echo "$OUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['problem']['originality'] == 'NON_ORIGINAL', d
"
echo "crawl enqueue OK problem=$PID job=$JID"

poll_job() {
  local jid="$1"
  for _ in $(seq 1 90); do
    R=$(curl -sf "$BASE/api/jobs/$jid")
    ST=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
    if [ "$ST" = "done" ] || [ "$ST" = "failed" ]; then
      echo "$R"
      return 0
    fi
    sleep 1
  done
  return 1
}

R=$(poll_job "$JID") || { echo "crawl job poll timeout (network?)"; exit 1; }
echo "$R" | python3 -c "
import sys, json
j = json.load(sys.stdin)
if j['status'] == 'done':
    assert j.get('result_json', {}).get('ok'), j
    print('crawl import done OK')
elif j['status'] == 'failed' and '403' in str(j.get('result_json', {})):
    print('WARN: Codeforces 403 without cookie — enqueue/whitelist OK, skip live fetch')
else:
    raise AssertionError(j)
"

P=$(curl -sf "$BASE/api/problems/$PID")
echo "$P" | python3 -c "
import sys, json
p = json.load(sys.stdin)
assert p['originality'] == 'NON_ORIGINAL', p
assert p['spec_json'].get('import', {}).get('status') == 'imported', p
"
echo "problem import OK"

curl -sf "$BASE/api/monitor/events/export?problem_id=$PID&limit=5" | python3 -c "
import sys, json
json.load(sys.stdin)
"
echo "events export OK"

cli() {
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'duliu-duliu-1'; then
    docker exec -e DULIU_API="$BASE" duliu-duliu-1 python -m duliu.cli "$@"
  else
    PYTHONPATH="$(cd "$(dirname "$0")/.." && pwd)/packages" python3 -m duliu.cli "$@"
  fi
}
cli health | grep -q M5
cli tree | grep -q Workspace
echo "CLI OK"

echo "==> M5 smoke passed"
