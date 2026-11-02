#!/usr/bin/env bash
# End-to-end autoresearch demo.
#   real researcher : export OPENROUTER_API_KEY=sk-or-...  (optional HARNESS_MODEL=google/gemini-2.5-pro)
#   offline         : no key -> demo/researcher_mock.json replays 7 proposals (training + eval really run)
set -euo pipefail
cd "$(dirname "$0")/autoresearch"
[ -z "${OPENROUTER_API_KEY:-}" ] && export HARNESS_MOCK="$PWD/../demo/researcher_mock.json"

echo "\$ python prepare.py          # frozen data + time split"; python prepare.py
echo; echo "\$ python harness.py reset   # baseline + hash the frozen files"; python harness.py reset
echo; echo "\$ python harness.py run --iterations 7"; python harness.py run --iterations 7

echo; echo "===== anti-cheat check: tamper with the frozen evaluator ====="
cp evaluate.py /tmp/evaluate.bak
echo "# researcher sneaks in a change" >> evaluate.py
python harness.py step --hypothesis "edit the metric code" --edits '[{"old": "def build_model():", "new": "def build_model():  # tweak"}]' | head -2
cp /tmp/evaluate.bak evaluate.py; echo "(evaluate.py restored)"

echo; echo "\$ python harness.py finalize   # hidden test split, scored once"; python harness.py finalize
python plot.py
