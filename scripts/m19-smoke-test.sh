#!/usr/bin/env bash
# M19: Polygon API + STRESS LLM preflight
set -euo pipefail
BASE="${DULIU_BASE:-http://127.0.0.1:8000}"

curl -sf "$BASE/api/health" | grep -q M19
echo "health M19 OK"

curl -sf "$BASE/api/health" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('polygon_api') and d.get('stress_llm') is not None, d
print('flags OK')
"

curl -sf "$BASE/api/agents/stages" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('polygon_api') and d.get('stress_llm_agent') is not None, d
print('agents OK')
"

curl -sf "$BASE/api/session/tools" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for t in ('polygon_api_sync','polygon_api_build_package','stress_preflight'):
    assert t in d['tools'], d
print('session tools OK', len(d['tools']))
"

curl -sf "$BASE/api/polygon/api/status" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'methods' in d and 'problem.buildPackage' in d['methods'], d
print('polygon api status OK', d.get('api_configured'))
"

PID=$(curl -sf "$BASE/api/tree" | python3 -c "
import json,sys
t=json.load(sys.stdin)
print(t['problems'][0]['id'] if t.get('problems') else '')
")
if [ -n "$PID" ]; then
  curl -sf "$BASE/api/problems/$PID/polygon/api/status" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'api_configured' in d, d
print('problem polygon api OK')
"
  curl -sf -X POST "$BASE/api/problems/$PID/polygon/api/build-package" \
    -H 'Content-Type: application/json' \
    -d '{"full":false,"verify":true}' | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('reason') or d.get('ok') is not None, d
print('build-package OK', d.get('reason') or 'ok')
"
  STAGE=$(curl -sf "$BASE/api/problems/$PID" | python3 -c "import json,sys;print(json.load(sys.stdin)['current_stage'])")
  if [ "$STAGE" = "STRESS" ]; then
    curl -sf -X POST "$BASE/api/problems/$PID/dispatch" \
      -H 'Content-Type: application/json' \
      -d '{"stage_id":"STRESS","reason":"m19-smoke"}' | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d.get('dispatch') or {}
rep=r.get('report') or {}
assert rep.get('preflight') or rep.get('job_id'), rep
print('STRESS dispatch OK', (rep.get('summary') or '')[:50])
"
  else
    echo "skip STRESS dispatch (stage=$STAGE)"
  fi
fi

echo "M19 smoke passed"
