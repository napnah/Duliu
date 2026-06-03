#!/bin/bash
set -e
python -m duliu.worker &
exec uvicorn duliu.api.main:app --host 0.0.0.0 --port 8000
