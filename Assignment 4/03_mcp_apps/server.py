"""An MCP server whose tools come with user interfaces (MCP Apps, SEP-1865).

MCP Apps adds three things to a normal MCP server:
  1. a RESOURCE with a ui:// URI and MIME type text/html;profile=mcp-app (the "view");
  2. a TOOL whose _meta.ui.resourceUri points at that view;
  3. a tool RESULT with `content` (text, for the model and for hosts without UI)
     and `structuredContent` (data, for the view).
The host reads the view, mounts it in a sandboxed iframe and talks to it with
JSON-RPC over postMessage (ui/initialize, ui/notifications/tool-result, tools/call ...).

Four tools = the four generative-UI modes, each with its own view:
  sales_dashboard   STATIC       hand-written view; the model only supplies arguments
  render_spec       DECLARATIVE  the model sends a catalog tree; a generic catalog view draws it
  render_html       OPEN-ENDED   the model sends HTML; the view nests it in a second sandbox
  render_mixed      MIXED        catalog tree with one HtmlView region (nested sandbox)
  drill_region      app-only tool (visibility ["app"]): the view calls it through the host

    python server.py          # stdio (what host.py, Claude Desktop, Goose... launch)
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from mcp import types  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402

from common import data  # noqa: E402
from common.catalog import CatalogError, validate  # noqa: E402
from common.html_policy import PolicyError, check_html  # noqa: E402
from common.terminal import render as to_text  # noqa: E402

MIME = "text/html;profile=mcp-app"
VIEWS = HERE / "views"
COMMON_WEB = HERE.parent / "common" / "web"
# Restrictive: the views are self-contained, so no domains are declared.
VIEW_META = {"ui": {"csp": {"connectDomains": [], "resourceDomains": []}, "prefersBorder": True}}

mcp = MCPServer("cmpe297-sales-apps", log_level="WARNING")


def bundle(view_file):
    """A view must be ONE self-contained document. Inline the shared design system
    (components.mjs + sandbox.mjs + style.css) so the view draws the same catalog."""
    def strip_module(src):
        src = re.sub(r"^import .*?;\s*$", "", src, flags=re.M)
        return re.sub(r"^export (const|function|class|async function)", r"\1", src, flags=re.M)
    lib = strip_module((COMMON_WEB / "sandbox.mjs").read_text()) + "\n" + strip_module((COMMON_WEB / "components.mjs").read_text())
    html = (VIEWS / view_file).read_text()
    html = html.replace("/*__CATALOG_CSS__*/", (COMMON_WEB / "style.css").read_text())
    html = html.replace("/*__CATALOG_JS__*/", lib)
    html = html.replace("/*__BRIDGE_JS__*/", (VIEWS / "app-bridge.js").read_text())
    return html


def result(text, structured):
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], structured_content=structured)


def error(text):
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=True)


# ------------------------------------------------------------------ STATIC
@mcp.tool(meta={"ui": {"resourceUri": "ui://sales/static.html"}})
def sales_dashboard(quarter: str = "Q3") -> types.CallToolResult:
    """Pre-built Q3 sales dashboard (revenue, orders, regions)."""
    s = data.summary()
    text = f"{s['quarter']}: revenue {data.money(s['revenue'])} ({s['growth']}), " + \
           ", ".join(f"{r['region']} {data.money(r['revenue'])}" for r in s["regions"])
    return result(text, s)


# ------------------------------------------------------------------ DECLARATIVE
@mcp.tool(meta={"ui": {"resourceUri": "ui://sales/catalog.html"}})
def render_spec(spec: dict) -> types.CallToolResult:
    """Render a UI tree {type, props, children} built ONLY from the catalog (no HtmlView)."""
    try:
        validate(spec, allow_html=False)
    except CatalogError as e:
        return error(f"invalid spec: {e}")   # the model reads this and can retry
    return result(to_text(spec), {"tree": spec})


# ------------------------------------------------------------------ OPEN-ENDED
@mcp.tool(meta={"ui": {"resourceUri": "ui://sales/open.html"}})
def render_html(title: str, html: str) -> types.CallToolResult:
    """Show a self-contained HTML document (no network) in a nested sandbox."""
    try:
        check_html(html)
    except PolicyError as e:
        return error(f"html rejected: {e}")
    return result(f"[interactive view '{title}' - open in a host that supports MCP Apps]", {"title": title, "html": html})


# ------------------------------------------------------------------ MIXED
@mcp.tool(meta={"ui": {"resourceUri": "ui://sales/catalog.html"}})
def render_mixed(spec: dict) -> types.CallToolResult:
    """Render a catalog tree that may contain HtmlView regions for what the catalog cannot show."""
    try:
        if validate(spec, allow_html=True) < 1:
            raise CatalogError("mixed mode expects at least one HtmlView region")
        for node in _walk(spec):
            if node["type"] == "HtmlView":
                check_html(node["props"]["html"])
    except (CatalogError, PolicyError) as e:
        return error(f"invalid spec: {e}")
    return result(to_text(spec), {"tree": spec})


# ------------------------------------------------------------------ app-only action tool
@mcp.tool(meta={"ui": {"visibility": ["app"]}})
def drill_region(region: str) -> types.CallToolResult:
    """Monthly detail for one region. Called by views, hidden from the model."""
    try:
        d = data.region_detail(region)
    except KeyError as e:
        return error(str(e))
    tree = {"type": "Card", "props": {"title": f"{d['region']} · monthly detail"}, "children": [
        {"type": "Row", "props": {}, "children": [
            {"type": "Metric", "props": {"label": "Quarter total", "value": data.money(d["total"])}},
            {"type": "BarChart", "props": {"title": "By month", "labels": d["months"], "values": d["revenue"]}}]}]}
    return result(to_text(tree), {"tree": tree, **d})


def _walk(n):
    yield n
    for c in n.get("children") or []:
        yield from _walk(c)


# ------------------------------------------------------------------ the views
@mcp.resource("ui://sales/static.html", name="static dashboard view", mime_type=MIME, meta=VIEW_META)
def static_view() -> str:
    return bundle("static.html")


@mcp.resource("ui://sales/catalog.html", name="catalog renderer view", mime_type=MIME, meta=VIEW_META)
def catalog_view() -> str:
    return bundle("catalog.html")


@mcp.resource("ui://sales/open.html", name="nested-sandbox HTML view", mime_type=MIME, meta=VIEW_META)
def open_view() -> str:
    return bundle("open.html")

if __name__ == "__main__":
    mcp.run("stdio")
