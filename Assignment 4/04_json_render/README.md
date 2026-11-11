# 04 · json-render: one flat spec, streamed as JSON Patch

Video: [`videos/04_json_render.mp4`](../videos/04_json_render.mp4) · Logs: [`docs/execution_logs/04_json_render.txt`](../docs/execution_logs/04_json_render.txt) · Screenshots: [`docs/screenshots/04_json_render/`](../docs/screenshots/04_json_render)

**Idea:** a json-render spec is `{root, elements, state}`, where `elements` is a **flat map**. The model streams it as RFC 6902 JSON Patch lines, one element or state value per line, so the page can paint after the first few lines. The same spec can be drawn by more than one renderer; here, the browser and the terminal.

```json
{"op":"add","path":"/root","value":"main"}
{"op":"add","path":"/elements/main","value":{"type":"Column","props":{},"children":["title","kpis", ...]}}
{"op":"add","path":"/elements/title","value":{"type":"Heading","props":{"text":{"$state":"/title"}}}}
{"op":"add","path":"/state/title","value":"Q3 2026 - revenue up 12%, West leads"}
```

## Files

| File | What it does |
|---|---|
| `jsonrender.py` | `check_op()` (per-line checks), `resolve()` (`$state`, `$item`), `visible()`, `to_tree()` (repeat + `on.press`), `expand_static()` (the `SalesOverview` registry component), `detail_patches()` (the server's answer to a click) |
| `agent.py` | Streams the model's JSONL, forwards each patch after checking it, runs a final check on the complete spec, handles actions |
| `fixtures/*.jsonl` | The model's patch stream per mode |
| `web/jr-renderer.mjs` | Browser mirror: keeps the spec, applies patches, resolves, paints; built-in `setState` runs locally |
| `cli.py`, `tests/test_json_render.py` (5 tests) | Terminal renderer; tests |

## Step-by-step walkthrough

**Step 1: check each line while streaming** (`check_op`). Only `/root`, `/elements/…` and `/state…` may be patched. Element types must be in the catalog (or be `SalesOverview`), props must be known, and an `action` inside `props` is rejected with "put actions in the element's 'on' field".

**Step 2: forward or reject** (`Part._forward`). Each patch is applied to the server's copy of the spec and then yielded to the page. A rejected patch becomes an `{"error"}` message and is not applied. When the stream ends, `final_check()` resolves the whole spec and validates the tree. Elements that are referenced but never defined are reported.

**Step 3: resolve the spec into a tree** (`to_tree`):
- `{"$state": "/kpi/revenue"}` reads the state;
- `"visible": {"$state": "/showTable", "eq": true}` filters an element;
- `"repeat": {"statePath": "/regions"}` renders the children once per item, with `{"$item": "label"}` reading the current item;
- `"on": {"press": {"action": "drill_region", "params": {...}}}` becomes the catalog Button's action.

**Step 4: STATIC.** One element of type `SalesOverview`, a custom registry component whose layout we wrote (`expand_static` / `SalesOverview()` in JS). The model only fills its props.

**Step 5: DECLARATIVE.** The full spec streams in. The state patches come right after the elements that use them, so the first paint shows the layout with placeholders (`test_first_patch_paints_partial_tree`).

**Step 6: OPEN-ENDED and MIXED.** An `HtmlView` element (sandboxed). It is forbidden in declarative mode, required in the other two, and its HTML is always policy-checked.

**Step 7: two kinds of action** (`web/jr-renderer.mjs`):
- `setState` is **built in and client-only**: "Hide orders" sets `/state/showTable` to `false` and the table disappears through `visible`, with no server call. The log shows `local setState`.
- `drill_region` is POSTed with the current root id. The **server** answers with more patches on the same spec: it adds detail elements and state, wraps the old root in a new `page` Column, and replaces `/root`.

**Step 8: one spec, two renderers.** `cli.py` replays the same patches and draws the result with `common/terminal.py`.

## Run

```bash
python cli.py --mode declarative --action
python agent.py 8004                 # http://127.0.0.1:8004/?mode=declarative
python -m unittest discover -s tests -v
```
