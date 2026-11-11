"""The json-render agent: the model streams JSONL patches that build one spec.

    static       one element of the registry's custom type SalesOverview (we built its layout)
    declarative  the full flat element map + state, streamed patch by patch
    open_ended   one HtmlView element (model-written HTML in a sandbox)
    mixed        catalog elements + one HtmlView element

Each patch line is checked (paths, types, props) before it is forwarded; the
complete spec is checked once more as a resolved tree. User actions:
setState runs on the client; drill_region comes here and is answered with
more patches on the same spec.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from common import data, llm  # noqa: E402
from common.catalog import CatalogError, catalog_prompt, validate  # noqa: E402
from common.html_policy import PolicyError, check_html  # noqa: E402
from common.json_patch import PatchError, apply_op  # noqa: E402

import jsonrender as jr  # noqa: E402

FIX = HERE / "fixtures"
FORMAT = """Output JSONL: one RFC 6902 JSON Patch op per line, nothing else. Build {root, elements, state}.
Start with {"op":"add","path":"/root","value":"main"}, then one line per element:
{"op":"add","path":"/elements/<id>","value":{"type":...,"props":{...},"children":[ids]}}
State: {"op":"add","path":"/state/<key>","value":...}; read it in props with {"$state":"/pointer"}.
Optional element fields: "visible": {"$state":"/x","eq":true}; "repeat": {"statePath":"/arr"} with {"$item":"field"};
"on": {"press": {"action": name, "params": {...}}} - setState(statePath, value) is built in."""
SYSTEMS = {
    "static": FORMAT + "\nUse ONE element of type SalesOverview(title, revenue, growth, regions:[{name, revenue}]).",
    "declarative": FORMAT + "\nComponents:\n" + catalog_prompt(),
    "open_ended": FORMAT + "\nUse ONE element of type HtmlView(title, html): a self-contained document; "
                  "window.genui.action(name, params) sends an action.",
    "mixed": FORMAT + "\nComponents:\n" + catalog_prompt(include_html=True) + "\nAdd ONE HtmlView only for what the catalog cannot do.",
}


def user_prompt(prompt):
    return f"{prompt}\n\nData (JSON):\n{json.dumps(data.summary())}"


def final_check(spec, mode):
    tree = jr.to_tree(spec)
    if mode == "static":
        if spec["elements"][spec["root"]]["type"] not in jr.STATIC_COMPONENTS:
            raise CatalogError("static mode: the root must be the pre-built SalesOverview")
    regions = validate(_no_pending(tree), allow_html=mode in ("open_ended", "mixed"))
    if mode in ("open_ended", "mixed") and regions < 1:
        raise CatalogError(f"{mode} mode expects an HtmlView element")
    for el in spec["elements"].values():
        if el["type"] == "HtmlView":
            check_html(el["props"]["html"])
    return tree


def _no_pending(n):
    if "pending" in n:
        raise CatalogError(f"element {n['pending']!r} is referenced but never defined")
    for c in n.get("children", []):
        _no_pending(c)
    return n


class Part:
    name = "json-render · flat specs streamed as JSON Patch"
    web_dir = HERE / "web"
    default_prompt = "Show me Q3 sales by region"
    pace = 0.06 if llm.backend() == "scripted" else 0

    def run(self, mode, prompt):
        yield {"__meta": {"backend": llm.backend(), "mode": mode}}
        spec, buffer = {"root": None, "elements": {}, "state": {}}, ""
        for chunk in llm.stream_text(SYSTEMS[mode], user_prompt(prompt), FIX / f"{mode}.jsonl", delay=0):
            buffer += chunk
            *lines, buffer = buffer.split("\n")
            for line in filter(str.strip, lines):
                yield from self._forward(json.loads(line), spec, mode)
        if buffer.strip():
            yield from self._forward(json.loads(buffer), spec, mode)
        try:
            final_check(spec, mode)
        except (CatalogError, PolicyError) as e:
            yield {"error": f"spec invalid: {e}"}

    def _forward(self, op, spec, mode):
        try:
            jr.check_op(op)
            if mode == "declarative" and isinstance(op.get("value"), dict) and op["value"].get("type") == "HtmlView":
                raise CatalogError("HtmlView is not allowed in declarative mode")
            apply_op(spec, op)
        except (CatalogError, PatchError, KeyError, IndexError) as e:
            yield {"error": f"rejected patch {op.get('path')}: {e}"}
            return
        yield op

    def action(self, mode, body):
        """body = {action, params, root}: answered with patches (app code, no model call)."""
        yield {"__meta": {"backend": "app code (no model)", "mode": mode}}
        if body.get("action") != "drill_region":
            yield {"error": f"server does not handle action {body.get('action')!r}"}
            return
        try:
            yield from jr.detail_patches(body.get("params", {}).get("region", ""), body.get("root", "main"))
        except KeyError as e:
            yield {"error": str(e)}


PART = Part()

if __name__ == "__main__":
    from common.server import serve
    serve(PART, int(sys.argv[1]) if len(sys.argv) > 1 else 8004)
