"""OpenUI Lang by hand: tokenizer, parser, resolver - Python mirror of web/openui.mjs.

A program is one statement per line:

    root = Stack([title, kpis, chart])
    title = Heading("Q3 2026")
    kpis = Stack([Metric("Revenue", "$4.20M", "+12%"), Metric("Orders", "579,300")], "row")
    chart = BarChart("Revenue by region", ["West", "East"], [1420000, 1180000])

- arguments are POSITIONAL; each component has a fixed signature (SIGNATURES);
- a name may be used BEFORE it is defined (hoisting), which is what makes streaming
  work: the page re-parses after every chunk and draws unresolved names as placeholders;
- a later `name = ...` replaces an earlier one, so an app can patch a program by appending.
Compared with JSON, there are no repeated keys ("type", "props", "children"), which is
why OpenUI Lang is compact.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.catalog import CatalogError  # noqa: E402

# component -> (catalog type, positional parameter names)
SIGNATURES = {
    "Stack": ("Stack", ["children", "direction"]),
    "Card": ("Card", ["title", "children"]),
    "Heading": ("Heading", ["text"]),
    "Text": ("Text", ["text", "tone"]),
    "Metric": ("Metric", ["label", "value", "delta"]),
    "BarChart": ("BarChart", ["title", "labels", "values"]),
    "Table": ("Table", ["columns", "rows"]),
    "Badge": ("Badge", ["text", "tone"]),
    "Button": ("Button", ["label", "action", "params"]),
    "HtmlArtifact": ("HtmlView", ["title", "html"]),
    # STATIC mode: a pre-built component in OUR library; the model only passes values.
    "SalesOverview": ("SalesOverview", ["title", "revenue", "growth", "labels", "values"]),
}

TOKEN = re.compile(r'\s*(?:(?P<str>"(?:[^"\\]|\\.)*")|(?P<num>-?\d+(?:\.\d+)?)|(?P<name>[A-Za-z_]\w*)|(?P<p>[\[\](){},:=]))')


class ParseError(ValueError):
    pass


def tokenize(src):
    pos, out = 0, []
    while pos < len(src):
        if src[pos:].strip() == "":
            break
        m = TOKEN.match(src, pos)
        if not m:
            raise ParseError(f"unexpected character {src[pos]!r}")
        kind = m.lastgroup
        text = m.group(kind)
        out.append((kind, json.loads(text) if kind == "str" else float(text) if kind == "num" and "." in text
                    else int(text) if kind == "num" else text))
        pos = m.end()
    return out


class _P:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def eat(self, value=None):
        tok = self.peek()
        if tok[0] is None or (value is not None and tok[1] != value):
            raise ParseError(f"expected {value!r}, got {tok[1]!r}")
        self.i += 1
        return tok

    def expr(self):
        kind, val = self.peek()
        if kind in ("str", "num"):
            self.i += 1
            return val
        if kind == "p" and val == "[":
            self.eat("[")
            items = []
            while self.peek()[1] != "]":
                items.append(self.expr())
                if self.peek()[1] == ",":
                    self.eat(",")
            self.eat("]")
            return items
        if kind == "p" and val == "{":
            self.eat("{")
            obj = {}
            while self.peek()[1] != "}":
                k = self.eat()[1]
                self.eat(":")
                obj[k] = self.expr()
                if self.peek()[1] == ",":
                    self.eat(",")
            self.eat("}")
            return obj
        if kind == "name":
            self.i += 1
            if val in ("true", "false", "null"):
                return {"true": True, "false": False, "null": None}[val]
            if self.peek()[1] == "(":
                self.eat("(")
                args = []
                while self.peek()[1] != ")":
                    args.append(self.expr())
                    if self.peek()[1] == ",":
                        self.eat(",")
                self.eat(")")
                return {"$call": val, "args": args}
            return {"$ref": val}
        raise ParseError(f"unexpected token {val!r}")


def parse(program, *, partial=False):
    """Program text -> {name: expression}. With partial=True the last, possibly cut-off
    line is ignored, and lines that fail to parse are skipped (they are still streaming)."""
    lines = program.split("\n")
    if partial:
        lines = lines[:-1]
    stmts = {}
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        try:
            p = _P(tokenize(line))
            name = p.eat()[1]
            p.eat("=")
            stmts[name] = p.expr()
            if p.i != len(p.t):
                raise ParseError("extra tokens after expression")
        except ParseError as e:
            if partial:
                continue
            raise ParseError(f"line {n}: {e}: {line[:60]}") from None
    return stmts


def resolve(stmts, expr=None, seen=()):
    """Expressions -> normalized tree. Unknown names become {"pending": name}."""
    if expr is None:
        if "root" not in stmts:
            return {"pending": "root"}
        expr = stmts["root"]
    if isinstance(expr, list):
        return [resolve(stmts, e, seen) for e in expr]
    if isinstance(expr, dict) and "$ref" in expr:
        name = expr["$ref"]
        if name in seen:
            raise CatalogError(f"{name} refers to itself")
        return resolve(stmts, stmts[name], seen + (name,)) if name in stmts else {"pending": name}
    if isinstance(expr, dict) and "$call" in expr:
        comp = expr["$call"]
        if comp not in SIGNATURES:
            raise CatalogError(f"unknown component {comp}(...). Known: {', '.join(SIGNATURES)}")
        kind, names = SIGNATURES[comp]
        if len(expr["args"]) > len(names):
            raise CatalogError(f"{comp} takes at most {len(names)} arguments: {', '.join(names)}")
        props = {k: resolve(stmts, v, seen) for k, v in zip(names, expr["args"])}
        return to_node(kind, props)
    if isinstance(expr, dict):
        return {k: resolve(stmts, v, seen) for k, v in expr.items()}
    return expr


def to_node(kind, props):
    if kind == "Stack":
        return {"type": "Row" if props.get("direction") == "row" else "Column", "props": {}, "children": props.get("children") or []}
    if kind == "Card":
        return {"type": "Card", "props": {"title": props.get("title")}, "children": props.get("children") or []}
    if kind == "SalesOverview":   # the pre-built component's fixed layout
        top = (props.get("labels") or ["…"])[0]
        return {"type": "Card", "props": {"title": f"{props.get('title')} (pre-built SalesOverview)"}, "children": [
            {"type": "Row", "props": {}, "children": [
                {"type": "Metric", "props": {"label": "Revenue", "value": props.get("revenue"), "delta": props.get("growth")}},
                {"type": "Metric", "props": {"label": "Top region", "value": top}}]},
            {"type": "BarChart", "props": {"labels": props.get("labels"), "values": props.get("values")}},
            {"type": "Button", "props": {"label": f"Drill into {top}", "action": "drill_region", "params": {"region": top}}}]}
    return {"type": kind, "props": {k: v for k, v in props.items() if v is not None}, "children": []}
