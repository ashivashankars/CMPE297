"""json-render by hand: a flat spec, streamed as JSON Patch, resolved against state.

A json-render spec (vercel-labs/json-render) is

    {"root": "main",
     "elements": {"main": {"type": "Card", "props": {...}, "children": ["kpis", ...]}, ...},
     "state": {...}}

- elements is a FLAT map, so a model can stream it as RFC 6902 patches
  (one line = one element) and the page can paint after the first few lines;
- props may be dynamic: {"$state": "/kpi/revenue"} reads state;
- "visible": {"$state": "/showTable", "eq": true} hides an element;
- "repeat": {"statePath": "/regions"} renders children once per array item,
  and {"$item": "name"} reads a field of the current item;
- "on": {"press": {"action": name, "params": {...}}} binds an event to a NAMED action.
  setState is built in and runs on the client; other actions go to the server.

The same spec feeds two renderers: web/jr-renderer.mjs and the terminal.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import data  # noqa: E402
from common.catalog import CATALOG, CatalogError  # noqa: E402

# A custom registry component for STATIC mode: written by us, a single element for the model.
STATIC_COMPONENTS = {"SalesOverview": {"title", "revenue", "growth", "regions"}}
TOP_LEVEL = ("/root", "/elements/", "/state")


def get_ptr(doc, pointer):
    for t in [p for p in pointer.split("/")[1:] if p != ""]:
        if isinstance(doc, list):
            doc = doc[int(t)] if t.isdigit() and int(t) < len(doc) else None
        elif isinstance(doc, dict):
            doc = doc.get(t)
        else:
            return None
    return doc


def check_op(op):
    """Per-line checks while streaming: allowed paths, known types, known props."""
    if op.get("op") not in ("add", "replace", "remove"):
        raise CatalogError(f"op must be add/replace/remove, got {op.get('op')!r}")
    path = op.get("path", "")
    if not path.startswith(TOP_LEVEL):
        raise CatalogError(f"path {path!r} must start with /root, /elements/ or /state")
    if path.startswith("/elements/") and path.count("/") == 2 and op["op"] != "remove":
        el = op.get("value") or {}
        kind = el.get("type")
        if kind in STATIC_COMPONENTS:
            return
        if kind not in CATALOG:
            raise CatalogError(f"element {path}: unknown type {kind!r}")
        unknown = set(el.get("props") or {}) - set(CATALOG[kind]["props"])
        if unknown:
            raise CatalogError(f"element {path}: unknown props {sorted(unknown)} for {kind}")
        if "action" in (el.get("props") or {}):
            raise CatalogError(f"element {path}: put actions in the element's 'on' field, not in props")


def resolve(value, state, item=None):
    if isinstance(value, dict):
        if set(value) == {"$state"}:
            return get_ptr(state, value["$state"])
        if set(value) == {"$item"}:
            return (item or {}).get(value["$item"])
        return {k: resolve(v, state, item) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, state, item) for v in value]
    return value


def visible(cond, state, item=None):
    if cond is None:
        return True
    actual = get_ptr(state, cond["$state"]) if "$state" in cond else (item or {}).get(cond.get("$item"))
    return actual == cond["eq"] if "eq" in cond else bool(actual)


def expand_static(kind, p):
    """What the registry's SalesOverview draws: a fixed layout, the model only filled props."""
    top = p["regions"][0]["name"]
    return {"type": "Card", "props": {"title": f"{p['title']} (pre-built SalesOverview)"}, "children": [
        {"type": "Row", "props": {}, "children": [
            {"type": "Metric", "props": {"label": "Revenue", "value": p["revenue"], "delta": p["growth"]}},
            {"type": "Metric", "props": {"label": "Top region", "value": top}}]},
        {"type": "BarChart", "props": {"labels": [r["name"] for r in p["regions"]], "values": [r["revenue"] for r in p["regions"]]}},
        {"type": "Button", "props": {"label": f"Drill into {top}", "action": "drill_region", "params": {"region": top}}}]}


def to_tree(spec, el_id=None, item=None, depth=0):
    """Spec + state -> the normalized tree (visible filtering, repeat expansion, $state resolution)."""
    state = spec.get("state", {})
    el_id = el_id or spec.get("root")
    el = spec.get("elements", {}).get(el_id)
    if el is None:
        return {"pending": el_id}
    if depth > 20:
        raise CatalogError("spec nests too deep (cycle?)")
    props = resolve(el.get("props") or {}, state, item)
    if el["type"] in STATIC_COMPONENTS:
        return expand_static(el["type"], props)
    press = (el.get("on") or {}).get("press")
    if el["type"] == "Button" and press:
        props = {**props, "action": press["action"], "params": resolve(press.get("params") or {}, state, item)}
    children = []
    rep = el.get("repeat")
    items = get_ptr(state, rep["statePath"]) or [] if rep else [item]
    for it in items:
        for cid in el.get("children") or []:
            child = spec["elements"].get(cid)
            if child is not None and not visible(child.get("visible"), state, it):
                continue
            children.append(to_tree(spec, cid, it, depth + 1))
    return {"id": el_id, "type": el["type"], "props": props, "children": children}


def detail_patches(region, old_root):
    """The SERVER's answer to drill_region: patches on the same spec (app code, not the model).
    A new Column becomes the root and holds the old root plus the detail card."""
    d = data.region_detail(region)
    return [
        {"op": "add", "path": "/state/detail", "value": {"title": f"{d['region']} · monthly detail",
                                                         "total": data.money(d["total"]), "months": d["months"], "revenue": d["revenue"]}},
        {"op": "add", "path": "/elements/detail", "value": {"type": "Card", "props": {"title": {"$state": "/detail/title"}},
                                                            "children": ["detail-row"]}},
        {"op": "add", "path": "/elements/detail-row", "value": {"type": "Row", "props": {}, "children": ["detail-total", "detail-bars"]}},
        {"op": "add", "path": "/elements/detail-total", "value": {"type": "Metric", "props": {"label": "Quarter total", "value": {"$state": "/detail/total"}}}},
        {"op": "add", "path": "/elements/detail-bars", "value": {"type": "BarChart", "props": {"title": "By month",
                                                                 "labels": {"$state": "/detail/months"}, "values": {"$state": "/detail/revenue"}}}},
        {"op": "add", "path": "/elements/page", "value": {"type": "Column", "props": {}, "children": [old_root, "detail"]}},
        {"op": "replace", "path": "/root", "value": "page"},
    ] if old_root != "page" else [  # already drilled once: just swap the detail data
        {"op": "replace", "path": "/state/detail", "value": {"title": f"{d['region']} · monthly detail",
                                                             "total": data.money(d["total"]), "months": d["months"], "revenue": d["revenue"]}}]
