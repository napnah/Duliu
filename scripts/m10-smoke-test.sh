#!/usr/bin/env bash
# M10: Postgres checkpointer, SSE stream, langgraph history, fetch-std API
set -euo pipefail
BASE="${DULIU_BASE:-http://127.0.0.1:8000}"

curl -sf "$BASE/api/health" | grep -q M10
echo "health M10 OK"

curl -sf "$BASE/api/health" | grep -q langgraph_checkpoint
echo "checkpointer field OK"

sse_line=$(timeout 3 curl -sfN "$BASE/api/monitor/events/stream" 2>/dev/null | head -n 1 || true)
echo "$sse_line" | grep -q connected
echo "SSE stream OK"

PID=$(curl -sf "$BASE/api/tree" | python3 -c "
import json,sys
t=json.load(sys.stdin)
for p in t.get('problems',[]):
    if p.get('originality')=='NON_ORIGINAL':
        print(p['id']); break
" 2>/dev/null || true)
if [ -n "${PID:-}" ]; then
  curl -sf "$BASE/api/problems/$PID/langgraph/status" | grep -q checkpointer
  curl -sf "$BASE/api/problems/$PID/langgraph/history" | grep -q history
  echo "langgraph history OK ($PID)"
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/problems/$PID/import/fetch-std" -H 'Content-Type: application/json' -d '{}')
  if [ "$code" = "400" ] || [ "$code" = "200" ]; then
    echo "fetch-std endpoint OK (http $code)"
  else
    echo "fetch-std unexpected http $code" >&2
    exit 1
  fi
else
  echo "skip problem-specific checks (no NON_ORIGINAL in tree)"
fi

echo "M10 smoke passed"
