# 03 · MCP Apps: UI resources inside a host (SEP-1865)

Video: [`videos/03_mcp_apps.mp4`](../videos/03_mcp_apps.mp4) · Logs: [`docs/execution_logs/03_mcp_apps.txt`](../docs/execution_logs/03_mcp_apps.txt) · Screenshots: [`docs/screenshots/03_mcp_apps/`](../docs/screenshots/03_mcp_apps)

**Idea:** in the earlier parts, my own page renders the UI. With MCP Apps, **another application (the host) embeds the UI**. A real MCP server publishes a `ui://` HTML resource next to its tool. The host reads it, mounts it in a sandboxed iframe, and talks to it over JSON-RPC `postMessage`.

```
host.py (MCP client, stdio) ──tools/list, tools/call, resources/read──▶ server.py (MCPServer)
   │ SSE
browser host page ──srcdoc + CSP──▶ <iframe sandbox="allow-scripts"> view
   ◀── ui/initialize · ui/notifications/initialized · tools/call · ui/message ──
   ──▶ ui/notifications/tool-input · ui/notifications/tool-result · responses ──▶
```

## Files

| File | What it does |
|---|---|
| `server.py` | The MCP server (official `mcp` 2.x SDK, `MCPServer`, stdio). Four UI tools (one per mode), one app-only tool, three `ui://` resources (MIME `text/html;profile=mcp-app`). `bundle()` inlines the shared design system so every view is a single self-contained document |
| `views/static.html` | Hand-written view (**static**) |
| `views/catalog.html` | Generic catalog renderer (**declarative** + **mixed**) |
| `views/open.html` | Nests model HTML in a second sandbox (**open-ended**) |
| `views/app-bridge.js` | The view side of the bridge: `app.connect()`, `app.callTool()`, `app.say()` |
| `host.py` | The host: MCP client session, model choice, `tools/call`, `resources/read`; `/api/call-tool` proxies the view's calls |
| `web/host-bridge.mjs` | The browser side of the host: CSP from `_meta.ui.csp`, mounting, the JSON-RPC handler |
| `tests/test_mcp_apps.py` (7 tests) | Start the real server over stdio |

## Step-by-step walkthrough

**Step 1: a tool that points at a view** (`server.py`):
```python
@mcp.tool(meta={"ui": {"resourceUri": "ui://sales/static.html"}})
def sales_dashboard(quarter: str = "Q3") -> types.CallToolResult:
    return result(text, s)   # content: text for the model / text-only hosts; structured_content: data for the view
```

**Step 2: the view resource.** `@mcp.resource("ui://sales/static.html", mime_type="text/html;profile=mcp-app", meta=VIEW_META)` returns one complete HTML document. `VIEW_META` declares **no** network or resource domains, so the host applies its most restrictive CSP.

**Step 3: the four modes as four tools.**
- `sales_dashboard` → **static** view: every element is hand-written, and only numbers arrive (`structuredContent`).
- `render_spec(spec)` → **declarative**: the **server validates** the tree against the catalog. An invalid spec returns `isError` with a readable message, and the view never sees it.
- `render_html(title, html)` → **open-ended**: policy-checked, then `views/open.html` mounts it in a **nested** sandbox, two boundaries deep.
- `render_mixed(spec)` → **mixed**: catalog tree with at least one `HtmlView`, each nested-sandboxed.

**Step 4: an app-only tool.** `drill_region` has `_meta.ui.visibility = ["app"]`. `host.py` hides it from the model (`modelSees` vs `hiddenAppOnly` in the wire log), but views may call it.

**Step 5: the host's sequence** (`host._run`): `tools/list` → the model chooses a tool and arguments (`fixtures/<mode>.json`) → `tools/call` → `resources/read` of `_meta.ui.resourceUri`. A host without MCP Apps support would stop after `tools/call` and show `result.content`. The page shows that text too, so you can compare.

**Step 6: mounting and the bridge** (`web/host-bridge.mjs`). `cspFor()` builds the CSP, adding only well-formed declared domains. `withCsp()` puts it before any of the view's markup. `handle()` answers `ui/initialize` with host info and context. **Only after** `ui/notifications/initialized` does it send `tool-input` and `tool-result`. It proxies `tools/call` to `/api/call-tool`, shows `ui/message` in the chat, and resizes on `size-changed`. It accepts messages only from that iframe's `contentWindow`.

**Step 7: a click inside a view** (`views/app-bridge.js`). `app.callTool("drill_region", {region})` is a JSON-RPC request to the host. `host._call_from_view()` re-checks that the tool exists and allows `"app"` before calling the MCP server (`test_host_refuses_unknown_tool_from_view`). The view then paints the returned tree itself.

## Run

```bash
pip install "mcp>=2.3,<3"
python cli.py --mode static --action     # real MCP over stdio, terminal = a text-only host
python host.py 8003                      # http://127.0.0.1:8003/?mode=open_ended
python -m unittest discover -s tests -v
python server.py                         # the same server can be added to any MCP host (stdio)
```
