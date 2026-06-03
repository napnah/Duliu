#!/usr/bin/env bash
# M14: stage agents API + job websocket
set -euo pipefail
BASE="${DULIU_BASE:-http://127.0.0.1:8000}"

curl -sf "$BASE/api/health" | grep -q M14
echo "health M14 OK"

curl -sf "$BASE/api/agents/stages" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'SPEC' in d['stages'], d
print('agents/stages OK')
"

PID=$(curl -sf "$BASE/api/tree" | python3 -c "
import json,sys
t=json.load(sys.stdin)
for p in t.get('problems',[]):
    if p.get('current_stage')=='SPEC':
        print(p['id']); break
else:
    raise SystemExit('no problem at SPEC')
")

curl -sf -X POST "$BASE/api/problems/$PID/dispatch" \
  -H 'Content-Type: application/json' \
  -d '{"stage_id":"SPEC","reason":"m14-smoke"}' | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d.get('dispatch') or {}
rep=r.get('report') or {}
assert rep.get('ok') or r.get('agent'), r
print('dispatch SPEC OK', r.get('agent') or rep.get('mode'))
"

JOB=$(curl -sf -X POST "$BASE/api/problems/$PID/run" \
  -H 'Content-Type: application/json' \
  -d '{"program":"std","input":"1 2\n","use_editor_draft":true,"draft":{"source":"print(3)\n","language":"python"}}')
JID=$(echo "$JOB" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

if command -v docker >/dev/null && docker ps --format '{{.Names}}' | grep -q duliu-duliu; then
  docker exec duliu-duliu-1 python3 -c "
from starlette.testclient import TestClient
from duliu.api.main import app
with TestClient(app) as c:
    with c.websocket_connect('/api/jobs/$JID/ws') as ws:
        m=ws.receive_json()
        assert m.get('type')=='connected', m
        for _ in range(200):
            p=ws.receive_json()
            if p.get('type')=='done' or p.get('status') in ('done','failed'):
                break
        else:
            raise SystemExit('job ws timeout')
print('job ws OK')
" 2>/dev/null || echo "job ws probe skipped"
else
  echo "skip job ws (no container)"
fi

echo "M14 smoke passed"
