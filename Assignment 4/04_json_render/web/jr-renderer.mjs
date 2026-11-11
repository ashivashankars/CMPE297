// json-render in the browser: keep ONE spec {root, elements, state}, apply each
// streamed JSON Patch, resolve it into the normalized tree and paint.
// Mirrors jsonrender.py. setState actions are handled here (no server round trip);
// every other action is POSTed to the server, which answers with more patches.

import { paint } from "/common/components.mjs";
import { applyOp } from "/common/json-patch.mjs";

const getPtr = (doc, p) => p.split("/").slice(1).filter(Boolean).reduce((d, t) => (d == null ? undefined : d[t]), doc);

function resolve(v, state, item) {
  if (v && typeof v === "object" && !Array.isArray(v)) {
    const k = Object.keys(v);
    if (k.length === 1 && k[0] === "$state") return getPtr(state, v.$state);
    if (k.length === 1 && k[0] === "$item") return item?.[v.$item];
    return Object.fromEntries(k.map((x) => [x, resolve(v[x], state, item)]));
  }
  return Array.isArray(v) ? v.map((x) => resolve(x, state, item)) : v;
}
const visible = (c, state, item) => {
  if (!c) return true;
  const actual = "$state" in c ? getPtr(state, c.$state) : item?.[c.$item];
  return "eq" in c ? actual === c.eq : Boolean(actual);
};

// The registry's pre-built component for STATIC mode: we wrote this layout, the model fills props.
function SalesOverview(p) {
  const top = p.regions?.[0]?.name ?? "…";
  return { type: "Card", props: { title: `${p.title} (pre-built SalesOverview)` }, children: [
    { type: "Row", props: {}, children: [
      { type: "Metric", props: { label: "Revenue", value: p.revenue, delta: p.growth } },
      { type: "Metric", props: { label: "Top region", value: top } }] },
    { type: "BarChart", props: { labels: (p.regions ?? []).map((r) => r.name), values: (p.regions ?? []).map((r) => r.revenue) } },
    { type: "Button", props: { label: `Drill into ${top}`, action: "drill_region", params: { region: top } } }] };
}

export function toTree(spec, id = spec.root, item = undefined, depth = 0) {
  const el = spec.elements[id];
  if (!el || depth > 20) return { pending: id };
  let props = resolve(el.props ?? {}, spec.state, item);
  if (el.type === "SalesOverview") return SalesOverview(props);
  const press = el.on?.press;
  if (el.type === "Button" && press) props = { ...props, action: press.action, params: resolve(press.params ?? {}, spec.state, item) };
  const items = el.repeat ? getPtr(spec.state, el.repeat.statePath) ?? [] : [item];
  const children = [];
  for (const it of items) for (const cid of el.children ?? []) {
    const child = spec.elements[cid];
    if (child && !visible(child.visible, spec.state, it)) continue;
    children.push(toTree(spec, cid, it, depth + 1));
  }
  return { id, type: el.type, props, children };
}

export function createRenderer(container, ctx) {
  let spec;
  const draw = () => {
    if (!spec.root) return;
    paint(container, toTree(spec), {
      onAction(action, params) {
        if (action === "setState") {                   // built-in: client-local, no server call
          const op = { op: "add", path: `/state${params.statePath}`, value: params.value };
          ctx.log({ local: "setState", ...op }, "out");
          applyOp(spec, op);
          return draw();
        }
        ctx.action({ action, params, root: spec.root });
      },
    });
    const info = document.createElement("div");
    info.className = "jr-info";
    info.textContent = `spec: root=${spec.root} · ${Object.keys(spec.elements).length} elements · state keys: ${Object.keys(spec.state).join(", ") || "–"}`;
    container.prepend(info);
  };
  return {
    reset() { spec = { root: null, elements: {}, state: {} }; container.replaceChildren(); },
    onMessage(op) { applyOp(spec, op); draw(); },
  };
}

export const label = (m) => m.local ? `local setState ${m.path}` : m.action ? `action ${m.action} ${JSON.stringify(m.params)}` : `${m.op} ${m.path}`;
