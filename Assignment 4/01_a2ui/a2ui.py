"""A2UI v0.9 by hand: the four server->client envelopes, one client->server
action, JSON Pointer data binding, and the Surface a renderer keeps.

A2UI separates STRUCTURE from DATA:
    createSurface     open a surface and name the catalog it uses
    updateComponents  a FLAT list of components that refer to each other by id
    updateDataModel   JSON values at a JSON Pointer path; components bind to them
    deleteSurface     drop the surface

A prop written as {"path": "/summary/revenue"} is a binding: the renderer reads
the data model at that pointer. So the model (or your app) can change numbers
with a tiny updateDataModel and never resend the layout.

This module is the Python mirror of web/a2ui-renderer.mjs; the CLI and the
tests use it, the browser uses the JS copy.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.catalog import CatalogError, validate  # noqa: E402

VERSION = "v0.9.1"
CATALOG_ID = "https://github.com/ashivashankars/CMPE297/a2ui/catalogs/sales/v1"
KINDS = ("createSurface", "updateComponents", "updateDataModel", "deleteSurface")
STRUCTURAL = {"id", "component", "child", "children", "weight", "action"}


# ------------------------------------------------------------ envelopes

def create_surface(surface_id):
    return {"version": VERSION, "createSurface": {"surfaceId": surface_id, "catalogId": CATALOG_ID}}


def update_components(surface_id, components):
    return {"version": VERSION, "updateComponents": {"surfaceId": surface_id, "components": components}}


def update_data_model(surface_id, path, value):
    return {"version": VERSION, "updateDataModel": {"surfaceId": surface_id, "path": path, "value": value}}


def delete_surface(surface_id):
    return {"version": VERSION, "deleteSurface": {"surfaceId": surface_id}}


def kind_of(message):
    found = [k for k in KINDS if k in message]
    return found[0] if len(found) == 1 else None


def check_envelope(message):
    """The envelope rules, written as model-readable errors."""
    if not isinstance(message, dict):
        raise CatalogError("each line must be one JSON object")
    if message.get("version") != VERSION:
        raise CatalogError(f"version must be {VERSION!r}")
    kind = kind_of(message)
    if kind is None:
        raise CatalogError(f"a message carries exactly one of {KINDS}")
    body = message[kind]
    if not isinstance(body, dict) or not isinstance(body.get("surfaceId"), str):
        raise CatalogError(f"{kind}: surfaceId (string) is required")
    if kind == "updateComponents":
        comps = body.get("components")
        if not isinstance(comps, list) or not all(isinstance(c, dict) and "id" in c and "component" in c for c in comps):
            raise CatalogError("updateComponents: components is a list of {id, component, ...}")
    if kind == "updateDataModel" and not str(body.get("path", "")).startswith("/"):
        raise CatalogError("updateDataModel: path must be a JSON Pointer starting with '/'")
    return kind


# ------------------------------------------------------------ JSON Pointer

def _tokens(pointer):
    return [t.replace("~1", "/").replace("~0", "~") for t in pointer.split("/")[1:]] if pointer not in ("", "/") else []


def get_pointer(doc, pointer):
    for t in _tokens(pointer):
        if isinstance(doc, list):
            t = int(t)
            if t >= len(doc):
                return None
            doc = doc[t]
        elif isinstance(doc, dict):
            doc = doc.get(t)
        else:
            return None
    return doc


def set_pointer(doc, pointer, value):
    tokens = _tokens(pointer)
    if not tokens:
        return value
    cur = doc
    for t in tokens[:-1]:
        cur = cur.setdefault(t, {})
    cur[tokens[-1]] = value
    return doc


# ------------------------------------------------------------ the surface

class Surface:
    def __init__(self, surface_id, catalog_id):
        self.id, self.catalog_id = surface_id, catalog_id
        self.components = {}   # id -> component (flat map: later updates replace by id)
        self.data = {}

    def resolve(self, value):
        """A {"path": ...} binding reads the data model; everything else is literal."""
        if isinstance(value, dict) and set(value) == {"path"}:
            return get_pointer(self.data, value["path"])
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        return value

    def tree(self, comp_id="root", _seen=None):
        """Flat components + data model -> the normalized tree the catalog validates."""
        _seen = _seen or set()
        comp = self.components.get(comp_id)
        if comp is None:
            return {"pending": comp_id}          # referenced before it arrived: still streaming
        if comp_id in _seen:
            raise CatalogError(f"component {comp_id!r} is its own ancestor")
        _seen = _seen | {comp_id}
        kind = comp["component"]
        props = {k: self.resolve(v) for k, v in comp.items() if k not in STRUCTURAL}
        kids = comp.get("children") or ([comp["child"]] if comp.get("child") and kind != "Button" else [])
        if kind == "Button":   # A2UI: a Button's label is a child Text; its action is an event
            label = self.components.get(comp.get("child"), {}).get("text", "…")
            event = (comp.get("action") or {}).get("event", {})
            props = {"label": self.resolve(label), "action": event.get("name", ""), "params": self.resolve(event.get("context", {}))}
            kids = []
        return {"id": comp_id, "type": kind, "props": props, "children": [self.tree(k, _seen) for k in kids]}


class Client:
    """What a renderer does with the stream: keep surfaces, apply messages in order."""

    def __init__(self):
        self.surfaces = {}

    def apply(self, message):
        kind = check_envelope(message)
        body = message[kind]
        sid = body["surfaceId"]
        if kind == "createSurface":
            self.surfaces[sid] = Surface(sid, body["catalogId"])
            return kind
        surface = self.surfaces.get(sid)
        if surface is None:
            raise CatalogError(f"{kind}: surface {sid!r} does not exist yet; send createSurface first")
        if kind == "updateComponents":
            for c in body["components"]:
                surface.components[c["id"]] = c
        elif kind == "updateDataModel":
            surface.data = set_pointer(surface.data, body["path"], body.get("value"))
        elif kind == "deleteSurface":
            del self.surfaces[sid]
        return kind

    def validate_all(self, allow_html=True):
        for s in self.surfaces.values():
            validate(_no_pending(s.tree()), allow_html=allow_html, path=s.id)


def _no_pending(node):
    if "pending" in node:
        raise CatalogError(f"component {node['pending']!r} is referenced but never defined")
    for c in node.get("children", []):
        _no_pending(c)
    return node


def parse_jsonl(text):
    """Complete lines -> messages; the trailing partial line stays for the next chunk."""
    *lines, rest = text.split("\n")
    return [json.loads(l) for l in lines if l.strip()], rest


def action_message(name, surface_id, source_id, context):
    """client -> server: what a Button click sends."""
    return {"version": VERSION, "action": {"name": name, "surfaceId": surface_id,
                                            "sourceComponentId": source_id, "context": context}}
