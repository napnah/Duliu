#!/usr/bin/env bash
# M17: contest LangGraph + session evaluate_contest_set + tool panel APIs
set -euo pipefail
BASE="${DULIU_BASE:-http://127.0.0.1:8000}"

curl -sf "$BASE/api/health" | grep -q M17
echo "health M17 OK"

curl -sf "$BASE/api/session/tools" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'evaluate_contest_set' in d.get('tools',[]), d
print('session tools OK', len(d['tools']))
"

curl -sf "$BASE/api/contest-sets/langgraph/graph" | python3 -c "
import json,sys
d=json.load(sys.stdin)
nodes=d.get('nodes') or []
assert 'scan_slots' in nodes and 'evaluate' in nodes, d
print('contest graph OK', nodes)
"

CS=$(curl -sf "$BASE/api/tree" | python3 -c "
import json,sys
t=json.load(sys.stdin)
cs=t.get('contest_sets') or []
print(cs[0]['id'] if cs else '')
")
if [ -n "$CS" ]; then
  curl -sf "$BASE/api/contest-sets/$CS/langgraph/status" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'graph' in d and 'checkpointer' in d, d
print('langgraph status OK', d.get('thread_id'))
"
  curl -sf -X POST "$BASE/api/contest-sets/$CS/evaluate" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('summary') or d.get('ok') is not None, d
print('set evaluate OK', d.get('summary','')[:60])
"
else
  echo "skip contest evaluate (no contest set)"
fi

echo "M17 smoke passed"
