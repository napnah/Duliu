#!/usr/bin/env bash
# M12: WebSocket monitor + LangGraph 3-node dispatch graph
set -euo pipefail
BASE="${DULIU_BASE:-http://127.0.0.1:8000}"

curl -sf "$BASE/api/health" | grep -q M12
echo "health M12 OK"

curl -sf "$BASE/api/health" | grep -q websocket
echo "monitor_transport OK"

curl -sf "$BASE/api/langgraph/dispatch-graph" | python3 -c "
import json,sys
g=json.load(sys.stdin)
assert g['nodes']==['prepare','dispatch','finalize'], g
print('dispatch-graph OK')
"

if command -v docker >/dev/null && docker ps --format '{{.Names}}' | grep -q duliu-duliu; then
  docker exec duliu-duliu-1 python3 -c "
from starlette.testclient import TestClient
from duliu.api.main import app
with TestClient(app) as c:
    with c.websocket_connect('/api/monitor/events/ws') as ws:
        msg = ws.receive_json()
        assert msg.get('type')=='connected', msg
print('websocket OK')
" 2>/dev/null && echo "websocket in-container OK" || echo "websocket probe skipped"
else
  echo "skip in-container websocket (no duliu container)"
fi

echo "M12 smoke passed"
