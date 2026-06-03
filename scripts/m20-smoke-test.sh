#!/usr/bin/env bash
# M20: polygon package download, package sync, stress interpretation
set -euo pipefail
BASE="${DULIU_BASE:-http://127.0.0.1:8000}"

curl -sf "$BASE/api/health" | grep -q M20
echo "health M20 OK"

curl -sf "$BASE/api/health" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('stress_interpret') and d.get('package_polygon_sync'), d
print('flags OK')
"

curl -sf "$BASE/api/polygon/api/status" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'problem.package' in d['methods'], d
print('polygon methods OK')
"

curl -sf "$BASE/api/session/tools" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for t in ('polygon_api_download_package','package_sync_polygon','stress_interpret'):
    assert t in d['tools'], d
print('session tools OK', len(d['tools']))
"

PID=$(curl -sf "$BASE/api/tree" | python3 -c "
import json,sys
t=json.load(sys.stdin)
print(t['problems'][0]['id'] if t.get('problems') else '')
")
if [ -n "$PID" ]; then
  curl -sf -X POST "$BASE/api/problems/$PID/polygon/api/download-package" \
    -H 'Content-Type: application/json' \
    -d '{"package_type":"standard"}' | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('reason') or d.get('ok') is not None, d
print('download OK', d.get('reason') or d.get('path',''))
"
  curl -sf -X POST "$BASE/api/problems/$PID/package/sync-polygon" \
    -H 'Content-Type: application/json' \
    -d '{}' | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('mode') or d.get('reason'), d
print('sync OK', d.get('mode'), d.get('reason',''))
"
  curl -sf "$BASE/api/problems/$PID/stress/interpretation" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'interpretation' in d, d
print('stress interpretation OK', d.get('reason') or 'ok')
"
fi

echo "M20 smoke passed"
