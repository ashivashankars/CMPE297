#!/usr/bin/env bash
# Run every test and every codelab in the terminal; save the output as execution evidence.
#   ./run_all.sh            -> docs/execution_logs/*.txt
set -u
cd "$(dirname "$0")"
OUT=docs/execution_logs
mkdir -p "$OUT"
export NO_COLOR=1 GENUI_DELAY=0
PY=${PYTHON:-python3}
parts=(01_a2ui 02_ag_ui 03_mcp_apps 04_json_render 05_openui 06_harness)

{
  echo "# Test run - $(date -u '+%Y-%m-%d %H:%M UTC') - $($PY -V) - node $(node -v 2>/dev/null)"
  for p in "${parts[@]}"; do
    echo; echo "## $p"
    (cd "$p" && $PY -m unittest discover -s tests -v 2>&1)
  done
  echo; echo "## browser modules (node --test)"
  node --test tests_js/frontend.test.mjs 2>&1 | grep -E "^(ok|not ok|# (pass|fail))"
} | tee "$OUT/00_tests.txt"

for p in "${parts[@]}"; do
  echo "== $p: all four modes + one click" | tee "$OUT/$p.txt"
  (cd "$p" && $PY cli.py --action 2>&1) >> "$OUT/$p.txt"
done
echo; echo "logs written to $OUT/"
