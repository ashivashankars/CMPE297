# Video walkthrough

## 1. Included video: code + execution walkthrough (≈ 9 min)

**File:** [`video/Assignment3_ADK_walkthrough.mp4`](video/Assignment3_ADK_walkthrough.mp4) (1080p, narrated)

| Time | Section | What is shown |
|---|---|---|
| 0:00 | Intro | The five agents, setup (`pip install`, `.env`, `adk web`, `pytest`) |
| ~1:10 | (a) Lead generation | Architecture → `research_fanout.py` (dynamic ParallelAgent) → two-turn execution trace |
| ~2:50 | (b) Gemini CLI tool | Architecture → `run_gemini_cli` hardening → URL-injection, loop and budget tests + pipeline trace |
| ~4:20 | (c) MCP bug assistant | Architecture → `McpToolset` wiring (stdio, GitHub HTTP, Toolbox) → real MCP round-trip trace |
| ~5:40 | (d) Code review | Architecture → fix `LoopAgent` + validator → trace where the loop runs twice and escalates |
| ~7:00 | (e) E-commerce | Architecture → identity guard + `require_confirmation` → shopping journey with a spoofed email |
| ~8:20 | Tests & deploy | `pytest -v` (19 passed) → `adk deploy cloud_run` / `agent_engine` |

The execution segments come from **real runs** of each agent through ADK's `Runner`: real tools, both MCP servers as stdio subprocesses, SQLite transactions, the Gemini CLI subprocess path, parallel fan-out, loops, callbacks, session state and artifacts. Only the Gemini model is replaced by a scripted stand-in (`tests/fake_llm.py`), so the runs are reproducible and need no API key. The full traces are in [`transcripts/offline/`](transcripts/offline/). To regenerate them:

```bash
TRACE_DIR=transcripts/offline pytest -v
```

## 2. Recording a live version with real Gemini calls (recommended addition)

With a `GOOGLE_API_KEY` in `.env`, record the screen (OBS, Loom or QuickTime) while following this script. It takes about 12 minutes. Keep the **Events** tab of `adk web` visible so viewers can see each tool call and sub-agent hop.

**Before recording**

```bash
cd "Assignment 3" && source .venv/bin/activate
pytest -q                                   # show 19 passed
adk web                                     # open http://localhost:8000
```

### (a) `lead_generation_agent` (~3 min)
1. Open `agent.py`, then `sub_agents/research_fanout.py`, and explain why the fan-out is a custom `BaseAgent`.
2. Chat:
   - `I sell cloud cost-optimisation software. Find me leads among fintech companies in India.`
   - `Study 3 companies.` → in Events, expand `CompanyResearchFanout` to show 3 researchers running in parallel.
   - `Yes, find 5 leads.` → open the **Artifacts** tab and click `lead_report.md`.
3. Show the **State** tab: `stage` moves from `patterns_ready` to `leads_ready`.

### (b) `gemini_cli_agent` (~2 min)
1. Show `tools.py` (no `shell=True`, URL allow-list, budget), then the `RefinementLoop` in `agent.py`.
2. Chat: `Is the Gemini CLI tool working?`, then `Explain the architecture of https://github.com/google/adk-python and where tool calling is implemented.`
3. In Events, point out each `run_gemini_cli` call, the Critic's verdict, and `exit_loop`. Open `gemini_cli_report.md` in Artifacts.

### (c) `bug_assistant_agent` (~2 min)
1. Show `mcp_server/ticket_server.py` (FastMCP tools) and `McpToolset(StdioConnectionParams…)` in `tools.py`.
2. Optional: `npx @modelcontextprotocol/inspector python bug_assistant_agent/mcp_server/ticket_server.py` to show the same server in another MCP client.
3. Chat: `Our customers say they got charged twice for their bean subscription. Is there already a ticket?`, then `Create a ticket: the Espresso Pro steam wand keeps dripping water after brewing finishes.`, then `What tickets were created in the last 30 days?`

### (d) `code_review_assistant` (~2.5 min)
1. Show `sub_agents/review_pipeline.py` and `fix_pipeline.py`.
2. Paste the buggy code from `scripts/run_demo.py` (`BUGGY_CODE`) with `Please review this code:`.
3. In Events, show the TestRunner's executed code. Reply `Yes, please fix it.` and show the loop iterations and `exit_fix_loop`, then download `fixed_code.py` from Artifacts.

### (e) `ecommerce_agent` (~2.5 min)
1. Show `guards.py` (`enforce_identity`, audit log) and `require_confirmation` in `agent.py`.
2. Chat:
   - `I'm training for my first half marathon and need cushioned running shoes under $170.`
   - `Add the Clifton 10 in size 9, White to my list.`
   - `Show my shopping list and the stores near me.`
   - `Place the order at Palo Alto with Express Delivery.` → the **approve/reject dialog** appears. Approve it.
   - `Actually change it to Store Pickup, then show my orders.`
3. Show `audit_log` in the State tab.

**Wrap-up (30 s):** run `python scripts/run_demo.py all` to save live transcripts to `transcripts/`, and show the `adk deploy cloud_run` command from the README.
