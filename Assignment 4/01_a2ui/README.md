# 01 · A2UI: Agent-to-User Interface (v0.9)

Video: [`videos/01_a2ui.mp4`](../videos/01_a2ui.mp4) · Logs: [`docs/execution_logs/01_a2ui.txt`](../docs/execution_logs/01_a2ui.txt) · Screenshots: [`docs/screenshots/01_a2ui/`](../docs/screenshots/01_a2ui)

**Idea:** A2UI keeps **structure** and **data** apart. The agent sends a flat list of components that refer to each other by id, and a separate data model. Components bind to data with JSON Pointers (`{"path": "/kpi/revenue"}`), so changing a number is a tiny `updateDataModel` with no layout resent.

```
createSurface(sales) → updateComponents(sales) → updateDataModel(sales) → … → deleteSurface
                         flat list, ids              values at a JSON Pointer
```

## Files

| File | What it does |
|---|---|
| `a2ui.py` | Envelope builders, `check_envelope()`, JSON Pointer get/set, `Surface` (components + data → tree), `Client` (applies messages in order) |
| `agent.py` | The four modes and the action handler. `TEMPLATES` = our pre-built surfaces (static mode) |
| `fixtures/*.jsonl` | What the model writes in each mode (`static.json` is a template choice) |
| `web/a2ui-renderer.mjs` | Browser mirror of `a2ui.py`: surfaces, binding resolution, painting, action messages |
| `cli.py` | Terminal run; `tests/test_a2ui.py` has 7 tests |

## Step-by-step walkthrough

**Step 1: the four envelopes** (`a2ui.py`: `create_surface`, `update_components`, `update_data_model`, `delete_surface`). Every message has `"version": "v0.9.1"` and exactly one of the four keys. `check_envelope()` enforces that and gives readable errors (for example, an unknown surface: "send createSurface first").

**Step 2: the surface** (`Surface.resolve`, `Surface.tree`). `components` is a dict by id, so a later `updateComponents` with the same id *replaces* that component. `tree("root")` walks children ids. An id that has not arrived yet becomes `{"pending": id}`, which the browser draws as a skeleton, so the page renders while the stream is still arriving. A2UI Buttons hold their label as a child `Text` and their action as `{"event": {"name", "context"}}`, and `tree()` maps that onto the catalog `Button`.

**Step 3: STATIC** (`Part._static`). The model replies `{"widget": "sales_overview", "args": {...}}`. Our code sends `createSurface`, then **our** `TEMPLATES["sales_overview"]`, then `updateDataModel("/", args)`. The model never writes a component. The test `test_static_layout_comes_from_our_template` checks this.

**Step 4: DECLARATIVE** (`Part._stream_jsonl`). The model writes JSONL (`fixtures/declarative.jsonl`). As each complete line arrives it is applied to a `Client` and checked (`_check_components`), and only then forwarded. HtmlView is rejected in this mode. After the stream ends, `validate_all()` checks every surface against the catalog. In the browser you can watch the title appear empty and fill in when `updateDataModel /title` arrives.

**Step 5: OPEN-ENDED.** A2UI deliberately never ships code. Our custom catalog (`CATALOG_ID`) adds one escape-hatch component, `HtmlView`, whose `html` is checked by `html_policy.check_html()` and mounted by `common/web/sandbox.mjs`.

**Step 6: MIXED.** The same JSONL stream mixes catalog components (Metric, BarChart, Button) with **one** HtmlView for the what-if slider. `require_html` makes sure the region is there.

**Step 7: actions** (`Part.action`). A click sends the A2UI client→server message:
```json
{"version": "v0.9.1", "action": {"name": "drill_region", "surfaceId": "sales", "sourceComponentId": "drill_west", "context": {"region": "West"}}}
```
The server checks the name against `ALLOWED_ACTIONS`. In static mode our template draws the detail surface. In the other modes the model designs the `detail` surface with **bindings only** (`fixtures/action.jsonl`), and then the **app** sends `updateDataModel` with the real numbers for the region that was clicked. This is A2UI's separation of structure and data in practice.

**Step 8: the browser** (`web/a2ui-renderer.mjs`). `onMessage()` applies the same four envelopes, and `Surface.tree()` resolves bindings. Each surface is painted separately with a header showing its component count and data keys.

## Run

```bash
python cli.py                       # all four modes
python cli.py --mode mixed --action # one mode + a click
python agent.py 8001                # browser: http://127.0.0.1:8001/?mode=declarative
python -m unittest discover -s tests -v
```

Excerpt from `cli.py --mode mixed --action`:
```
createSurface(sales)     {"version": "v0.9.1", "createSurface": {"surfaceId": "sales", ...}}
updateComponents(sales)  {... "components": [{"id": "root", "component": "Column", ...
updateDataModel(sales)   {... "path": "/", "value": {"revenue": "$4.20M", "top": "West", ...
⬆ user action: {"version": "v0.9.1", "action": {"name": "drill_region", ...}}
createSurface(detail) · updateComponents(detail) · updateDataModel(detail)
✓ catalog-valid tree: 9 nodes, 1 sandboxed HtmlView region(s)
```
