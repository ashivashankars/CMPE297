"""A second renderer for the same normalized tree: plain text for a terminal.

"One spec, two renderers": the browser draws components.mjs, the CLI draws this.
HtmlView cannot run in a terminal, so it degrades to a labelled placeholder,
which is exactly what a host without HTML support should do.
"""

BAR = "█"


def render(node, indent=0):
    return "\n".join(_lines(node, indent))


def _lines(node, ind):
    pad = "  " * ind
    t, p, kids = node["type"], node.get("props") or {}, node.get("children") or []
    out = []
    if t in ("Column", "Row"):
        for k in kids:
            out += _lines(k, ind)
    elif t == "Card":
        title = p.get("title") or ""
        out.append(f"{pad}┌─ {title} " + "─" * max(2, 44 - len(title)))
        if p.get("subtitle"):
            out.append(f"{pad}│ {p['subtitle']}")
        for k in kids:
            out += [f"{pad}│ {line}" for line in _lines(k, 0)]
        out.append(f"{pad}└" + "─" * 48)
    elif t == "Heading":
        out.append(f"{pad}## {p['text']}")
    elif t == "Text":
        out.append(f"{pad}{p['text']}")
    elif t == "Metric":
        out.append(f"{pad}[{p['label']}] {p['value']}" + (f"  ({p['delta']})" if p.get("delta") else ""))
    elif t == "Badge":
        out.append(f"{pad}({p['text']})")
    elif t == "BarChart":
        if p.get("title"):
            out.append(f"{pad}{p['title']}")
        vals = [float(v) for v in p["values"]] or [1]
        top = max(vals) or 1
        for label, v in zip(p["labels"], vals):
            out.append(f"{pad}{str(label):>8} {BAR * max(1, round(28 * v / top))} {v:,.0f}")
    elif t == "Table":
        cols = [str(c) for c in p["columns"]]
        rows = [[str(c) for c in r] for r in p["rows"]]
        w = [max(len(x) for x in [c] + [r[i] for r in rows if i < len(r)]) for i, c in enumerate(cols)]
        out.append(pad + " | ".join(c.ljust(w[i]) for i, c in enumerate(cols)))
        out.append(pad + "-+-".join("-" * x for x in w))
        for r in rows:
            out.append(pad + " | ".join(c.ljust(w[i]) for i, c in enumerate(r)))
    elif t == "Button":
        out.append(f"{pad}[ {p['label']} ]  -> action:{p['action']} {p.get('params') or ''}".rstrip())
    elif t == "HtmlView":
        out.append(f"{pad}<HtmlView '{p.get('title', 'generated view')}': {len(p['html'])} bytes, "
                   "runs only in a sandboxed browser frame>")
    return out
