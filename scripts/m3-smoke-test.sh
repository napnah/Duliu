#!/usr/bin/env bash
# M3 冒烟测试（API 已启动时）
set -euo pipefail
BASE="${1:-http://localhost:8000}"

echo "==> M3 smoke @ $BASE"
curl -sf "$BASE/api/health" | grep -q M3
echo "health OK"

TREE=$(curl -sf "$BASE/api/tree")
echo "$TREE" | grep -q "M3 Demo Interactive"
echo "$TREE" | grep -q "M3 Package Ready"
echo "demo seeds OK"

IID=$(echo "$TREE" | python3 -c "import sys,json; d=json.load(sys.stdin); print([p['id'] for p in d['problems'] if 'Interactive' in p['title']][0])")
PID=$(echo "$TREE" | python3 -c "import sys,json; d=json.load(sys.stdin); print([p['id'] for p in d['problems'] if p['title']=='M3 Package Ready'][0])")

poll_job() {
  local jid="$1"
  for _ in $(seq 1 60); do
    R=$(curl -sf "$BASE/api/jobs/$jid")
    ST=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
    if [ "$ST" = "done" ] || [ "$ST" = "failed" ]; then
      echo "$R"
      return 0
    fi
    sleep 1
  done
  return 1
}

JOB=$(curl -sf -X POST "$BASE/api/problems/$IID/run/interactive" -H "Content-Type: application/json" -d '{}')
JID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
R=$(poll_job "$JID")
echo "$R" | python3 -c "import sys,json; r=json.load(sys.stdin).get('result_json') or {}; assert r.get('verdict')=='AC', r"
echo "interactive AC OK"

ZIP=$(curl -sf -o /tmp/m3_poly.zip -w "%{http_code}" "$BASE/api/problems/$PID/polygon/export")
[ "$ZIP" = "200" ]
python3 -c "import zipfile; z=zipfile.ZipFile('/tmp/m3_poly.zip'); assert 'problem.xml' in z.namelist(); assert 'manifest.json' in z.namelist()"
echo "polygon zip OK"

DISPATCH=$(curl -sf -X POST "$BASE/api/problems/$PID/dispatch" -H "Content-Type: application/json" \
  -d '{"stage_id":"PACKAGE","reason":"smoke"}')
echo "$DISPATCH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'zip_path' in d['dispatch']['report'], d"
echo "package dispatch OK"

echo "==> M3 smoke passed"
