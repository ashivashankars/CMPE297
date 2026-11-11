"""A small coding-agent harness with generative UI as ONE MORE TOOL.

The loop is the classic harness loop:

    messages = [system, user]
    repeat (at most MAX_TURNS):
        reply = model(messages)                 # text and/or tool calls
        for each tool call: run it, append the result (errors are results too)
        stop when the model answers without tool calls

Tools:
    load_sales(group_by)        read the CSV (the agent gets data the normal way)
    load_region(region)         monthly numbers for one region
    render_ui(...)              put an interface on the user's surfaces - validated per mode:
        static       {"component": "sales_overview", "props": {...}}   pre-built component
        declarative  {"tree": {...catalog tree...}}
        open_ended   {"html": "<!doctype html>..."}                    sandboxed
        mixed        {"tree": {... with HtmlView ...}}
        any mode     {"component": "region_detail", "props": {"region": ...}}  pre-built drill-down

A validation failure is returned to the model as the tool result, so the model can
correct itself on the next turn (the declarative fixture shows exactly that).
A click on the web surface becomes a new USER message: "[ui action] drill_region {...}".
The harness emits events; the terminal and the web page are two surfaces for them.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from common import data, llm  # noqa: E402
from common.catalog import ALLOWED_ACTIONS, CatalogError, catalog_prompt, validate  # noqa: E402
from common.html_policy import PolicyError, check_html  # noqa: E402

MAX_TURNS = 6
FIX = HERE / "fixtures"

TOOL_DOCS = """Tools (call them by replying with JSON {"text": "...", "tool_calls": [{"name": ..., "arguments": {...}}]};
reply with no tool_calls when you are done):
- load_sales(group_by: "region") -> quarter totals per region
- load_region(region) -> monthly revenue for one region
- render_ui(...) -> show an interface to the user. In every mode render_ui({"component": "region_detail", "props": {"region"}})
  shows the pre-built drill-down. Other arguments depend on the UI mode:"""
MODE_DOCS = {
    "static": 'render_ui({"component": "sales_overview", "props": {title, revenue, growth, labels[], values[]}})',
    "declarative": 'render_ui({"tree": {type, props, children}}) using ONLY this catalog:\n' + catalog_prompt(),
    "open_ended": 'render_ui({"html": "<!doctype html>..."}) a self-contained document; window.genui.action(name, params) sends actions',
    "mixed": 'render_ui({"tree": ...}) from this catalog, with ONE HtmlView for what it cannot show:\n' + catalog_prompt(include_html=True),
}


def system_prompt(mode):
    return f"You are a data assistant inside a harness.\n{TOOL_DOCS}\n{MODE_DOCS[mode]}"


def sales_overview(p):
    """The pre-built component for static mode (developer-owned layout)."""
    top = p["labels"][0]
    return {"type": "Card", "props": {"title": f"{p['title']} (pre-built sales_overview)"}, "children": [
        {"type": "Row", "props": {}, "children": [
            {"type": "Metric", "props": {"label": "Revenue", "value": p["revenue"], "delta": p.get("growth")}},
            {"type": "Metric", "props": {"label": "Top region", "value": top}}]},
        {"type": "BarChart", "props": {"labels": p["labels"], "values": p["values"]}},
        {"type": "Button", "props": {"label": f"Drill into {top}", "action": "drill_region", "params": {"region": top}}}]}


class Tools:
    def __init__(self, mode):
        self.mode = mode

    def load_sales(self, group_by="region"):
        if group_by != "region":
            raise ValueError("group_by must be 'region'")
        s = data.summary()
        return {"quarter": s["quarter"], "revenue": s["revenue"], "growth": s["growth"], "orders": s["orders"],
                "avg_ticket": s["avg_ticket"], "regions": s["regions"]}

    def load_region(self, region):
        return data.region_detail(region)

    def render_ui(self, **args):
        """Validate, then return the tree to draw. Raises with a model-readable reason."""
        m = self.mode
        if args.get("component") == "region_detail":     # pre-built, allowed in every mode
            d = data.region_detail((args.get("props") or {}).get("region", ""))
            return {"type": "Card", "props": {"title": f"{d['region']} · monthly detail (pre-built region_detail)"}, "children": [
                {"type": "Row", "props": {}, "children": [
                    {"type": "Metric", "props": {"label": "Quarter total", "value": data.money(d["total"])}},
                    {"type": "BarChart", "props": {"title": "By month", "labels": d["months"], "values": d["revenue"]}}]}]}
        if m == "static":
            if args.get("component") != "sales_overview":
                raise CatalogError("static mode: component must be 'sales_overview'")
            p = args.get("props") or {}
            missing = {"title", "revenue", "labels", "values"} - set(p)
            if missing:
                raise CatalogError(f"sales_overview: missing props {sorted(missing)}")
            tree = sales_overview(p)
        elif m == "open_ended":
            tree = {"type": "HtmlView", "props": {"title": args.get("title", "Generated view"), "html": check_html(args.get("html"))}}
        else:
            tree = args.get("tree")
            if not isinstance(tree, dict):
                raise CatalogError("render_ui needs a 'tree' object")
            regions = validate(tree, allow_html=m == "mixed")
            if m == "mixed" and regions != 1:
                raise CatalogError(f"mixed mode expects exactly one HtmlView, found {regions}")
            for n in _walk(tree):
                if n["type"] == "HtmlView":
                    check_html(n["props"]["html"])
        validate(tree)
        return tree


def _walk(n):
    yield n
    for c in n.get("children") or []:
        yield from _walk(c)


# ---------------------------------------------------------------- models

class ScriptedModel:
    """Replays fixtures/<name>.json: a list of turns. {{region}} is replaced with the region of the
    last UI action, so the replay reacts to the button you actually clicked."""

    def __init__(self, name, variables=None):
        text = llm.load_fixture(FIX / f"{name}.json")
        for k, v in (variables or {}).items():
            text = text.replace("{{" + k + "}}", v)
        self.turns = json.loads(text)

    def __call__(self, system, messages):
        return self.turns.pop(0) if self.turns else {"text": "(script finished)", "tool_calls": []}


class LiveModel:
    def __call__(self, system, messages):
        transcript = "\n".join(f"[{m['role']}] {m['content']}" for m in messages)
        return json.loads(llm.strip_fences(llm.complete(system, transcript + "\n[assistant]", fixture=None)))


# ---------------------------------------------------------------- the loop

class Harness:
    def __init__(self, mode):
        self.mode, self.tools = mode, Tools(mode)
        self.messages = []

    def run(self, user_text, model):
        """Generator of events: turn, text, tool_call, tool_result, render, done."""
        self.messages.append({"role": "user", "content": user_text})
        yield {"event": "user", "content": user_text}
        for turn in range(1, MAX_TURNS + 1):
            reply = model(system_prompt(self.mode), self.messages)
            yield {"event": "turn", "n": turn}
            if reply.get("text"):
                yield {"event": "text", "content": reply["text"]}
            calls = reply.get("tool_calls") or []
            self.messages.append({"role": "assistant", "content": json.dumps(reply)})
            if not calls:
                yield {"event": "done", "turns": turn}
                return
            for call in calls:
                name, args = call.get("name"), call.get("arguments") or {}
                yield {"event": "tool_call", "name": name, "arguments": _short(args)}
                try:
                    fn = getattr(self.tools, name, None)
                    if fn is None or name.startswith("_"):
                        raise ValueError(f"unknown tool {name!r}")
                    out = fn(**args)
                    if name == "render_ui":
                        yield {"event": "render", "tree": out}
                        result = "rendered on the user's surfaces"
                    else:
                        result = json.dumps(out)
                    yield {"event": "tool_result", "name": name, "ok": True, "content": result}
                except (CatalogError, PolicyError, ValueError, KeyError, TypeError) as e:
                    result = f"error: {e}"
                    yield {"event": "tool_result", "name": name, "ok": False, "content": result}
                self.messages.append({"role": "tool", "content": f"{name} -> {result}"})
        yield {"event": "done", "turns": MAX_TURNS, "stopped": "turn limit"}

    def ui_action(self, name, params, model):
        """A click on a rendered Button (or in the sandbox) arrives as a user message."""
        if name not in ALLOWED_ACTIONS:
            yield {"event": "error", "content": f"action {name!r} not allowed"}
            return
        yield from self.run(f"[ui action] {name} {json.dumps(params)}", model)


def _short(args):
    return {k: (v[:80] + f"… ({len(v)} chars)" if isinstance(v, str) and len(v) > 100 else v) for k, v in args.items()}


def model_for(name, variables=None):
    return ScriptedModel(name, variables) if llm.backend() == "scripted" else LiveModel()


def safe_region(params):
    region = str((params or {}).get("region", ""))
    return region if re.fullmatch(r"[A-Za-z ]{1,20}", region) else "West"
