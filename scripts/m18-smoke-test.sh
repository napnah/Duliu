#!/usr/bin/env bash
# M18: polygon form auto-upload + langgraph history + session tools
set -euo pipefail
BASE="${DULIU_BASE:-http://127.0.0.1:8000}"

curl -sf "$BASE/api/health" | grep -q M18
echo "health M18 OK"

curl -sf "$BASE/api/health" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('polygon_form_upload'), d
print('polygon_form_upload OK')
"

curl -sf "$BASE/api/session/tools" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for t in ('prepare_polygon_upload','langgraph_history'):
    assert t in d['tools'], d
print('session tools OK', len(d['tools']))
"

PID=$(curl -sf "$BASE/api/tree" | python3 -c "
import json,sys
t=json.load(sys.stdin)
for p in t.get('problems',[]):
    if p.get('current_stage')=='PACKAGE':
        print(p['id']); break
else:
    print(t['problems'][0]['id'] if t.get('problems') else '')
")
if [ -n "$PID" ]; then
  curl -sf -X POST "$BASE/api/problems/$PID/polygon/auto-upload" | python3 -c "
import json,sys
d=json.load(sys.stdin)
f=d.get('form_upload') or {}
assert f.get('mode')=='form_upload', f
print('auto-upload OK', f.get('reason') or f.get('ok'))
"
  curl -sf "$BASE/api/problems/$PID/langgraph/history" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'history' in d, d
print('problem lg history OK', len(d['history']))
"
else
  echo "skip problem endpoints (no problem)"
fi

CS=$(curl -sf "$BASE/api/tree" | python3 -c "
import json,sys
t=json.load(sys.stdin)
cs=t.get('contest_sets') or []
print(cs[0]['id'] if cs else '')
")
if [ -n "$CS" ]; then
  curl -sf "$BASE/api/contest-sets/$CS/langgraph/history" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'history' in d, d
print('contest lg history OK', len(d['history']))
"
fi

echo "M18 smoke passed"
