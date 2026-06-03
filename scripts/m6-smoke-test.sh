#!/usr/bin/env bash
# M6 冒烟：NON_ORIGINAL IMPORT + import_check + submission gate
set -euo pipefail
BASE="${1:-http://localhost:8000}"
export DULIU_API="$BASE"

echo "==> M6 smoke @ $BASE"
curl -sf "$BASE/api/health" | grep -qE 'M6|M9'
echo "health OK"

TREE=$(curl -sf "$BASE/api/tree")
PID=$(echo "$TREE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for p in d['problems']:
    if p['title'] == 'M6 NON_ORIGINAL Demo':
        print(p['id'])
        break
else:
    raise SystemExit('M6 demo not found')
")
echo "demo problem $PID"

GRAPH=$(curl -sf "$BASE/api/problems/$PID/pipeline-graph")
echo "$GRAPH" | python3 -c "
import sys, json
g = json.load(sys.stdin)
assert g['originality'] == 'NON_ORIGINAL'
assert g['nodes'][0]['stage_id'] == 'IMPORT', g
"
echo "pipeline graph OK"

JOB=$(curl -sf -X POST "$BASE/api/problems/$PID/import/check")
JID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
for _ in $(seq 1 90); do
  R=$(curl -sf "$BASE/api/jobs/$JID")
  ST=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  if [ "$ST" = "done" ] || [ "$ST" = "failed" ]; then break; fi
  sleep 1
done
echo "$R" | python3 -c "
import sys, json
j = json.load(sys.stdin)
assert j['status'] == 'done' and j['result_json'].get('ok'), j
"
echo "import_check OK"

curl -sf -X POST "$BASE/api/problems/$PID/import/confirm-submission" \
  -H "Content-Type: application/json" \
  -d '{"submission_url":"https://codeforces.com/"}' > /dev/null
echo "submission confirm OK"

curl -sf -X POST "$BASE/api/problems/$PID/stages/IMPORT/approve" \
  -H "Content-Type: application/json" \
  -d '{"note":"m6-smoke"}' | python3 -c "
import sys, json
p = json.load(sys.stdin)
assert p['current_stage'] == 'SPEC', p
"
echo "IMPORT gate OK"

cli() {
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'duliu-duliu-1'; then
    docker exec -e DULIU_API="$BASE" duliu-duliu-1 python -m duliu.cli "$@"
  else
    PYTHONPATH="$(cd "$(dirname "$0")/.." && pwd)/packages" python3 -m duliu.cli "$@"
  fi
}
cli health | grep -qE 'M6|M9'
echo "CLI OK"

echo "==> M6 smoke passed"
