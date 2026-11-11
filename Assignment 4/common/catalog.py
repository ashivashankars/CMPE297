"""The component catalog: the contract between the model and the page.

Every codelab speaks a different *format* (A2UI messages, AG-UI state, json-render
specs, OpenUI Lang, an MCP App view, a harness tool call) but all of them end up
drawing the same small design system. Each format is converted into one
"normalized tree" and checked here:

    {"type": "Card", "props": {"title": "..."}, "children": [ ...nodes... ]}

The catalog plays three roles at once:
  1. PROMPT     - catalog_prompt() tells the model what it may use;
  2. VALIDATOR  - validate() rejects anything outside the contract;
  3. REGISTRY   - common/web/components.mjs draws each type (same names).

Modes and the catalog:
  static       the model never sees this catalog; it picks a pre-built widget
  declarative  the model composes a tree from these components
  open-ended   the model writes HTML; only HtmlView is involved (sandboxed)
  mixed        catalog components + exactly the HtmlView regions it needs
"""

STR, NUM, LIST, BOOL = "string", "number", "array", "boolean"

# type -> {prop: (type, required)}, plus whether it accepts children
CATALOG = {
    "Column":  {"props": {"gap": (STR, False)}, "children": True,
                "doc": "Stacks children vertically."},
    "Row":     {"props": {"gap": (STR, False)}, "children": True,
                "doc": "Places children side by side (wraps on small screens)."},
    "Card":    {"props": {"title": (STR, False), "subtitle": (STR, False)}, "children": True,
                "doc": "A bordered box with an optional title."},
    "Heading": {"props": {"text": (STR, True)}, "children": False, "doc": "A section heading."},
    "Text":    {"props": {"text": (STR, True), "tone": (STR, False)}, "children": False,
                "doc": "A paragraph. tone: default | muted."},
    "Metric":  {"props": {"label": (STR, True), "value": (STR, True), "delta": (STR, False)}, "children": False,
                "doc": "One KPI number with a label and an optional change like +12%."},
    "BarChart": {"props": {"title": (STR, False), "labels": (LIST, True), "values": (LIST, True)}, "children": False,
                 "doc": "A horizontal bar chart; labels and values have the same length."},
    "Table":   {"props": {"columns": (LIST, True), "rows": (LIST, True)}, "children": False,
                "doc": "Column headers and rows of cells."},
    "Badge":   {"props": {"text": (STR, True), "tone": (STR, False)}, "children": False,
                "doc": "A small status pill. tone: info | success | warning."},
    "Button":  {"props": {"label": (STR, True), "action": (STR, True), "params": ("object", False)}, "children": False,
                "doc": "Sends a NAMED action back to the app. It never runs code."},
    "HtmlView": {"props": {"title": (STR, False), "html": (STR, True)}, "children": False,
                 "doc": "ESCAPE HATCH: a self-contained HTML document run in a sandboxed iframe."},
}

# The only actions a Button may name. The app decides what an action does.
ALLOWED_ACTIONS = {"drill_region", "refresh", "export_csv", "setState"}  # setState: client-local (json-render built-in)

_PY = {STR: (str, int, float), NUM: (int, float), LIST: (list,), BOOL: (bool,), "object": (dict,)}


class CatalogError(ValueError):
    """A validation failure. Its message is written for the model: it is sent back as feedback."""


def validate(node, *, allow_html=True, path="root", max_depth=12, _depth=0, _html=None):
    """Check a normalized tree. Returns the number of HtmlView regions it contains."""
    _html = _html if _html is not None else [0]
    if _depth > max_depth:
        raise CatalogError(f"{path}: tree deeper than {max_depth}")
    if not isinstance(node, dict) or "type" not in node:
        raise CatalogError(f"{path}: expected an object with a 'type'")
    kind = node["type"]
    spec = CATALOG.get(kind)
    if spec is None:
        raise CatalogError(f"{path}: unknown component {kind!r}. Allowed: {', '.join(CATALOG)}")
    if kind == "HtmlView":
        if not allow_html:
            raise CatalogError(f"{path}: HtmlView is not allowed in this mode")
        _html[0] += 1
    props = node.get("props") or {}
    for name, value in props.items():
        if name not in spec["props"]:
            raise CatalogError(f"{path} ({kind}): unknown prop {name!r}. Allowed: {', '.join(spec['props']) or 'none'}")
        want = spec["props"][name][0]
        if value is not None and not isinstance(value, _PY[want]):
            raise CatalogError(f"{path} ({kind}).{name}: expected {want}, got {type(value).__name__}")
    for name, (_, required) in spec["props"].items():
        if required and props.get(name) in (None, ""):
            raise CatalogError(f"{path} ({kind}): missing required prop {name!r}")
    if kind == "BarChart" and len(props["labels"]) != len(props["values"]):
        raise CatalogError(f"{path} (BarChart): labels and values differ in length")
    if kind == "Button" and props["action"] not in ALLOWED_ACTIONS:
        raise CatalogError(f"{path} (Button): action {props['action']!r} is not allowed. Allowed: {sorted(ALLOWED_ACTIONS)}")
    children = node.get("children") or []
    if children and not spec["children"]:
        raise CatalogError(f"{path} ({kind}): does not take children")
    for i, child in enumerate(children):
        validate(child, allow_html=allow_html, path=f"{path}.children[{i}]", _depth=_depth + 1, _html=_html)
    return _html[0]


def catalog_prompt(include_html=False):
    """The catalog as prompt text: one line per component."""
    lines = []
    for kind, spec in CATALOG.items():
        if kind == "HtmlView" and not include_html:
            continue
        props = ", ".join(f"{n}{'' if req else '?'}: {t}" for n, (t, req) in spec["props"].items())
        kids = " [children]" if spec["children"] else ""
        lines.append(f"- {kind}({props}){kids} - {spec['doc']}")
    lines.append(f"Button actions allowed: {', '.join(sorted(ALLOWED_ACTIONS))}")
    return "\n".join(lines)


def count(node):
    """Number of nodes in a tree (used in logs and tests)."""
    return 1 + sum(count(c) for c in node.get("children") or [])
