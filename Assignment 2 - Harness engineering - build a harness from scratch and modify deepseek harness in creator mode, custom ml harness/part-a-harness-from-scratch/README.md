# Part A · A coding-agent harness from scratch (OpenRouter)

🎬 **Video:** [../videos/part-a-harness-from-scratch.mp4](../videos/part-a-harness-from-scratch.mp4) (6m 26s: code walkthrough of every file + execution)

Built progressively, one idea per file, Python standard library only. Inspired by
[dlmastery/simple-coding-harness](https://github.com/dlmastery/simple-coding-harness),
[avbiswas/neural-code](https://github.com/avbiswas/neural-code) and
[SWE-agent/mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent); the code here is written independently.

| File | Adds | Key idea |
|---|---|---|
| `llm.py` | the model client | OpenRouter `/chat/completions` over plain `urllib`; `HARNESS_MOCK` replays scripted replies for offline demos |
| `step01_chat.py` | memory | the model is stateless; the harness resends the whole history |
| `step02_one_tool.py` | one tool (`bash`) | a tool = JSON schema for the model + a function the harness runs |
| `step03_agent_loop.py` | **the loop** | keep calling tools until the model answers in plain text |
| `tools.py` | tool registry | `@tool` builds the JSON schema from type hints; `read/write/edit_file`, `list_dir`, `bash` |
| `step04_tool_registry.py` | coding agent | registry + exact-match `edit_file` (read before edit) |
| `step05_safety_budget.py` | guardrails | workspace sandbox, permission gate for risky shell, output truncation, step/token/$ budgets |
| `step06_harness.py` | full harness | `AGENTS.md` rules, context compaction, **verifier loop** (act → verify → repair), JSONL session log |
| `workspace_template/` | practice repo | `calc.py` with two bugs, `test_calc.py`, `AGENTS.md` |
| `demo_scripts/*.json` | offline model | the scripted model choices used for the recording |

## Run

```bash
# live model (any OpenRouter model; attach your Gemini key on OpenRouter to bill your student plan)
export OPENROUTER_API_KEY=sk-or-...
export HARNESS_MODEL=google/gemini-2.5-flash      # optional
./run_demos.sh

# or individual steps
python step01_chat.py                              # interactive REPL
cp -r workspace_template workspace && cd workspace
python ../step06_harness.py --verify "python test_calc.py" "Make the tests in test_calc.py pass"
```

With no `OPENROUTER_API_KEY`, `run_demos.sh` sets `HARNESS_MOCK` and replays `demo_scripts/`; the tools still really run.

## What the step-6 run shows

```
  [4] edit_file{... subtract ... a - b}
  [harness] verify `python test_calc.py` -> FAIL        <- model said "done" too early
  [harness] compacted 4 old messages (2844 chars)
  [6] edit_file{... if b == 0: raise ValueError ...}    <- repair, following AGENTS.md
  [harness] verify `python test_calc.py` -> PASS
bot > Fixed both bugs ... all 4 tests passed. (verified by harness)
```
