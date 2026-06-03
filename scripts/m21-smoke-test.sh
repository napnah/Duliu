#!/usr/bin/env bash
# M21: polygon zip import + counterexamples API
set -euo pipefail
BASE="${DULIU_BASE:-http://127.0.0.1:8000}"

curl -sf "$BASE/api/health" | grep -q M21
echo "health M21 OK"

curl -sf "$BASE/api/health" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('polygon_import') and d.get('stress_counterexample_archive'), d
print('flags OK')
"

curl -sf "$BASE/api/session/tools" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for t in ('import_polygon_package','list_counterexamples'):
    assert t in d['tools'], d
print('session tools OK', len(d['tools']))
"

PID=$(curl -sf "$BASE/api/tree" | python3 -c "
import json,sys
t=json.load(sys.stdin)
print(t['problems'][0]['id'] if t.get('problems') else '')
")
if [ -n "$PID" ]; then
  curl -sf -X POST "$BASE/api/problems/$PID/polygon/import-package" \
    -H 'Content-Type: application/json' \
    -d '{}' | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('reason') or d.get('ok') is not None, d
print('import OK', d.get('reason') or d.get('imported_count'))
"
  curl -sf "$BASE/api/problems/$PID/counterexamples" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'items' in d, d
print('counterexamples OK', len(d['items']))
"
fi

echo "M21 smoke passed"
