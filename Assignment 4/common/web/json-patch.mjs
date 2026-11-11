// RFC 6902 JSON Patch for the browser (add / replace / remove / test). Mirrors common/json_patch.py.
const tokens = (p) => (p === "" ? [] : p.split("/").slice(1).map((t) => t.replace(/~1/g, "/").replace(/~0/g, "~")));
const clone = (v) => (v === undefined ? v : structuredClone(v));

export function applyOp(doc, op) {
  const t = tokens(op.path ?? "");
  if (!t.length) return clone(op.value);
  let parent = doc;
  for (const k of t.slice(0, -1)) parent = parent[Array.isArray(parent) ? Number(k) : k];
  const last = t.at(-1);
  if (Array.isArray(parent)) {
    const i = last === "-" ? parent.length : Number(last);
    if (op.op === "add") parent.splice(i, 0, clone(op.value));
    else if (op.op === "replace") parent[i] = clone(op.value);
    else if (op.op === "remove") parent.splice(i, 1);
  } else {
    if (op.op === "add" || op.op === "replace") parent[last] = clone(op.value);
    else if (op.op === "remove") delete parent[last];
  }
  return doc;
}
export const applyPatch = (doc, ops) => ops.reduce(applyOp, doc);
