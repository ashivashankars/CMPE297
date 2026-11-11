#!/usr/bin/env bash
# Start all six codelab servers (Ctrl+C stops them all).
#   A2UI http://127.0.0.1:8001   AG-UI :8002   MCP Apps :8003
#   json-render :8004            OpenUI :8005  Harness :8006
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
trap 'kill 0' EXIT
(cd 01_a2ui && $PY agent.py 8001) &
(cd 02_ag_ui && $PY agent.py 8002) &
(cd 03_mcp_apps && $PY host.py 8003) &
(cd 04_json_render && $PY agent.py 8004) &
(cd 05_openui && $PY agent.py 8005) &
(cd 06_harness && $PY agent.py 8006) &
wait
