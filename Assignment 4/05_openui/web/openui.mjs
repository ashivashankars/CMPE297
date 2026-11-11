// OpenUI Lang in the browser: tokenizer, parser, resolver. Mirrors openui.py.
// The renderer re-parses the WHOLE program after every streamed chunk; the last
// (cut-off) line is skipped and names not yet defined render as placeholders.

export const SIGNATURES = {
  Stack: ["Stack", ["children", "direction"]], Card: ["Card", ["title", "children"]],
  Heading: ["Heading", ["text"]], Text: ["Text", ["text", "tone"]],
  Metric: ["Metric", ["label", "value", "delta"]], BarChart: ["BarChart", ["title", "labels", "values"]],
  Table: ["Table", ["columns", "rows"]], Badge: ["Badge", ["text", "tone"]],
  Button: ["Button", ["label", "action", "params"]], HtmlArtifact: ["HtmlView", ["title", "html"]],
  SalesOverview: ["SalesOverview", ["title", "revenue", "growth", "labels", "values"]],
};

const TOKEN = /\s*(?:("(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?)|([A-Za-z_]\w*)|([\[\](){},:=]))/y;

export function tokenize(src) {
  const out = [];
  TOKEN.lastIndex = 0;
  while (TOKEN.lastIndex < src.length) {
    if (!src.slice(TOKEN.lastIndex).trim()) break;
    const m = TOKEN.exec(src);
    if (!m) throw new Error(`unexpected character ${src[TOKEN.lastIndex]}`);
    if (m[1]) out.push(["str", JSON.parse(m[1])]);
    else if (m[2]) out.push(["num", Number(m[2])]);
    else if (m[3]) out.push(["name", m[3]]);
    else out.push(["p", m[4]]);
  }
  return out;
}

function parseLine(toks) {
  let i = 0;
  const peek = () => toks[i] ?? [null, null];
  const eat = (v) => { const t = peek(); if (t[0] === null || (v !== undefined && t[1] !== v)) throw new Error(`expected ${v}`); i++; return t; };
  const list = (close) => { const items = []; while (peek()[1] !== close) { items.push(expr()); if (peek()[1] === ",") eat(","); } eat(close); return items; };
  function expr() {
    const [k, v] = peek();
    if (k === "str" || k === "num") { i++; return v; }
    if (k === "p" && v === "[") { eat("["); return list("]"); }
    if (k === "p" && v === "{") {
      eat("{"); const o = {};
      while (peek()[1] !== "}") { const key = eat()[1]; eat(":"); o[key] = expr(); if (peek()[1] === ",") eat(","); }
      eat("}"); return o;
    }
    if (k === "name") {
      i++;
      if (v === "true" || v === "false" || v === "null") return { true: true, false: false, null: null }[v];
      if (peek()[1] === "(") { eat("("); return { $call: v, args: list(")") }; }
      return { $ref: v };
    }
    throw new Error(`unexpected ${v}`);
  }
  const name = eat()[1]; eat("=");
  const e = expr();
  if (i !== toks.length) throw new Error("extra tokens");
  return [name, e];
}

export function parse(program, { partial = false } = {}) {
  let lines = program.split("\n");
  if (partial) lines = lines.slice(0, -1);
  const stmts = {};
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || line.startsWith("```")) continue;
    try { const [n, e] = parseLine(tokenize(line)); stmts[n] = e; }
    catch (err) { if (!partial) throw err; }
  }
  return stmts;
}

function toNode(kind, p) {
  if (kind === "Stack") return { type: p.direction === "row" ? "Row" : "Column", props: {}, children: p.children ?? [] };
  if (kind === "Card") return { type: "Card", props: { title: p.title }, children: p.children ?? [] };
  if (kind === "SalesOverview") {           // the pre-built library component (static mode)
    const top = p.labels?.[0] ?? "…";
    return { type: "Card", props: { title: `${p.title} (pre-built SalesOverview)` }, children: [
      { type: "Row", props: {}, children: [
        { type: "Metric", props: { label: "Revenue", value: p.revenue, delta: p.growth } },
        { type: "Metric", props: { label: "Top region", value: top } }] },
      { type: "BarChart", props: { labels: p.labels ?? [], values: p.values ?? [] } },
      { type: "Button", props: { label: `Drill into ${top}`, action: "drill_region", params: { region: top } } }] };
  }
  return { type: kind, props: Object.fromEntries(Object.entries(p).filter(([, v]) => v != null)), children: [] };
}

export function resolve(stmts, expr = undefined, seen = []) {
  if (expr === undefined) return "root" in stmts ? resolve(stmts, stmts.root, seen) : { pending: "root" };
  if (Array.isArray(expr)) return expr.map((e) => resolve(stmts, e, seen));
  if (expr && typeof expr === "object") {
    if ("$ref" in expr) {
      if (seen.includes(expr.$ref)) return { type: "Text", props: { text: `cycle at ${expr.$ref}` } };
      return expr.$ref in stmts ? resolve(stmts, stmts[expr.$ref], [...seen, expr.$ref]) : { pending: expr.$ref };
    }
    if ("$call" in expr) {
      const sig = SIGNATURES[expr.$call];
      if (!sig) return { type: "Unknown:" + expr.$call, props: {} };
      const props = Object.fromEntries(sig[1].map((n, i) => [n, expr.args[i] === undefined ? undefined : resolve(stmts, expr.args[i], seen)]));
      return toNode(sig[0], props);
    }
    return Object.fromEntries(Object.entries(expr).map(([k, v]) => [k, resolve(stmts, v, seen)]));
  }
  return expr;
}
