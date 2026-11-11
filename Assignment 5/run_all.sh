#!/usr/bin/env bash
# Runs every Section-10 codelab in order and saves each lab's console output next to it.
# Usage:  ./run_all.sh            (all labs, ~15-20 min on a laptop CPU)
#         ./run_all.sh 10.05      (one lab)
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
for script in labs/10.*/*.py; do
  lab=$(basename "$(dirname "$script")")
  if [[ $# -gt 0 && "$lab" != "$1"* ]]; then continue; fi
  echo ">>> $lab  ($script)"
  start=$(date +%s)
  python3 "$script" | tee "$(dirname "$script")/output.txt"
  echo ">>> $lab finished in $(( $(date +%s) - start ))s"
done
