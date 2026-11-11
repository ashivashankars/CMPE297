# 06 · Harness integration: generative UI as a tool in the agent loop

Video: [`videos/06_harness.mp4`](../videos/06_harness.mp4) · Logs: [`docs/execution_logs/06_harness.txt`](../docs/execution_logs/06_harness.txt) · Screenshots: [`docs/screenshots/06_harness/`](../docs/screenshots/06_harness)

**Idea:** in a coding or data agent harness, the UI is **just another tool**. The agent loads data with ordinary tools and then calls `render_ui`. The harness validates the UI for the current mode. A validation failure is returned to the model **as the tool result**, so the model can fix it on the next turn. The harness emits events to two surfaces, the terminal and the web page, and a click on the web surface becomes a new **user message** in the same session.

```
user ─▶ model ─▶ load_sales ─▶ result ─▶ model ─▶ render_ui(PieChart) ─▶ ✗ error result
                                          model ─▶ render_ui(BarChart…) ─▶ ✓ render ─▶ surfaces
click ─▶ "[ui action] drill_region {...}" ─▶ model ─▶ load_region ─▶ render_ui(region_detail)
```

## Files

| File | What it does |
|---|---|
| `harness.py` | `Harness.run()` (the loop, `MAX_TURNS = 6`), `Tools` (`load_sales`, `load_region`, `render_ui`), `ScriptedModel` / `LiveModel`, `ui_action()` |
| `agent.py` | Keeps one `Harness` per mode, so clicks continue the same conversation; serves the web surface |
| `cli.py` | The terminal surface |
| `fixtures/<mode>.json` | The model's turns. `action.json` is the reply to a click (`{{region}}` = the region that was clicked) |
| `web/harness-surface.mjs` | Transcript (turns, calls, results, errors) plus rendered UIs |
| `tests/test_harness.py` (5 tests) | |

## Step-by-step walkthrough

**Step 1: the loop** (`Harness.run`). Append the user message, then for each turn: ask the model, emit its text, run every tool call, and append each result (including errors) as a `tool` message. Stop when the model replies with no tool calls, or at `MAX_TURNS` (`test_turn_limit`).

**Step 2: data tools.** `load_sales(group_by="region")` and `load_region(region)` read the CSV through `common/data.py`, the same way a harness reads files.

**Step 3: `render_ui`, one tool with four contracts** (`Tools.render_ui`):
- **static**: `{"component": "sales_overview", "props": {...}}`. Any other shape is refused (`test_static_mode_refuses_free_trees`);
- **declarative**: `{"tree": ...}` validated against the catalog, with HtmlView not allowed;
- **open-ended**: `{"html": ...}` checked with `check_html`;
- **mixed**: `{"tree": ...}` with **exactly one** HtmlView;
- in every mode, `{"component": "region_detail", "props": {"region"}}` is the pre-built drill-down.

**Step 4: errors are results, and the model recovers.** In `fixtures/declarative.json`, turn 2 uses a `PieChart`. The harness returns `error: root.children[1]: unknown component 'PieChart'. Allowed: …`. Turn 3 switches to `BarChart` and the render succeeds (`test_validation_error_is_a_result_and_model_recovers`). With a live model this is the same self-correction loop.

**Step 5: two surfaces.** Every `render` event carries the validated tree. `cli.py` draws it with the terminal renderer; the web page draws it with `components.mjs` and the sandbox.

**Step 6: clicks are user messages** (`Harness.ui_action`). The action name is checked against `ALLOWED_ACTIONS`, and then `run("[ui action] drill_region {\"region\": \"South\"}")` continues **the same** `messages` list, so the model sees the whole earlier conversation (`test_click_continues_the_same_session`).

**Step 7: scripted vs live.** `ScriptedModel` pops recorded turns, and `LiveModel` sends the transcript to `common/llm.py`. The loop, tools and validation do not change between the two.

## Run

```bash
python cli.py --mode declarative          # watch the PieChart error and the fix
python cli.py --mode mixed --action
python agent.py 8006                      # http://127.0.0.1:8006/?mode=declarative
python -m unittest discover -s tests -v
```
