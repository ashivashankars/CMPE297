// The registry half of the catalog (common/catalog.py is the validator half).
// One function per component type; the names match the catalog exactly.
// Every codelab converts its own format into the normalized tree
//     { type, props, children: [...] }
// and calls renderTree(). Nothing here evaluates model text as code.

import { mountHtml } from "./sandbox.mjs";

export const ALLOWED_ACTIONS = ["drill_region", "refresh", "export_csv", "setState"];

const h = (tag, cls, text) => {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined && text !== null) el.textContent = String(text);
  return el;
};

const REGISTRY = {
  Column: (p, kids) => { const el = h("div", "c-column"); el.append(...kids()); return el; },
  Row: (p, kids) => { const el = h("div", "c-row"); el.append(...kids()); return el; },
  Card: (p, kids) => {
    const el = h("section", "c-card");
    if (p.title) el.append(h("h3", "c-card-title", p.title));
    if (p.subtitle) el.append(h("div", "c-card-sub", p.subtitle));
    el.append(...kids());
    return el;
  },
  Heading: (p) => h("h2", "c-heading", p.text),
  Text: (p) => h("p", `c-text ${p.tone === "muted" ? "muted" : ""}`, p.text),
  Metric: (p) => {
    const el = h("div", "c-metric");
    el.append(h("div", "c-metric-label", p.label), h("div", "c-metric-value", p.value));
    if (p.delta) el.append(h("div", `c-metric-delta ${String(p.delta).startsWith("-") ? "down" : "up"}`, p.delta));
    return el;
  },
  Badge: (p) => h("span", `c-badge ${p.tone || "info"}`, p.text),
  BarChart: (p) => {
    const el = h("figure", "c-bars");
    if (p.title) el.append(h("figcaption", "", p.title));
    const values = (p.values || []).map(Number);
    const top = Math.max(...values, 1);
    (p.labels || []).forEach((label, i) => {
      const row = h("div", "c-bar-row");
      const bar = h("div", "c-bar");
      bar.style.width = `${(100 * (values[i] || 0)) / top}%`;
      const track = h("div", "c-bar-track");
      track.append(bar);
      row.append(h("span", "c-bar-label", label), track, h("span", "c-bar-value", (values[i] || 0).toLocaleString()));
      el.append(row);
    });
    return el;
  },
  Table: (p) => {
    const table = h("table", "c-table");
    const head = h("tr");
    (p.columns || []).forEach((c) => head.append(h("th", "", c)));
    table.append(head);
    (p.rows || []).forEach((r) => {
      const tr = h("tr");
      r.forEach((c) => tr.append(h("td", "", typeof c === "number" ? c.toLocaleString() : c)));
      table.append(tr);
    });
    return table;
  },
  Button: (p, _kids, ctx) => {
    const b = h("button", "c-button", p.label);
    b.onclick = () => ctx.onAction?.(p.action, p.params || {}, ctx.id);
    return b;
  },
  HtmlView: (p, _kids, ctx) => {
    const holder = h("div", "c-htmlholder");
    mountHtml(holder, p.html, { title: p.title, onAction: ctx.onAction, allowedActions: ALLOWED_ACTIONS });
    return holder;
  },
};

export function renderTree(node, ctx = {}) {
  if (!node) return h("div", "c-empty", "…");
  if (node.pending) return h("div", "c-skeleton", `loading ${node.pending}…`);   // streaming placeholder
  const make = REGISTRY[node.type];
  if (!make) {
    const el = h("div", "c-error", `Unknown component "${node.type}" - not in the catalog, not rendered`);
    return el;
  }
  const kids = () => (node.children || []).map((c) => renderTree(c, ctx));
  const el = make(node.props || {}, kids, { ...ctx, id: node.id });
  el.dataset.type = node.type;
  if (node.id) el.dataset.id = node.id;
  return el;
}

/** Replace a container's content with a freshly rendered tree, disposing old sandboxes first. */
export function paint(container, tree, ctx) {
  container.querySelectorAll(".htmlview").forEach((w) => w.dispose?.());
  container.replaceChildren(renderTree(tree, ctx));
}
