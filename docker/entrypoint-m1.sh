#!/bin/bash
set -e
if [ -x /install-runner-deps.sh ]; then
  /install-runner-deps.sh || true
fi
python -m duliu.worker &
exec uvicorn duliu.api.main:app --host 0.0.0.0 --port 8000
