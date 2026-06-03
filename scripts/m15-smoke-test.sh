#!/usr/bin/env bash
# M15: STRESS agent + session tools API
set -euo pipefail
BASE="${DULIU_BASE:-http://127.0.0.1:8000}"

curl -sf "$BASE/api/health" | grep -q M15
echo "health M15 OK"

curl -sf "$BASE/api/agents/stages" | grep -q stress_agent
curl -sf "$BASE/api/session/tools" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'dispatch_stage' in d['tools'], d
print('session tools OK')
"

PID=$(curl -sf "$BASE/api/tree" | python3 -c "
import json,sys
t=json.load(sys.stdin)
for p in t.get('problems',[]):
    if p.get('current_stage')=='STRESS':
        print(p['id']); break
else:
    for p in t.get('problems',[]):
        if 'Adv Ready' in p.get('title',''):
            print(p['id']); break
")
[ -n "$PID" ] || exit 1

STAGE=$(curl -sf "$BASE/api/problems/$PID" | python3 -c "import json,sys;print(json.load(sys.stdin)['current_stage'])")

if [ "$STAGE" = "STRESS" ]; then
  curl -sf -X POST "$BASE/api/problems/$PID/dispatch" \
    -H 'Content-Type: application/json' \
    -d '{"stage_id":"STRESS","reason":"m15-smoke"}' | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d.get('dispatch') or {}
rep=r.get('report') or {}
assert rep.get('ok') or rep.get('job_id'), rep
print('dispatch STRESS OK', rep.get('summary','')[:60])
"
else
  curl -sf -X POST "$BASE/api/problems/$PID/stress/run" -H 'Content-Type: application/json' -d '{"mode":"quick"}' | python3 -c "
import json,sys; print('stress job', json.load(sys.stdin)['id'])
"
  echo "dispatch STRESS skipped (stage=$STAGE), stress/run OK"
fi

echo "M15 smoke passed"
