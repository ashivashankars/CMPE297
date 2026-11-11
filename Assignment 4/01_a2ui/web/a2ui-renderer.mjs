// A2UI renderer (browser). Mirrors a2ui.py: keep surfaces, apply envelopes in
// order, resolve {"path"} bindings against each surface's data model, convert
// the flat component map into the shared normalized tree, and paint it.

import { paint } from "/common/components.mjs";

const tokens = (p) => (p === "/" || p === "" ? [] : p.split("/").slice(1).map((t) => t.replace(/~1/g, "/").replace(/~0/g, "~")));
export function getPointer(doc, p) { return tokens(p).reduce((d, t) => (d == null ? undefined : d[t]), doc); }
export function setPointer(doc, p, value) {
  const t = tokens(p);
  if (!t.length) return value;
  let cur = doc;
  for (const k of t.slice(0, -1)) cur = cur[k] ??= {};
  cur[t.at(-1)] = value;
  return doc;
}

const STRUCTURAL = new Set(["id", "component", "child", "children", "weight", "action"]);

export class Surface {
  constructor(id, catalogId) { this.id = id; this.catalogId = catalogId; this.components = new Map(); this.data = {}; }
  resolve(v) {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      const keys = Object.keys(v);
      if (keys.length === 1 && keys[0] === "path") return getPointer(this.data, v.path);
      return Object.fromEntries(keys.map((k) => [k, this.resolve(v[k])]));
    }
    return Array.isArray(v) ? v.map((x) => this.resolve(x)) : v;
  }
  tree(id = "root", seen = new Set()) {
    const c = this.components.get(id);
    if (!c) return { pending: id };          // referenced, not yet streamed: draw a skeleton
    if (seen.has(id)) return { type: "Text", props: { text: `cycle at ${id}` } };
    seen = new Set(seen).add(id);
    if (c.component === "Button") {
      const event = c.action?.event ?? {};
      return { id, type: "Button", children: [],
        props: { label: this.resolve(this.components.get(c.child)?.text ?? "…"), action: event.name, params: this.resolve(event.context ?? {}) } };
    }
    const props = Object.fromEntries(Object.entries(c).filter(([k]) => !STRUCTURAL.has(k)).map(([k, v]) => [k, this.resolve(v)]));
    const kids = c.children ?? (c.child ? [c.child] : []);
    return { id, type: c.component, props, children: kids.map((k) => this.tree(k, seen)) };
  }
}

export function createRenderer(container, ctx) {
  let surfaces = new Map();
  const draw = () => {
    container.replaceChildren();
    for (const s of surfaces.values()) {
      const box = document.createElement("div");
      box.className = "a2ui-surface";
      box.dataset.surface = s.id;
      const tag = document.createElement("div");
      tag.className = "surface-tag";
      tag.textContent = `surface: ${s.id} · ${s.components.size} components · data keys: ${Object.keys(s.data).join(", ") || "–"}`;
      const body = document.createElement("div");
      box.append(tag, body);
      container.append(box);
      paint(body, s.tree(), {
        onAction: (name, context, sourceComponentId) => ctx.action({
          version: "v0.9.1",
          action: { name, surfaceId: s.id, sourceComponentId: sourceComponentId ?? "html", context },
        }),
      });
    }
  };
  return {
    reset() { surfaces = new Map(); container.replaceChildren(); },
    onMessage(m) {
      if (m.createSurface) surfaces.set(m.createSurface.surfaceId, new Surface(m.createSurface.surfaceId, m.createSurface.catalogId));
      else if (m.updateComponents) { const s = surfaces.get(m.updateComponents.surfaceId); m.updateComponents.components.forEach((c) => s.components.set(c.id, c)); }
      else if (m.updateDataModel) { const s = surfaces.get(m.updateDataModel.surfaceId); s.data = setPointer(s.data, m.updateDataModel.path, m.updateDataModel.value); }
      else if (m.deleteSurface) surfaces.delete(m.deleteSurface.surfaceId);
      draw();
    },
  };
}

export const label = (m) => {
  const k = ["createSurface", "updateComponents", "updateDataModel", "deleteSurface", "action"].find((x) => x in m);
  return `${k}(${m[k]?.surfaceId ?? ""})${k === "action" ? " " + m.action.name : ""}`;
};
