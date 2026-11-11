"""A minimal MCP Apps HOST: an MCP client (stdio) + a web page that embeds views.

What a host does, in order (each step is one wire-log entry in the page):
  1. tools/list         - learn the tools; tools with _meta.ui.visibility == ["app"] are
                          hidden from the model (only views may call them)
  2. the model chooses  - one tool + arguments (scripted fixture, or a live model)
  3. tools/call         - run it on the MCP server; get content + structuredContent
  4. resources/read     - fetch the ui:// view named by the tool's _meta.ui.resourceUri
  5. mount + bridge     - (browser) sandboxed iframe + CSP, JSON-RPC over postMessage,
                          deliver tool-input and tool-result, proxy the view's tools/call

    python host.py 8003     then open http://127.0.0.1:8003
"""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

from common import data, llm  # noqa: E402
from common.catalog import catalog_prompt  # noqa: E402

FIX = HERE / "fixtures"
SERVER = StdioServerParameters(command=sys.executable, args=[str(HERE / "server.py")], cwd=str(HERE))


@asynccontextmanager
async def session():
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            yield s


def dump(model):
    return model.model_dump(by_alias=True, exclude_none=True, mode="json")


def visible_to_model(tool):
    vis = ((tool.get("_meta") or {}).get("ui") or {}).get("visibility", ["model", "app"])
    return "model" in vis


def system_prompt(mode, tools):
    listing = "\n".join(f"- {t['name']}: {t.get('description', '').strip()}" for t in tools)
    hint = {"static": "Use sales_dashboard.", "declarative": f"Use render_spec. Catalog:\n{catalog_prompt()}",
            "open_ended": "Use render_html with a self-contained document; call window.genui.action(name, params) for actions.",
            "mixed": f"Use render_mixed. Catalog:\n{catalog_prompt(include_html=True)}"}[mode]
    return f"Tools:\n{listing}\n{hint}\nReply with ONE JSON object: {{\"tool\": name, \"arguments\": {{...}}}}"


async def _run(mode, prompt):
    out = []
    async with session() as s:
        tools = [dump(t) for t in (await s.list_tools()).tools]
        model_tools = [t for t in tools if visible_to_model(t)]
        out.append({"mcp": "tools/list", "modelSees": [t["name"] for t in model_tools],
                    "hiddenAppOnly": [t["name"] for t in tools if not visible_to_model(t)]})
        reply = json.loads(llm.strip_fences(llm.complete(system_prompt(mode, model_tools),
                                                         f"{prompt}\n\nData: {json.dumps(data.summary())}",
                                                         FIX / f"{mode}.json", delay=0)))
        tool = next((t for t in model_tools if t["name"] == reply.get("tool")), None)
        out.append({"mcp": "model chose", "tool": reply.get("tool"), "arguments": reply.get("arguments", {})})
        if tool is None:
            out.append({"error": f"model chose unknown or hidden tool {reply.get('tool')!r}"})
            return out
        result = dump(await s.call_tool(tool["name"], reply.get("arguments", {})))
        out.append({"mcp": "tools/call", "name": tool["name"], "result": result})
        uri = ((tool.get("_meta") or {}).get("ui") or {}).get("resourceUri")
        if uri:   # a host without MCP Apps support would stop here and show result.content text
            res = dump(await s.read_resource(uri))["contents"][0]
            out.append({"mcp": "resources/read", "uri": uri, "mimeType": res["mimeType"], "_meta": res.get("_meta", {}),
                        "html": res["text"], "tool": tool, "toolInput": reply.get("arguments", {})})
    return out


async def _call_from_view(name, arguments):
    """A view asked the host to call a tool. The host decides: same server, tool must exist and allow 'app'."""
    async with session() as s:
        tools = {t.name: dump(t) for t in (await s.list_tools()).tools}
        tool = tools.get(name)
        vis = ((tool or {}).get("_meta", {}).get("ui") or {}).get("visibility", ["model", "app"])
        if tool is None or "app" not in vis:
            return {"isError": True, "content": [{"type": "text", "text": f"host refused tools/call {name!r}"}]}
        return dump(await s.call_tool(name, arguments))


class Part:
    name = "MCP Apps · minimal host"
    web_dir = HERE / "web"
    default_prompt = "Show me Q3 sales by region"
    pace = 0.25 if llm.backend() == "scripted" else 0

    def run(self, mode, prompt):
        yield {"__meta": {"backend": llm.backend(), "mode": mode}}
        yield from asyncio.run(_run(mode, prompt))

    def action(self, mode, body):
        """In the browser, a view's click arrives as a bridge tools/call (see post()).
        The CLI simulates the same request here."""
        yield {"mcp": "tools/call from view", "name": body.get("name"),
               "result": asyncio.run(_call_from_view(body.get("name"), body.get("arguments") or {}))}

    def post(self, handler, url, body):
        if url.path != "/api/call-tool":
            return False
        handler.send_json(asyncio.run(_call_from_view(body.get("name"), body.get("arguments") or {})))
        return True


PART = Part()

if __name__ == "__main__":
    from common.server import serve
    serve(PART, int(sys.argv[1]) if len(sys.argv) > 1 else 8003)
