"""Terminal run of the MCP Apps codelab: `python cli.py [--mode M] [--action] [--full]`.
The terminal is a host WITHOUT MCP Apps support for HTML, so it shows result.content
text plus the catalog tree from structuredContent."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import cli  # noqa: E402
from host import PART  # noqa: E402


def label(m):
    return f"{m['mcp']} {m.get('name') or (m.get('tool') if isinstance(m.get('tool'), str) else m.get('uri', ''))}"[:28]


def trees(messages):
    out = []
    for m in messages:
        if m["mcp"].startswith("tools/call"):
            sc = m["result"].get("structuredContent") or {}
            if "tree" in sc:
                out.append(sc["tree"])
            elif "html" in sc:
                out.append({"type": "HtmlView", "props": {"title": sc["title"], "html": sc["html"]}})
            elif "regions" in sc:   # the static view's data, drawn as the hand-written view would
                out.append({"type": "Card", "props": {"title": f"{sc['quarter']} (static view data)"}, "children": [
                    {"type": "Metric", "props": {"label": "Revenue", "value": f"${sc['revenue']/1e6:.2f}M", "delta": sc["growth"]}},
                    {"type": "BarChart", "props": {"labels": [r["region"] for r in sc["regions"]],
                                                   "values": [r["revenue"] for r in sc["regions"]]}}]})
    return out


if __name__ == "__main__":
    cli.main(PART, label, trees, action_body=lambda mode: {"name": "drill_region", "arguments": {"region": "West"}})
