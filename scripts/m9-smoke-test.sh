#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://localhost:8000}"
echo "==> M9 smoke @ $BASE"
curl -sf "$BASE/api/health" | grep -q M9
curl -sf "$BASE/api/runner/sandbox-status" | python3 -c "
import sys,json
d=json.load(sys.stdin)
assert d['mode'] in ('subprocess','isolate'), d
"
echo "sandbox status OK"
echo "==> M9 smoke passed"
