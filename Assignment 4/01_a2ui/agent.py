"""The A2UI agent: one generator per mode, plus the action handler.

    static       the model picks a PRE-BUILT surface template and fills its data;
                 our code owns every component (TEMPLATES below).
    declarative  the model writes A2UI JSONL itself: createSurface, updateComponents,
                 updateDataModel - using only catalog components.
    open_ended   the model writes one HtmlView component whose html runs in a sandbox.
                 (A2UI itself never ships code; HtmlView is a custom-catalog escape hatch.)
    mixed        catalog components AND one HtmlView region on the same surface.

Every message the model writes is checked (envelope + catalog) before it is
forwarded to the page. A bad message becomes an {"error": ...} the page shows,
and - with a live model - feedback for one retry.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from common import data, llm  # noqa: E402
from common.catalog import ALLOWED_ACTIONS, CatalogError, catalog_prompt, validate  # noqa: E402
from common.html_policy import PolicyError, check_html  # noqa: E402

import a2ui  # noqa: E402

FIX = HERE / "fixtures"

# ------------------------------------------------------------ static: templates we own

def _metric(cid, label, path, delta=None):
    c = {"id": cid, "component": "Metric", "label": label, "value": {"path": path}}
    if delta:
        c["delta"] = {"path": delta}
    return c


TEMPLATES = {
    "sales_overview": [
        {"id": "root", "component": "Card", "title": {"path": "/title"}, "children": ["kpis", "chart", "more"]},
        {"id": "kpis", "component": "Row", "children": ["m_rev", "m_orders", "m_ticket"]},
        _metric("m_rev", "Revenue", "/revenue", "/growth"),
        _metric("m_orders", "Orders", "/orders"),
        _metric("m_ticket", "Avg ticket", "/avg_ticket"),
        {"id": "chart", "component": "BarChart", "title": "Revenue by region",
         "labels": {"path": "/labels"}, "values": {"path": "/values"}},
        {"id": "more_label", "component": "Text", "text": "Drill into top region"},
        {"id": "more", "component": "Button", "child": "more_label",
         "action": {"event": {"name": "drill_region", "context": {"region": {"path": "/labels/0"}}}}},
    ],
    "region_detail": [
        {"id": "root", "component": "Card", "title": {"path": "/heading"}, "children": ["total", "months"]},
        _metric("total", "Quarter total", "/total"),
        {"id": "months", "component": "BarChart", "title": "Monthly revenue",
         "labels": {"path": "/months"}, "values": {"path": "/revenue"}},
    ],
}
WIDGET_ARGS = {"sales_overview": {"title", "revenue", "growth", "orders", "avg_ticket", "labels", "values"}}

SYSTEMS = {
    "static": (
        "You choose a pre-built widget; you never design layout.\n"
        "Widgets: sales_overview(title, revenue, growth, orders, avg_ticket, labels[], values[])\n"
        'Reply with ONE JSON object: {"widget": name, "args": {...}}. Format money like $4.20M.'),
    "declarative": (
        f"You write A2UI {a2ui.VERSION} messages as JSONL (one JSON object per line), nothing else.\n"
        "Order: createSurface, then updateComponents (flat list, one component has id 'root',\n"
        "children are referenced by id), then updateDataModel. Bind data with {\"path\": \"/pointer\"}.\n"
        f"catalogId: {a2ui.CATALOG_ID}\nComponents (props are flat keys on the component):\n"
        + catalog_prompt() +
        "\nA Button is {component:'Button', child:<Text id>, action:{event:{name, context}}}."),
}
HTML_RULE = ("HtmlView(title, html) runs a complete, self-contained HTML document in a sandboxed iframe: "
             "no network, no external files. To send an action call window.genui.action(name, params).")
SYSTEMS["open_ended"] = SYSTEMS["declarative"].split("Components (")[0] + (
    "Use exactly ONE component, with id 'root': " + HTML_RULE)
SYSTEMS["mixed"] = SYSTEMS["declarative"] + "\n- " + HTML_RULE + (
    "\nUse catalog components for everything they can show; add ONE HtmlView only for what they cannot "
    "(e.g. an interactive what-if slider).")


def user_prompt(prompt):
    return f"{prompt}\n\nData (JSON):\n{json.dumps(data.summary())}"


class Part:
    name = "A2UI · Agent-to-User Interface"
    web_dir = HERE / "web"
    default_prompt = "Show me Q3 sales by region"

    # ------------------------------------------------ runs
    def run(self, mode, prompt):
        yield {"__meta": {"backend": llm.backend(), "mode": mode}}
        if mode == "static":
            yield from self._static(prompt)
        else:
            yield from self._stream_jsonl(SYSTEMS[mode], user_prompt(prompt), FIX / f"{mode}.jsonl",
                                          allow_html=mode != "declarative", require_html=mode != "declarative")

    def _static(self, prompt):
        reply = json.loads(llm.strip_fences(llm.complete(SYSTEMS["static"], user_prompt(prompt), FIX / "static.json")))
        widget, args = reply.get("widget"), reply.get("args", {})
        if widget not in WIDGET_ARGS:
            yield {"error": f"unknown widget {widget!r}"}
            return
        missing = WIDGET_ARGS[widget] - set(args)
        if missing:
            yield {"error": f"{widget}: missing args {sorted(missing)}"}
            return
        # The model chose; our code builds every message. The template never comes from the model.
        yield a2ui.create_surface("sales")
        yield a2ui.update_components("sales", TEMPLATES[widget])
        yield a2ui.update_data_model("sales", "/", args)

    def _stream_jsonl(self, system, user, fixture, *, allow_html, require_html=False, client=None, final_check=True):
        """Forward each complete JSONL line as soon as it validates."""
        client = client or a2ui.Client()
        buffer = ""
        for chunk in llm.stream_text(system, user, fixture):
            messages, buffer = a2ui.parse_jsonl(buffer + chunk)
            for msg in messages:
                try:
                    client.apply(msg)
                    self._check_components(msg, allow_html)
                except (CatalogError, PolicyError) as e:
                    yield {"error": f"rejected message: {e}"}
                    continue
                yield msg
        if buffer.strip():
            messages, _ = a2ui.parse_jsonl(buffer + "\n")
            for msg in messages:
                client.apply(msg)
                yield msg
        if not final_check:
            return
        try:   # whole-surface check once the stream is complete
            client.validate_all(allow_html=allow_html)
            if require_html and not any('"HtmlView"' in json.dumps(s.components) for s in client.surfaces.values()):
                raise CatalogError("this mode requires an HtmlView region")
        except CatalogError as e:
            yield {"error": f"surface invalid: {e}"}

    @staticmethod
    def _check_components(msg, allow_html):
        for comp in msg.get("updateComponents", {}).get("components", []):
            if comp["component"] == "HtmlView":
                if not allow_html:
                    raise CatalogError("HtmlView is not allowed in declarative mode")
                check_html(comp.get("html", ""))

    # ------------------------------------------------ actions
    def action(self, mode, body):
        act = body.get("action") or {}
        name, context = act.get("name"), act.get("context") or {}
        if name not in ALLOWED_ACTIONS:
            yield {"error": f"action {name!r} not allowed"}
            return
        if name != "drill_region":
            yield {"error": f"{name}: not implemented in this demo"}
            return
        try:
            detail = data.region_detail(context.get("region", ""))
        except KeyError as e:
            yield {"error": str(e)}
            return
        model = {"heading": f"{detail['region']} · monthly detail", "region": detail["region"],
                 "months": detail["months"], "revenue": detail["revenue"], "total": data.money(detail["total"])}
        yield {"__meta": {"backend": llm.backend() if mode != "static" else "app code (no model)", "mode": mode}}
        if mode == "static":
            yield a2ui.create_surface("detail")
            yield a2ui.update_components("detail", TEMPLATES["region_detail"])
        else:
            # The model designs the detail surface (structure only, bound to paths)...
            client = a2ui.Client()
            yield from self._stream_jsonl(SYSTEMS["declarative"],
                                          f"User clicked drill_region for {detail['region']}. Design a 'detail' surface "
                                          "bound to /heading, /total, /months, /revenue. Do not send data.",
                                          FIX / "action.jsonl", allow_html=False,
                                          client=client, final_check=False)
            client.apply(a2ui.update_data_model("detail", "/", model))
            try:
                client.validate_all()
            except CatalogError as e:
                yield {"error": f"detail surface invalid: {e}"}
                return
        # ...and the APP supplies the data. Structure and data travel separately.
        yield a2ui.update_data_model("detail", "/", model)


PART = Part()

if __name__ == "__main__":
    from common.server import serve
    serve(PART, int(sys.argv[1]) if len(sys.argv) > 1 else 8001)
