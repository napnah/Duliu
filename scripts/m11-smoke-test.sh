#!/usr/bin/env bash
# M11: sandbox integration + env secret bootstrap + run job
set -euo pipefail
BASE="${DULIU_BASE:-http://127.0.0.1:8000}"

curl -sf "$BASE/api/health" | grep -q M11
echo "health M11 OK"

curl -sf "$BASE/api/runner/sandbox-status" | grep -q cpp_via_isolate
echo "sandbox-status OK"

PID=$(curl -sf "$BASE/api/tree" | python3 -c "
import json,sys
t=json.load(sys.stdin)
for p in t.get('problems',[]):
    if 'M1 Demo' in p.get('title','') or p.get('originality')=='ORIGINAL':
        print(p['id']); break
else:
    print(t['problems'][0]['id'] if t.get('problems') else '', end='')
")
[ -n "$PID" ] || { echo "no problem for run test" >&2; exit 1; }

JOB=$(curl -sf -X POST "$BASE/api/problems/$PID/run" \
  -H 'Content-Type: application/json' \
  -d '{"program":"std","input":"1 2\n","use_editor_draft":true,"draft":{"source":"a,b=map(int,input().split())\nprint(a+b)\n","language":"python"}}')
JID=$(echo "$JOB" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

for _ in $(seq 1 60); do
  st=$(curl -sf "$BASE/api/jobs/$JID" | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])")
  [ "$st" = "done" ] || [ "$st" = "failed" ] && break
  sleep 0.5
done
curl -sf "$BASE/api/jobs/$JID" | python3 -c "
import json,sys
j=json.load(sys.stdin)
assert j['status']=='done', j
r=j.get('result_json') or {}
assert r.get('verdict') in ('OK','AC'), r
print('run job OK', r.get('verdict'))
"

echo "M11 smoke passed"
