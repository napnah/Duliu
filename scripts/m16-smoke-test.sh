#!/usr/bin/env bash
# M16: IMPORT agent + polygon attempt-upload + session tools
set -euo pipefail
BASE="${DULIU_BASE:-http://127.0.0.1:8000}"

curl -sf "$BASE/api/health" | grep -q M16
echo "health M16 OK"

curl -sf "$BASE/api/agents/stages" | grep -q import_agent
echo "agents OK"

PID=$(curl -sf "$BASE/api/tree" | python3 -c "
import json,sys
t=json.load(sys.stdin)
for p in t.get('problems',[]):
    if p.get('originality')=='NON_ORIGINAL' and p.get('current_stage')=='IMPORT':
        print(p['id']); break
else:
    for p in t.get('problems',[]):
        if p.get('originality')=='NON_ORIGINAL':
            print(p['id']); break
")
[ -n "$PID" ] || { echo "no NON_ORIGINAL problem"; exit 1; }

STAGE=$(curl -sf "$BASE/api/problems/$PID" | python3 -c "import json,sys;print(json.load(sys.stdin)['current_stage'])")

if [ "$STAGE" = "IMPORT" ]; then
  curl -sf -X POST "$BASE/api/problems/$PID/dispatch" \
    -H 'Content-Type: application/json' \
    -d '{"stage_id":"IMPORT","reason":"m16-smoke"}' | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d.get('dispatch') or {}
rep=r.get('report') or {}
assert rep.get('checklist') or rep.get('ok') is not None, rep
print('dispatch IMPORT OK', rep.get('mode'))
"
else
  echo "skip IMPORT dispatch (stage=$STAGE)"
fi

curl -sf -X POST "$BASE/api/problems/$PID/polygon/attempt-upload" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('attempt'), d
print('polygon attempt OK', d['attempt'].get('mode'))
"

echo "M16 smoke passed"
