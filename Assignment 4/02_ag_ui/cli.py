"""Terminal run of the AG-UI codelab: `python cli.py [--mode M] [--action] [--full]`."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import PART  # noqa: E402
from common import cli  # noqa: E402
from common.json_patch import apply_patch  # noqa: E402


def label(e):
    extra = e.get("toolCallName") or (", ".join(f"{o['op']} {o['path']}" for o in e["delta"]) if isinstance(e.get("delta"), list) else "")
    return f"{e['type']} {extra}".strip()[:28]


def trees(events):
    """Fold the stream the way the page does: state from snapshot+deltas, tool args by call id."""
    state, args, names, out = {}, {}, {}, []
    for e in events:
        t = e["type"]
        if t == "STATE_SNAPSHOT":
            state = json.loads(json.dumps(e["snapshot"]))
        elif t == "STATE_DELTA":
            state = apply_patch(state, e["delta"])
        elif t == "TOOL_CALL_START":
            names[e["toolCallId"]], args[e["toolCallId"]] = e["toolCallName"], ""
        elif t == "TOOL_CALL_ARGS":
            args[e["toolCallId"]] += e["delta"]
    for cid, name in names.items():
        a = json.loads(args[cid])
        if name == "show_sales_dashboard":   # what the page's registered component draws
            out.append({"type": "Card", "props": {"title": f"{a['title']} (pre-built widget)"}, "children": [
                {"type": "Metric", "props": {"label": "Revenue", "value": a["revenue"], "delta": a["growth"]}},
                {"type": "BarChart", "props": {"labels": [r["name"] for r in a["regions"]], "values": [r["revenue"] for r in a["regions"]]}}]})
        elif name == "render_html":
            out.append({"type": "HtmlView", "props": {"title": a["title"], "html": a["html"]}})
    if state.get("ui", {}).get("children"):
        out.append(state["ui"])
    if state.get("detail"):
        out.append(state["detail"])
    return out


if __name__ == "__main__":
    cli.main(PART, label, trees, action_body=lambda mode: {"action": {"name": "drill_region", "params": {"region": "West"}}})
