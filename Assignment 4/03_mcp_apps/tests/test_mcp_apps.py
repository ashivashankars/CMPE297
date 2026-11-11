import asyncio
import os
import sys
import unittest
from pathlib import Path

os.environ["GENUI_LLM"], os.environ["GENUI_DELAY"] = "scripted", "0"
HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

import host  # noqa: E402


async def with_session(fn):
    async with host.session() as s:
        return await fn(s)


class MCPAppsTests(unittest.TestCase):
    def test_tools_point_at_ui_resources(self):
        tools = asyncio.run(with_session(lambda s: s.list_tools())).tools
        meta = {t.name: (t.meta or {}).get("ui", {}) for t in tools}
        self.assertEqual(meta["sales_dashboard"]["resourceUri"], "ui://sales/static.html")
        self.assertEqual(meta["render_spec"]["resourceUri"], "ui://sales/catalog.html")
        self.assertEqual(meta["drill_region"]["visibility"], ["app"])

    def test_view_resource_is_a_self_contained_mcp_app(self):
        res = asyncio.run(with_session(lambda s: s.read_resource("ui://sales/catalog.html"))).contents[0]
        self.assertEqual(res.mime_type, "text/html;profile=mcp-app")
        self.assertNotIn("import ", res.text.split("<script>")[1][:200])   # bundled, no module imports
        self.assertIn("function renderTree", res.text)

    def test_every_mode_end_to_end(self):
        for mode in ("static", "declarative", "open_ended", "mixed"):
            out = [m for m in host.PART.run(mode, "q3") if "__meta" not in m]
            self.assertEqual([m["mcp"] for m in out], ["tools/list", "model chose", "tools/call", "resources/read"], mode)
            self.assertFalse(out[2]["result"].get("isError"), mode)

    def test_model_does_not_see_app_only_tool(self):
        first = next(m for m in host.PART.run("static", "q3") if m.get("mcp") == "tools/list")
        self.assertNotIn("drill_region", first["modelSees"])

    def test_server_rejects_invalid_spec(self):
        r = asyncio.run(with_session(lambda s: s.call_tool("render_spec", {"spec": {"type": "Iframe"}})))
        self.assertTrue(r.is_error)

    def test_server_rejects_html_with_network_access(self):
        r = asyncio.run(with_session(lambda s: s.call_tool("render_html", {"title": "x", "html": "<script>fetch('https://evil')</script>"})))
        self.assertTrue(r.is_error)

    def test_host_refuses_unknown_tool_from_view(self):
        r = asyncio.run(host._call_from_view("delete_everything", {}))
        self.assertTrue(r["isError"])
        ok = asyncio.run(host._call_from_view("drill_region", {"region": "West"}))
        self.assertEqual(ok["structuredContent"]["region"], "West")


if __name__ == "__main__":
    unittest.main()
