# 02 · AG-UI: Agent-User Interaction protocol

Video: [`videos/02_ag_ui.mp4`](../videos/02_ag_ui.mp4) · Logs: [`docs/execution_logs/02_ag_ui.txt`](../docs/execution_logs/02_ag_ui.txt) · Screenshots: [`docs/screenshots/02_ag_ui/`](../docs/screenshots/02_ag_ui)

**Idea:** AG-UI is a **transport**, not a UI format. A run is a stream of typed JSON events over SSE that carries assistant text, tool calls and **shared state** between the agent and the page. Generative UI then means one of two things: a tool call the page knows how to draw, or a UI tree kept in shared state.

```
RUN_STARTED → STATE_SNAPSHOT → TEXT_MESSAGE_START/CONTENT…/END
           → TOOL_CALL_START → TOOL_CALL_ARGS… → TOOL_CALL_END → (STATE_DELTA…) → TOOL_CALL_RESULT
           → RUN_FINISHED   (or RUN_ERROR)
```

## Files

| File | What it does |
|---|---|
| `events.py` | Event constructors with camelCase wire fields (same JSON as the official `@ag-ui/core` types). `text_message()` and `tool_call()` stream in pieces. `run_input()` builds a `RunAgentInput` |
| `agent.py` | `Part.run()`: one run as a generator. `_execute()` handles the tools for each mode. `action()` starts a new run for a click |
| `fixtures/*.json` | The model's reply in each mode: `{"text", "tool_calls": [...]}` |
| `web/agui-client.mjs` | A hand-written AG-UI client: folds events into messages, tool calls and state; `TOOL_RENDERERS` |
| `cli.py`, `tests/test_ag_ui.py` (6 tests) | Terminal run; tests |

## Step-by-step walkthrough

**Step 1: events** (`events.py`). `text_message()` yields START, then 24-character CONTENT deltas, then END. `tool_call()` serializes the arguments and yields them as 160-character `TOOL_CALL_ARGS` deltas, the way a model streams function arguments.

**Step 2: a run** (`Part.run`). It always starts with `RUN_STARTED` and a `STATE_SNAPSHOT` of `{"ui": <empty Column>, "mode": ...}`, and always ends with `RUN_FINISHED`, or `RUN_ERROR` if the model call fails. The page can rely on that lifecycle.

**Step 3: STATIC: a tool with a registered component.** The model calls `show_sales_dashboard(title, revenue, growth, regions)`. The server only acknowledges with `TOOL_CALL_RESULT`. In the browser, `TOOL_RENDERERS.show_sales_dashboard` is **our** pre-built widget (shown with a ★ and a thick border). It re-renders as the arguments stream in, because `tryParse()` returns `null` until the JSON is complete.

**Step 4: DECLARATIVE: generative UI as shared state.** The model calls `update_ui({"patch": [...]})`. `_execute()` applies each op to a **copy** of the state, validates `state.ui` against the catalog, and only then commits and emits **one `STATE_DELTA` per op**. A rejected op becomes a `TOOL_CALL_RESULT` error and is never rendered (`test_invalid_patch_is_rejected_with_a_tool_result`). The page applies each delta with `applyPatch()` and re-paints `state.ui`, so the dashboard builds up node by node. The final op is a `replace` that updates the heading text in place.

**Step 5: OPEN-ENDED.** The model calls `render_html(title, html)`. The HTML streams through `TOOL_CALL_ARGS`, and the page shows "receiving html… N bytes". On `TOOL_CALL_END` it mounts the document with `mountHtml()`. The server runs `check_html()` and reports policy failures as an error result plus a `CUSTOM html_rejected` event.

**Step 6: MIXED.** This is the same `update_ui` path, but `validate(..., allow_html=True)` accepts an `HtmlView` node, and its HTML is also policy-checked.

**Step 7: actions start a new run.** A click POSTs `{action, runInput}`, where `runInput` is a `RunAgentInput` carrying the **current state** and a user message `"[ui action] drill_region {...}"`. `Part.action()` validates the action, runs the server tool `get_region_detail` (visible as `TOOL_CALL_*` events), and emits `STATE_DELTA add /detail`, then a text message.

**Step 8: the client** (`agui-client.mjs`). A `switch` on `e.type` handles text bubbles, tool-call renderers and state. A collapsible "shared state" panel shows the live state, with HTML elided.

## Run

```bash
python cli.py --mode declarative --action
python agent.py 8002                 # http://127.0.0.1:8002/?mode=static
python -m unittest discover -s tests -v
```
