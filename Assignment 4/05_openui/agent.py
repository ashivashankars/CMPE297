"""The OpenUI Lang agent: the model streams a PROGRAM, not JSON.

    static       root = SalesOverview(...)  - one call to a pre-built library component
    declarative  a full program from the catalog signatures (Stack, Card, Metric, ...)
    open_ended   root = HtmlArtifact(title, "<!doctype html>...") - sandboxed document
    mixed        catalog components + one HtmlArtifact

The server forwards raw text deltas (the page re-parses after every chunk, exactly as
OpenUI's streaming renderer does), then validates the finished program and reports
its size next to the equivalent JSON tree.
An action (drill_region) is answered by APPENDING lines to the program:
later definitions replace earlier ones.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from common import data, llm  # noqa: E402
from common.catalog import CatalogError, validate  # noqa: E402
from common.html_policy import PolicyError, check_html  # noqa: E402

import openui  # noqa: E402

FIX = HERE / "fixtures"

RULES = """You answer with OpenUI Lang only. One statement per line: name = Expression.
`root` is the entry point. Arguments are POSITIONAL. References may be used before they are defined.
Strings use double quotes with JSON escapes. Every name except root must be referenced.
Signatures (? = optional):"""
SIGS = {
    "Stack": "Stack(children: any[], direction?: \"column\" | \"row\")",
    "Card": "Card(title: string, children: any[])",
    "Heading": "Heading(text)", "Text": "Text(text, tone?: \"muted\")",
    "Metric": "Metric(label, value, delta?)", "BarChart": "BarChart(title, labels: string[], values: number[])",
    "Table": "Table(columns: string[], rows: any[][])", "Badge": "Badge(text, tone?: \"info\"|\"success\"|\"warning\")",
    "Button": "Button(label, action: \"drill_region\", params?: {region})",
    "HtmlArtifact": "HtmlArtifact(title, html) - a self-contained HTML document run in a sandbox; window.genui.action(name, params) sends an action",
    "SalesOverview": "SalesOverview(title, revenue, growth, labels[], values[]) - the pre-built dashboard",
}
ALLOWED = {
    "static": ["SalesOverview"],
    "declarative": ["Stack", "Card", "Heading", "Text", "Metric", "BarChart", "Table", "Badge", "Button"],
    "open_ended": ["HtmlArtifact"],
    "mixed": ["Stack", "Card", "Heading", "Text", "Metric", "BarChart", "Table", "Badge", "Button", "HtmlArtifact"],
}


def system(mode):
    return RULES + "\n" + "\n".join(SIGS[c] for c in ALLOWED[mode])


def check_program(program, mode):
    stmts = openui.parse(program)
    used = set(_calls(list(stmts.values())))
    bad = used - set(ALLOWED[mode])
    if bad:
        raise CatalogError(f"{mode} mode may not use {sorted(bad)}")
    tree = openui.resolve(stmts)
    if mode == "static":
        return tree
    regions = validate(_no_pending(tree), allow_html=mode in ("open_ended", "mixed"))
    if mode in ("open_ended", "mixed") and regions < 1:
        raise CatalogError("this mode expects an HtmlArtifact")
    for n in _walk(tree):
        if n["type"] == "HtmlView":
            check_html(n["props"]["html"])
    return tree


def _calls(expr):
    """Component names actually called (from the parsed program, not the raw text)."""
    if isinstance(expr, list):
        for e in expr:
            yield from _calls(e)
    elif isinstance(expr, dict):
        if "$call" in expr:
            yield expr["$call"]
        for v in expr.values():
            yield from _calls(v)


def _walk(n):
    yield n
    for c in n.get("children") or []:
        yield from _walk(c)


def _no_pending(n):
    if "pending" in n:
        raise CatalogError(f"{n['pending']!r} is used but never defined")
    for c in n.get("children") or []:
        _no_pending(c)
    return n


class Part:
    name = "OpenUI Lang · a compact UI language"
    web_dir = HERE / "web"
    default_prompt = "Show me Q3 sales by region"
    pace = 0.03 if llm.backend() == "scripted" else 0   # slow the replay so you can watch it stream

    def run(self, mode, prompt):
        yield {"__meta": {"backend": llm.backend(), "mode": mode}}
        program = ""
        for chunk in llm.stream_text(system(mode), f"{prompt}\n\nData: {json.dumps(data.summary())}", FIX / f"{mode}.oui"):
            program += chunk
            yield {"delta": chunk}
        program = llm.strip_fences(program)
        try:
            tree = check_program(program, mode)
        except (openui.ParseError, CatalogError, PolicyError) as e:
            yield {"error": f"program invalid: {e}"}
            return
        yield {"done": True, "bytes": len(program.encode()), "jsonTreeBytes": len(json.dumps(tree).encode()),
               "statements": len(openui.parse(program))}

    def action(self, mode, body):
        """body = {action, params, program}: answered with lines to append."""
        yield {"__meta": {"backend": "app code (no model)", "mode": mode}}
        if body.get("action") != "drill_region":
            yield {"error": f"unknown action {body.get('action')!r}"}
            return
        try:
            d = data.region_detail(body.get("params", {}).get("region", ""))
        except KeyError as e:
            yield {"error": str(e)}
            return
        program = body.get("program", "")
        detail = (f'detail = Card("{d["region"]} · monthly detail", [Stack([Metric("Quarter total", "{data.money(d["total"])}"), '
                  f'BarChart("By month", {json.dumps(d["months"])}, {json.dumps(d["revenue"])})], "row")])\n')
        if "\ndetail = " in "\n" + program:
            yield {"append": detail}                     # already drilled: replace only the detail
            return
        root_rhs = next((l.split("=", 1)[1].strip() for l in program.splitlines() if l.startswith("root =")), None)
        if root_rhs is None:
            yield {"error": "program has no root"}
            return
        yield {"append": f"page = {root_rhs}\n{detail}root = Stack([page, detail])\n"}


PART = Part()

if __name__ == "__main__":
    from common.server import serve
    serve(PART, int(sys.argv[1]) if len(sys.argv) > 1 else 8005)
