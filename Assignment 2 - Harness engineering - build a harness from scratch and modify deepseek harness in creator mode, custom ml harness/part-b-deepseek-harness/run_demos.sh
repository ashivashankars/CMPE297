#!/usr/bin/env bash
# Runs the two from-scratch plugins inside the REAL DeepSeek Harness (headless profile).
# Without a model key it uses scripted-model/ (pre-written model choices; DSH + plugins run for real).
# With a key: export DEEPSEEK_API_KEY=...  (or route OpenRouter, see README) and set USE_REAL_MODEL=1.
set -euo pipefail
cd "$(dirname "$0")"; HERE="$PWD"; DSH="${DSH:-dsh}"
for p in dsh-second-brain dsh-dataset-profiler; do $DSH plugin --profile headless add "$HERE/plugins/$p" >/dev/null; done

demo() {  # demo <script.json> <prompt>
  if [ -z "${USE_REAL_MODEL:-}" ]; then
    node scripted-model/scripted-model.mjs --port 8765 --script "demo/$1" 2>/tmp/scripted-model.log & MODEL=$!
    sleep 1; export DEEPSEEK_BASE_URL=http://127.0.0.1:8765/v1 DEEPSEEK_API_KEY=mock-key
  fi
  echo "\$ dsh --profile headless \"$2\""
  (cd demo && $DSH --profile headless "$2")
  [ -z "${USE_REAL_MODEL:-}" ] && { kill $MODEL; echo; echo "[what the harness offered the model]"; tail -1 /tmp/scripted-model.log; }
  echo
}

export DSH_BRAIN_DIR="$HERE/demo/brain"; rm -rf "$DSH_BRAIN_DIR"
echo "===== PLUGIN 1: dsh-second-brain ====="
demo second-brain.json "Remember what I learned about harnesses today, then tell me how the harness knows the loop is done."
echo "--- notes written to disk ---"; for f in "$DSH_BRAIN_DIR"/*.md; do echo "## $(basename "$f")"; cat "$f"; done
echo; echo "===== PLUGIN 2: dsh-dataset-profiler ====="
demo dataset-profiler.json "Profile churn.csv and tell me how to model churn safely."
