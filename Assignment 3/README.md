# Assignment 3 — End-to-end Google ADK agent applications

CMPE 297 · Emerging Technologies in AI/ML · Fall 2026 · Archana

Five agents built with the [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/), each adapted from the reference sample named in the assignment and extended toward production quality. Every agent runs locally with just a Gemini API key; cloud-only pieces (Cloud SQL, AlloyDB, Cloud Run) are replaced by local equivalents with the production configuration included alongside.

| # | Agent | Folder | ADK features exercised | Reference |
|---|---|---|---|---|
| a | Deep-research **lead generation** agent | [`lead_generation_agent/`](lead_generation_agent/) | AgentTool, SequentialAgent, **dynamic ParallelAgent fan-out** (custom BaseAgent), google_search, Pydantic `output_schema`, state machine in callbacks, artifacts | [blog](https://cloud.google.com/blog/products/ai-machine-learning/build-a-deep-research-agent-with-google-adk) · [repo](https://github.com/MagnIeeT/leadGenerationAgentADK) |
| b | **Gemini CLI as a tool** inside an ADK pipeline | [`gemini_cli_agent/`](gemini_cli_agent/) | Function tools wrapping a subprocess, SequentialAgent + **LoopAgent self-critique**, `exit_loop`, budgets, Dockerfile / Cloud Run | [article](https://medium.com/@derrickchwong/combine-adk-gemini-cli-and-cloud-run-c5dea5118853) · [repo](https://github.com/derrickchwong/gemini-cli-on-adk) |
| c | **MCP-tools** software bug assistant | [`bug_assistant_agent/`](bug_assistant_agent/) | **Custom MCP server (stdio)**, McpToolset, GitHub remote MCP (streamable HTTP), MCP Toolbox for Databases config, AgentTool(google_search), LangChain tool | [blog](https://cloud.google.com/blog/topics/developers-practitioners/tools-make-an-agent-from-zero-to-assistant-with-adk) · [sample](https://github.com/google/adk-samples) |
| d | Production **code review assistant** | [`code_review_assistant/`](code_review_assistant/) | Multi-agent review pipeline, **sandboxed code execution**, LoopAgent fix cycle, `user:` state for cross-session history, versioned artifacts | [codelab](https://codelabs.developers.google.com/adk-code-reviewer-assistant/instructions) · [repo](https://github.com/ayoisio/adk-code-review-assistant) |
| e | Production **e-commerce agent** | [`ecommerce_agent/`](ecommerce_agent/) | MCP store server with transactional orders, **identity enforcement** in `before_tool_callback`, **human-in-the-loop confirmation** on checkout, audit log, AlloyDB Toolbox config | [codelab](https://codelabs.developers.google.com/codelabs/sports-agent-adk-mcp-alloydb) · [repo](https://github.com/mtoscano84/sports-agent-adk-mcp-alloydb) |

📹 **Video walkthrough:** [`video/Assignment3_ADK_walkthrough.mp4`](https://drive.google.com/file/d/15sSZnusLJcKP1WpK4NsnFMuozfsHFav3/view?usp=sharing), a narrated code and execution walkthrough of all five agents. Timestamps and a script for recording a live version are in [`VIDEO_WALKTHROUGH.md`](VIDEO_WALKTHROUGH.md).

🧾 **Execution traces:** [`transcripts/offline/`](transcripts/offline/) has one trace per agent: every sub-agent hop, tool call, tool result and state change.

---

## 1. Setup (5 minutes)

```bash
git clone https://github.com/ashivashankars/CMPE297.git
cd "CMPE297/Assignment 3"
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then paste your GOOGLE_API_KEY (https://aistudio.google.com/apikey)

# only for agent (b):
npm install -g @google/gemini-cli
```

## 2. Run

```bash
adk web            # opens http://localhost:8000 — pick an agent from the dropdown
# or in the terminal:
adk run ecommerce_agent
```

`adk web` lists exactly the five agents. Its **Events** tab shows every tool call, sub-agent hop and state change, the **State** tab shows session state, and the **Artifacts** tab holds the generated reports (lead report, Gemini CLI report, code reviews, fixed code).

Headless demo with a saved transcript (good evidence for grading):

```bash
python scripts/run_demo.py ecommerce_agent      # or: all
# -> transcripts/ecommerce_agent.md
```

## 3. Test (no API key needed)

```bash
pytest            # 19 tests, ~5 s
TRACE_DIR=transcripts/offline pytest -v   # also write readable execution traces
```

The tests replace Gemini with a scripted fake model (`tests/fake_llm.py`) but run **everything else for real**: both MCP servers as stdio subprocesses, SQLite transactions, the fake Gemini CLI binary, parallel fan-out, loop escalation, callbacks, state and artifacts. This checks the wiring of each multi-agent flow end to end without spending tokens.

| Test file | What it proves |
|---|---|
| `test_a_lead_generation.py` | 2-turn run: intent → pattern discovery (parallel ×2) → leads (parallel ×2) → report artifact; parameter clamping |
| `test_b_gemini_cli.py` | URL allow-list blocks injection; CLI executes inside the cloned repo; critic rejects draft 1 and approves draft 2; call budget |
| `test_c_bug_assistant.py` | Real MCP stdio round-trips: duplicate search, create, invalid-priority rejection, update, date-range query |
| `test_d_code_review.py` | Review → fix flow; fix loop runs twice and exits on SUCCESSFUL; `user:` history; 3 artifacts saved |
| `test_e_ecommerce.py` | Full shopping journey; spoofed `user_email` is overridden; stock/ownership rules; checkout pauses for human confirmation |

## 4. Repository layout

```
Assignment 3/
├── lead_generation_agent/   (a)  agent.py, sub_agents/{pipelines,research_fanout}.py, schemas.py, callbacks.py
├── gemini_cli_agent/        (b)  agent.py, tools.py, Dockerfile, cloudbuild.yaml, deploy_cloud_run.sh
├── bug_assistant_agent/     (c)  agent.py, tools.py, mcp_server/ticket_server.py, deployment/toolbox/
├── code_review_assistant/   (d)  agent.py, tools.py, sub_agents/{review,fix}_pipeline.py
├── ecommerce_agent/         (e)  agent.py, guards.py, mcp_server/store_server.py, deployment/toolbox/
├── tests/                        offline e2e tests + fake LLM + fake Gemini CLI
├── scripts/run_demo.py           live scripted demos -> transcripts/
├── transcripts/offline/          execution traces from the e2e tests
├── video/                        narrated walkthrough video (mp4)
├── VIDEO_WALKTHROUGH.md          timestamps + live recording script
├── requirements.txt  .env.example  pytest.ini
```

Each agent folder has its own README with an architecture diagram, a file-by-file code walkthrough, demo prompts, and what was changed relative to the reference.

## 5. Deploying any agent

```bash
# Cloud Run (ADK builds the container for you)
adk deploy cloud_run --project $PROJECT_ID --region us-central1 --with_ui ./code_review_assistant
# Vertex AI Agent Engine
adk deploy agent_engine --project $PROJECT_ID --region us-central1 ./bug_assistant_agent
```

Agent (b) needs Node + the Gemini CLI inside the image, so it ships its own [`Dockerfile`](gemini_cli_agent/Dockerfile) and [`deploy_cloud_run.sh`](gemini_cli_agent/deploy_cloud_run.sh).

## 6. Notes and known limits

- **ADK version.** Tested on `google-adk 2.13`. ADK 2.x marks `SequentialAgent`/`ParallelAgent`/`LoopAgent` as deprecated in favour of `Workflow`, but they remain fully supported, are what the reference samples use, and `Workflow` cannot yet be used as an LlmAgent sub-agent. You'll see a deprecation warning at startup; it's harmless.
- **Models.** Defaults are `gemini-2.5-flash` / `gemini-2.5-pro`; change `GEMINI_FAST_MODEL` / `GEMINI_PRO_MODEL` in `.env` to any model your key supports.
- **Local stand-ins.** Cloud SQL + pgvector (c) and AlloyDB (e) are replaced by SQLite MCP servers with keyword/TF-IDF search. The equivalent MCP Toolbox `tools.yaml` files are included, and setting `MCP_TOOLBOX_URL` switches the agent to them.
- **Cost.** Agent (a) makes 2 + 2k + 2m model calls per full run with search grounding; k and m are capped at 10.
