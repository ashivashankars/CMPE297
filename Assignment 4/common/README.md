# 00 · Foundations: what all six codelabs share

Video: [`videos/00_foundations.mp4`](../videos/00_foundations.mp4)

The six codelabs differ only in the generative-UI technology. Everything else is shared, which keeps the comparison fair:

| File | Role |
|---|---|
| `data.py`, `fixtures/sales_q3.csv` | The one scenario: Q3 revenue/orders for 4 regions × 3 months, plus `region_detail()` for drill-downs |
| `catalog.py` | **The catalog**: 11 components with typed props. `validate()` checks a normalized tree; `catalog_prompt()` turns the catalog into prompt text |
| `html_policy.py` | Content policy for model-written HTML: no external scripts, network calls, nested frames or storage; size limit |
| `llm.py` | `stream_text(system, user, fixture)`: replays a fixture (scripted) or calls Anthropic / an OpenAI-compatible API (live) |
| `json_patch.py`, `web/json-patch.mjs` | RFC 6902 JSON Patch (used by AG-UI `STATE_DELTA` and json-render streams) |
| `terminal.py` | A second renderer: draws a normalized tree as text |
| `server.py` | A stdlib HTTP server that streams a part's messages as SSE (`/api/run`, `/api/action`) |
| `cli.py` | Shared terminal runner: prints every message, then the terminal render |
| `web/components.mjs` | The browser registry, with one function per catalog component. `renderTree()` / `paint()` |
| `web/sandbox.mjs` | The open-ended boundary: `sandbox="allow-scripts"` iframe, CSP, `window.genui.action()` bridge |
| `web/shell.mjs`, `web/style.css` | Page frame shared by all parts: mode tabs, prompt, rendered UI, and a wire log of every message |
| `fixtures/dashboard.html`, `fixtures/forecast.html` | The HTML documents the "model" writes in open-ended mode (donut chart) and mixed mode (what-if slider) |

## Step-by-step walkthrough

**Step 1: the normalized tree.** Every format is converted to this shape before validation and rendering:

```json
{"type": "Card", "props": {"title": "Revenue by region"}, "children": [
  {"type": "BarChart", "props": {"labels": ["West", "East"], "values": [1420000, 1180000]}}]}
```

**Step 2: the catalog is the contract** (`catalog.py`). One table drives three things:
- the **prompt**: `catalog_prompt()` prints `- Metric(label: string, value: string, delta?: string) - One KPI number…`;
- the **validator**: `validate()` raises `CatalogError("root.children[1]: unknown component 'PieChart'. Allowed: …")`, with messages written so the model can act on them;
- the **registry**: `web/components.mjs` uses the same names.

**Step 3: actions are names, not code.** A `Button` carries `action: "drill_region"` and `params`. Only names in `ALLOWED_ACTIONS` pass validation, and the server decides what each name does.

**Step 4: the sandbox** (`web/sandbox.mjs`). `mountHtml()` creates `<iframe sandbox="allow-scripts">`. Without `allow-same-origin` the frame has an opaque origin, so it cannot read the page, its cookies or its storage. `buildSrcdoc()` injects a CSP *before* the model's markup (`connect-src 'none'`, no external scripts) and a tiny bridge: `window.genui.action(name, params)` posts `{genui: "action", …}`. The page accepts only messages whose `event.source` is that frame, and only allowed action names.

**Step 5: scripted vs live model** (`llm.py`). `backend()` picks `anthropic`, `openai` or `scripted`. A scripted run replays `fixtures/<mode>.*` in 48-character chunks with a small delay, so the browser genuinely receives a stream. `{{json:dashboard.html}}` in a fixture inlines a shared HTML document as a JSON string.

**Step 6: one page shell** (`web/shell.mjs`). Each part provides `createRenderer(surface, ctx)` and `label(msg)`. The shell handles the mode tabs, reads SSE with `fetch` + `ReadableStream` (`readSSE()`), logs every message (⬇ in, ⬆ out), and posts actions.
