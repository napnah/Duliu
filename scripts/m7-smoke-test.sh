#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://localhost:8000}"
echo "==> M7 smoke @ $BASE"
curl -sf "$BASE/api/health" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('langgraph') is True, d
print('langgraph enabled OK')
"
TREE=$(curl -sf "$BASE/api/tree")
PID=$(echo "$TREE" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for p in d['problems']:
    if p['title']=='M3 Package Ready':
        print(p['id']); break
")
STAGE=$(curl -sf "$BASE/api/problems/$PID" | python3 -c "import sys,json; print(json.load(sys.stdin)['current_stage'])")
OUT=$(curl -sf -X POST "$BASE/api/problems/$PID/dispatch" -H "Content-Type: application/json" \
  -d "{\"stage_id\":\"$STAGE\",\"reason\":\"m7-smoke\"}")
echo "$OUT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
disp=d['dispatch']
assert disp.get('langgraph') is True, disp
assert disp.get('report') or disp.get('hint'), disp
"
LG=$(curl -sf "$BASE/api/problems/$PID/langgraph/status")
echo "$LG" | python3 -c "import sys,json; assert json.load(sys.stdin).get('thread_id')"
echo "==> M7 smoke passed"
