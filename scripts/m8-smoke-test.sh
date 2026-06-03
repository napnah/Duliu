#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://localhost:8000}"
echo "==> M8 smoke @ $BASE"
TREE=$(curl -sf "$BASE/api/tree")
PID=$(echo "$TREE" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for p in d['problems']:
    if 'M1 Demo' in p['title']:
        print(p['id']); break
")
curl -sf -X PUT "$BASE/api/problems/$PID/artifacts/std" -H "Content-Type: application/json" \
  -d '{"content_text":"// v1\nint main(){return 0;}\n","language":"cpp","author":"smoke"}' > /dev/null
curl -sf -X PUT "$BASE/api/problems/$PID/artifacts/std" -H "Content-Type: application/json" \
  -d '{"content_text":"// v2\nint main(){return 0;}\n","language":"cpp","author":"smoke"}' > /dev/null
VERS=$(curl -sf "$BASE/api/problems/$PID/artifacts/std/versions")
echo "$VERS" | python3 -c "import sys,json; assert len(json.load(sys.stdin))>=2"
REST=$(curl -sf -X POST "$BASE/api/problems/$PID/artifacts/std/restore" \
  -H "Content-Type: application/json" -d '{"version":1}')
echo "$REST" | python3 -c "import sys,json; assert json.load(sys.stdin)['version']>=3"
echo "==> M8 smoke passed"
