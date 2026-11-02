#!/usr/bin/env bash
# Runs every step. With OPENROUTER_API_KEY set it uses the real model;
# otherwise it replays demo_scripts/*.json (tools still really execute).
set -e
cd "$(dirname "$0")"
mock() { if [ -z "$OPENROUTER_API_KEY" ]; then export HARNESS_MOCK="$PWD/demo_scripts/$1.json"; fi; }
fresh() { rm -rf workspace && cp -r workspace_template workspace; }

echo "===== STEP 1: chat with memory ====="
mock step01; python step01_chat.py "What is an agent harness in one sentence?" "What did I just ask you?"
echo; echo "===== STEP 2: one tool ====="
mock step02; python step02_one_tool.py "How many python files are in this folder?"
echo; echo "===== STEP 3: the agent loop ====="
fresh; mock step03; (cd workspace && python ../step03_agent_loop.py "Read notes.txt and tell me the 3rd line")
echo; echo "===== STEP 4: tool registry + file editing ====="
fresh; mock step04; (cd workspace && python ../step04_tool_registry.py "Add a multiply(a, b) function to calc.py")
echo; echo "===== STEP 5: sandbox, permissions, budgets ====="
fresh; python -c "import py_compile; py_compile.compile('workspace/calc.py', cfile='workspace/calc.pyc')"
mock step05; (cd workspace && python ../step05_safety_budget.py "Clean up the workspace" < /dev/null)
echo; echo "===== STEP 6: full harness (AGENTS.md, compaction, verifier, session log) ====="
fresh; mock step06; (cd workspace && python ../step06_harness.py --compact-at 2500 --verify "python test_calc.py" "Make the tests in test_calc.py pass")
echo; echo "--- session log (first 4 events) ---"; head -n 4 workspace/runs/*.jsonl | cut -c1-150
