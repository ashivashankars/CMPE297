"""The AG-UI agent: a run is a generator of events.

How each mode reaches the page over the SAME event stream:

    static       the model calls the tool `show_sales_dashboard(...)`. The page has a
                 hand-built component registered for that tool name and draws it from
                 the streamed arguments (the "tool-based generative UI" pattern).
    declarative  the model calls `update_ui(patch)`. The server applies the patch to the
                 SHARED STATE and streams one STATE_DELTA per operation; the page renders
                 state.ui with the catalog. Generative UI = shared state.
    open_ended   the model calls `render_html(title, html)`; the html streams in
                 TOOL_CALL_ARGS and is mounted in a sandbox when TOOL_CALL_END arrives.
    mixed        like declarative, but state.ui contains one HtmlView node.

A user action starts a NEW run (RunAgentInput with the current state and a user
message describing the action). The server validates it, runs the server tool
`get_region_detail`, and patches state.
"""

import json
import sys
from pathlib import Path
from uuid import uuid4

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from common import data, llm  # noqa: E402
from common.catalog import ALLOWED_ACTIONS, CatalogError, catalog_prompt, validate  # noqa: E402
from common.html_policy import PolicyError, check_html  # noqa: E402
from common.json_patch import PatchError, apply_op  # noqa: E402

import events as E  # noqa: E402

FIX = HERE / "fixtures"
EMPTY_UI = {"type": "Column", "props": {}, "children": []}

TOOLS = {
    "show_sales_dashboard": "show_sales_dashboard(title, revenue, growth, regions: [{name, revenue}]) - the pre-built dashboard widget",
    "update_ui": "update_ui(patch: RFC 6902 ops on /ui) - edit the shared UI tree; nodes are {type, props, children}",
    "render_html": "render_html(title, html) - show a self-contained HTML document in a sandbox",
}
REPLY_FORMAT = ('Reply with ONE JSON object: {"text": "one short sentence", '
                '"tool_calls": [{"name": tool, "arguments": {...}}]}')
SYSTEMS = {
    "static": f"You drive a dashboard. Call exactly one tool:\n{TOOLS['show_sales_dashboard']}\n{REPLY_FORMAT}",
    "declarative": f"You build UI by editing shared state. Tool:\n{TOOLS['update_ui']}\n"
                   f"state.ui starts as {json.dumps(EMPTY_UI)}. Append nodes to /ui/children/-.\n"
                   f"Catalog:\n{catalog_prompt()}\n{REPLY_FORMAT}",
    "open_ended": f"Tool:\n{TOOLS['render_html']}\nNo network, no external files. "
                  f"Call window.genui.action(name, params) to send an action.\n{REPLY_FORMAT}",
    "mixed": f"You build UI by editing shared state. Tool:\n{TOOLS['update_ui']}\nCatalog:\n"
             f"{catalog_prompt(include_html=True)}\nUse ONE HtmlView only for what the catalog cannot show.\n{REPLY_FORMAT}",
}


def user_prompt(prompt):
    return f"{prompt}\n\nData (JSON):\n{json.dumps(data.summary())}"


class Part:
    name = "AG-UI · Agent-User Interaction protocol"
    web_dir = HERE / "web"
    default_prompt = "Show me Q3 sales by region"
    pace = 0.05 if llm.backend() == "scripted" else 0   # events arrive fast; slow them so you can watch

    def run(self, mode, prompt, run_input=None):
        ri = run_input or E.run_input(prompt, state={"ui": EMPTY_UI, "mode": mode})
        yield {"__meta": {"backend": llm.backend(), "mode": mode}}
        yield E.run_started(ri["threadId"], ri["runId"])
        state = json.loads(json.dumps(ri["state"]))
        yield E.state_snapshot(state)
        try:
            reply = json.loads(llm.strip_fences(llm.complete(SYSTEMS[mode], user_prompt(prompt), FIX / f"{mode}.json")))
        except Exception as e:  # noqa: BLE001
            yield E.run_error(f"model call failed: {e}")
            return
        if reply.get("text"):
            yield from E.text_message(reply["text"])
        for call in reply.get("tool_calls", []):
            yield from self._execute(call, state, mode)
        yield E.run_finished(ri["threadId"], ri["runId"])

    def _execute(self, call, state, mode):
        name, args = call.get("name"), call.get("arguments", {})
        allowed = {"static": {"show_sales_dashboard"}, "declarative": {"update_ui"},
                   "open_ended": {"render_html"}, "mixed": {"update_ui"}}[mode]
        cid = yield from E.tool_call(name, args)
        if name not in allowed:
            yield E.tool_result(cid, f"error: tool {name!r} is not available in {mode} mode")
            return
        if name == "show_sales_dashboard":
            # Rendering happens on the page (a registered component); the server just acknowledges.
            yield E.tool_result(cid, "rendered by the page's show_sales_dashboard component")
        elif name == "render_html":
            try:
                check_html(args.get("html", ""))
                yield E.tool_result(cid, "html accepted; mounted in sandbox")
            except PolicyError as e:
                yield E.tool_result(cid, f"error: {e}")
                yield E.ev("CUSTOM", name="html_rejected", value=str(e))
        elif name == "update_ui":
            applied = 0
            for op in args.get("patch", []):
                if not str(op.get("path", "")).startswith("/ui"):
                    yield E.tool_result(cid, f"error: may only patch /ui, not {op.get('path')}")
                    continue
                trial = json.loads(json.dumps(state))
                try:
                    apply_op(trial, op)
                    validate(trial["ui"], allow_html=mode == "mixed")
                    for node in _html_nodes(trial["ui"]):
                        check_html(node["props"]["html"])
                except (PatchError, CatalogError, PolicyError, KeyError, IndexError, ValueError) as e:
                    yield E.tool_result(cid, f"error: op {op.get('op')} {op.get('path')} rejected: {e}")
                    continue
                state.clear()
                state.update(trial)
                applied += 1
                yield E.state_delta([op])          # one delta per operation -> progressive render
            yield E.tool_result(cid, f"applied {applied} operation(s)")

    def action(self, mode, body):
        """A click: the page sends RunAgentInput {state, messages + the action}. A new run answers."""
        ri = body.get("runInput") or {}
        act = body.get("action") or {}
        yield {"__meta": {"backend": "app code (server tool)", "mode": mode}}
        yield E.run_started(ri.get("threadId", "thread_demo"), ri.get("runId", f"run_{uuid4().hex[:8]}"))
        if act.get("name") not in ALLOWED_ACTIONS or act.get("name") != "drill_region":
            yield E.run_error(f"action {act.get('name')!r} is not allowed here")
            return
        try:
            detail = data.region_detail(act.get("params", {}).get("region", ""))
        except KeyError as e:
            yield E.run_error(str(e))
            return
        cid = yield from E.tool_call("get_region_detail", {"region": detail["region"]})
        yield E.tool_result(cid, json.dumps(detail))
        node = {"type": "Card", "props": {"title": f"{detail['region']} · monthly detail"}, "children": [
            {"type": "Row", "props": {}, "children": [
                {"type": "Metric", "props": {"label": "Quarter total", "value": data.money(detail["total"])}},
                {"type": "BarChart", "props": {"title": "By month", "labels": detail["months"], "values": detail["revenue"]}}]}]}
        validate(node)
        yield E.state_delta([{"op": "add", "path": "/detail", "value": node}])
        yield from E.text_message(f"{detail['region']} grew every month of the quarter.")
        yield E.run_finished(ri.get("threadId", "thread_demo"), ri.get("runId", "run"))


def _html_nodes(node):
    if node.get("type") == "HtmlView":
        yield node
    for c in node.get("children") or []:
        yield from _html_nodes(c)


PART = Part()

if __name__ == "__main__":
    from common.server import serve
    serve(PART, int(sys.argv[1]) if len(sys.argv) > 1 else 8002)
