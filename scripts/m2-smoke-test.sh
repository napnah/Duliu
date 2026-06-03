#!/usr/bin/env bash
# M2 冒烟测试（API 已启动时）
set -euo pipefail
BASE="${1:-http://localhost:8000}"

echo "==> M2 smoke @ $BASE"
curl -sf "$BASE/api/health" | grep -qE 'M2|M3'
echo "health OK"

TREE=$(curl -sf "$BASE/api/tree")
echo "$TREE" | grep -q "M2 Demo OI"
echo "$TREE" | grep -q "M2 Demo SPJ"
echo "demo seeds OK"

PID=$(echo "$TREE" | python3 -c "import sys,json; d=json.load(sys.stdin); print([p['id'] for p in d['problems'] if p['title']=='M1 Demo A+B'][0])")
OID=$(echo "$TREE" | python3 -c "import sys,json; d=json.load(sys.stdin); print([p['id'] for p in d['problems'] if 'OI' in p['title']][0])")
AID=$(echo "$TREE" | python3 -c "import sys,json; d=json.load(sys.stdin); print([p['id'] for p in d['problems'] if p['title']=='M2 Adv Ready'][0])")

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
  echo "job timeout $jid" >&2
  return 1
}

JOB=$(curl -sf -X POST "$BASE/api/problems/$PID/run" -H "Content-Type: application/json" \
  -d '{"program":"std","input":"3 4\n","expected_out":"7\n"}')
JID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
R=$(poll_job "$JID")
echo "$R" | python3 -c "import sys,json; r=json.load(sys.stdin).get('result_json') or {}; assert r.get('verdict')=='AC', r"
echo "expected AC OK"

JOB=$(curl -sf -X POST "$BASE/api/problems/$OID/run" -H "Content-Type: application/json" \
  -d '{"program":"std","input":"3 4\n","language":"python"}')
JID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
R=$(poll_job "$JID")
echo "$R" | python3 -c "import sys,json; r=json.load(sys.stdin).get('result_json') or {}; assert r.get('stdout','').strip()=='7', r"
echo "python run OK"

DISPATCH=$(curl -sf -X POST "$BASE/api/problems/$AID/dispatch" -H "Content-Type: application/json" \
  -d '{"stage_id":"ADVERSARIAL_REVIEW","reason":"smoke"}')
echo "$DISPATCH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['dispatch']['report']['ok'], d"
echo "adversarial dispatch OK"

SESS=$(curl -sf -X POST "$BASE/api/sessions" -H "Content-Type: application/json" \
  -d "{\"problem_id\":\"$PID\",\"title\":\"smoke\"}")
SID=$(echo "$SESS" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
CHAT=$(curl -sf -X POST "$BASE/api/sessions/$SID/chat" -H "Content-Type: application/json" \
  -d "{\"message\":\"状态\",\"problem_id\":\"$PID\"}")
echo "$CHAT" | python3 -c "import sys,json; assert '当前阶段' in json.load(sys.stdin)['assistant']['content']"
echo "session chat OK"

echo "==> M2 smoke passed"
