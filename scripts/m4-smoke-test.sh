#!/usr/bin/env bash
# M4 冒烟测试（API 已启动时）
set -euo pipefail
BASE="${1:-http://localhost:8000}"

echo "==> M4 smoke @ $BASE"
curl -sf "$BASE/api/health" | grep -q M4
echo "health OK"

TREE=$(curl -sf "$BASE/api/tree")
echo "$TREE" | grep -q "M4 Demo ICPC Mini"
echo "M4 demo seed OK"

CSID=$(echo "$TREE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for c in d['contest_sets']:
    if 'M4 Demo' in c['name']:
        print(c['id'])
        break
")

DETAIL=$(curl -sf "$BASE/api/contest-sets/$CSID")
echo "$DETAIL" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['slot_count'] == 4, d
assert len(d['slots']) == 4, d
filled = [s for s in d['slots'] if s.get('problem_id')]
assert len(filled) >= 2, d
"
echo "contest detail OK"

EVAL=$(curl -sf -X POST "$BASE/api/contest-sets/$CSID/evaluate")
echo "$EVAL" | python3 -c "
import sys, json
r = json.load(sys.stdin)
assert 'chart' in r and r['chart'].get('ratings'), r
assert r['filled_slots'] >= 2, r
print('evaluate:', r['summary'])
"
echo "set evaluate OK"

curl -sf -X POST "$BASE/api/contest-sets/$CSID/approve-eval" \
  -H "Content-Type: application/json" \
  -d '{"note":"m4-smoke"}' | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'SET_EVAL_APPROVED', d
"
echo "approve eval OK"

SID=$(curl -sf -X POST "$BASE/api/sessions" -H "Content-Type: application/json" \
  -d '{"title":"M4 smoke session"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
CHAT=$(curl -sf -X POST "$BASE/api/sessions/$SID/chat" -H "Content-Type: application/json" \
  -d "{\"message\":\"套题状态\",\"contest_set_id\":\"$CSID\"}")
echo "$CHAT" | grep -q "M4 Demo"
echo "session contest status OK"

echo "==> M4 smoke passed"
