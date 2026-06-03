#!/usr/bin/env bash
# M13: Python/Java isolate flags + polygon prepare-upload
set -euo pipefail
BASE="${DULIU_BASE:-http://127.0.0.1:8000}"

curl -sf "$BASE/api/health" | grep -q M13
echo "health M13 OK"

curl -sf "$BASE/api/runner/sandbox-status" | grep -q python_java_via_isolate
echo "sandbox-status OK"

PID=$(curl -sf "$BASE/api/tree" | python3 -c "
import json,sys
t=json.load(sys.stdin)
for p in t.get('problems',[]):
    if 'Package Ready' in p.get('title','') or p.get('current_stage')=='PACKAGE':
        print(p['id']); break
else:
    print(t['problems'][0]['id'] if t.get('problems') else '', end='')
")
[ -n "$PID" ] || { echo "no problem" >&2; exit 1; }

OUT=$(curl -sf -X POST "$BASE/api/problems/$PID/polygon/prepare-upload")
echo "$OUT" | python3 -c "
import json,sys
d=json.load(sys.stdin)
u=d.get('upload') or {}
assert u.get('zip_path'), u
assert u.get('polygon_url'), u
print('prepare-upload OK', u.get('zip_path'))
"

curl -sf "$BASE/api/problems/$PID/polygon/upload-status" | grep -q zip_path
echo "upload-status OK"

echo "M13 smoke passed"
