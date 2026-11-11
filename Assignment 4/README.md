# Assignment 4: Generative UI (GenUX) codelabs

**CMPE 297 · Emerging Topics in AI · Fall 2026**

The assignment asks for A2UI, AG-UI, MCP Apps, json-render, OpenUI Lang and harness integration, each shown in four modes: **static**, **declarative**, **open-ended** and **mixed**. Every part comes with a code walkthrough, recorded execution, and a video.

I build the same Q3 sales dashboard in every codelab. The data, the component catalog and the sandbox are shared across all six parts, so the only thing that changes between them is the generative-UI technology.

Reference used: [dlmastery/simple-coding-harness/genui](https://github.com/dlmastery/simple-coding-harness/tree/main/genui).

## The four modes

| Mode | What the model decides | What the app owns | Safety boundary |
|---|---|---|---|
| **Static** | Which pre-built component to show, and its values | Every layout and component | Argument check |
| **Declarative** | A layout composed from a **catalog** of allowed components | The catalog, validation, rendering | Catalog validation |
| **Open-ended** | Arbitrary HTML/CSS/JS | Only the frame around it | Sandboxed iframe + CSP + content policy |
| **Mixed** | Catalog layout plus **one** sandboxed custom region | The catalog and the sandbox | Both |

## The six codelabs

| # | Folder | Technology | Static | Declarative | Open-ended | Mixed | Video |
|---|---|---|---|---|---|---|---|
| 0 | [`common/`](common) | Shared foundation: catalog, renderer, sandbox, LLM | | | | | [00_foundations.mp4](videos/00_foundations.mp4) |
| 1 | [`01_a2ui/`](01_a2ui) | **A2UI v0.9**: surfaces, flat components, data model | template + `updateDataModel` | model writes JSONL messages | `HtmlView` component | catalog + `HtmlView` | [01_a2ui.mp4](videos/01_a2ui.mp4) |
| 2 | [`02_ag_ui/`](02_ag_ui) | **AG-UI**: typed event stream (SSE) + shared state | tool call → registered component | `STATE_DELTA` JSON Patches | `render_html` tool args | state tree with `HtmlView` | [02_ag_ui.mp4](videos/02_ag_ui.mp4) |
| 3 | [`03_mcp_apps/`](03_mcp_apps) | **MCP Apps**: `ui://` views in a host, JSON-RPC bridge | hand-written view | catalog view draws spec | nested sandbox | catalog view + nested sandbox | [03_mcp_apps.mp4](videos/03_mcp_apps.mp4) |
| 4 | [`04_json_render/`](04_json_render) | **json-render**: flat spec streamed as JSON Patch | custom `SalesOverview` element | elements + `$state`, `visible`, `repeat`, `on.press` | `HtmlView` element | elements + `HtmlView` | [04_json_render.mp4](videos/04_json_render.mp4) |
| 5 | [`05_openui/`](05_openui) | **OpenUI Lang**: compact positional language, streamed | `root = SalesOverview(...)` | full program, forward refs | `HtmlArtifact(...)` | catalog + `HtmlArtifact` | [05_openui.mp4](videos/05_openui.mp4) |
| 6 | [`06_harness/`](06_harness) | **Harness integration**: `render_ui` as a tool in the agent loop | pre-built component | tree + self-correction on error | HTML | tree + one `HtmlView` | [06_harness.mp4](videos/06_harness.mp4) |

Each codelab folder has a **README with a step-by-step code walkthrough**, a `cli.py` (terminal run), a web server (browser run), `fixtures/` (the recorded model outputs) and `tests/`.

## Run it

You need Python 3.11+ and Node 18+ (Node is only used for the browser-module tests). The only Python package required is `mcp`, for part 3.

```bash
cd "Assignment 4"
python -m pip install -r requirements.txt     # mcp (part 3) + playwright/pygments (only for screenshots/videos)

./run_all.sh          # all tests + every codelab in the terminal -> docs/execution_logs/
./start_all.sh        # all six web servers
#   A2UI http://127.0.0.1:8001   AG-UI :8002   MCP Apps :8003
#   json-render :8004            OpenUI :8005  Harness :8006
```

You can also run a single part:

```bash
cd 01_a2ui
python cli.py --mode declarative --action    # messages, the click, and a terminal render
python agent.py 8001                         # then open http://127.0.0.1:8001
python -m unittest discover -s tests -v
```

### Scripted vs live model

By default, every codelab **replays the model's reply** from `fixtures/` and streams it in small chunks, so the runs are reproducible, work offline and cost nothing. If you set a key, the same code calls a real model instead:

```bash
export ANTHROPIC_API_KEY=...            # optional: GENUI_MODEL=claude-sonnet-5-5
# or: export OPENAI_API_KEY=...         # optional: OPENAI_BASE_URL, GENUI_MODEL
```

The prompts are built from the same catalog that validates the output (see `SYSTEMS` in each `agent.py`). Parsing, validation, rendering and actions follow the same code path in both backends. The page header shows which backend produced each run.

## Evidence of execution

| What | Where |
|---|---|
| Test results (37 Python + 3 Node tests, all passing) | [`docs/execution_logs/00_tests.txt`](docs/execution_logs/00_tests.txt) |
| Terminal runs, all 4 modes + a click, per part | [`docs/execution_logs/`](docs/execution_logs) |
| Browser screenshots, every mode before and after a click (48 images) | [`docs/screenshots/`](docs/screenshots) |
| Videos (code walkthrough + terminal run + live browser demo) | [`videos/`](videos) |
| Narration script for every video, with timestamps | [`docs/VIDEO_SCRIPT.md`](docs/VIDEO_SCRIPT.md) |

## Architecture

```
            prompt + data
                 │
         ┌───────▼────────┐   common/llm.py: scripted fixture or live model
         │     model      │
         └───────┬────────┘
     format-specific output: A2UI JSONL │ AG-UI tool call / state patch │ MCP tool call
                             json-render patches │ OpenUI program │ harness render_ui
                 │
         ┌───────▼────────┐   per-part parser + common/catalog.py (validate)
         │   validate     │   + common/html_policy.py (open-ended HTML)
         └───────┬────────┘   errors go back to the model / page, never rendered
                 │  normalized tree {type, props, children}
     ┌───────────┴────────────┐
     ▼                        ▼
 browser: components.mjs    terminal: common/terminal.py
 + sandbox.mjs (HtmlView)
     │ click → named action (allowed list) → server/app → more messages
```

## What I learned

- **A2UI, json-render and OpenUI Lang are *formats*** that describe a UI. **AG-UI is a *transport*** (events and shared state). **MCP Apps is a *hosting model*** (another application embeds your view). These are separate decisions.
- A **flat** structure (A2UI components, json-render elements, OpenUI statements with forward references) is what makes **progressive streaming** possible.
- The **catalog is the contract**: it acts as the prompt, the validator and the registry at the same time. Validation errors are sent back to the model as **feedback**. In part 6, the model fixes an invalid `PieChart` on its next turn.
- Model-written HTML is only acceptable inside a **sandbox**: no same-origin, a CSP that blocks the network, and a single action message shape. MCP Apps nests that sandbox two levels deep.
- **Mixed mode** (catalog plus one sandboxed region) is the practical default. You get the safety and consistency of the catalog, and an escape hatch for the occasional interactive widget the catalog cannot express.
- On byte size, the same dashboard as OpenUI Lang is **60%** of its JSON-tree size (822 vs 1374 bytes, `05_openui` declarative). This is a byte count on one example, not a tokenizer benchmark.
