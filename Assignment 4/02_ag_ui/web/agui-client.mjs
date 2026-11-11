// A hand-written AG-UI client. It folds the event stream into three things:
//   messages   assistant text, assembled from TEXT_MESSAGE_* deltas
//   toolCalls  name + streamed JSON arguments, from TOOL_CALL_*
//   state      the shared state, from STATE_SNAPSHOT and STATE_DELTA (JSON Patch)
// and renders: chat text, tool-call components, and state.ui / state.detail.

import { paint } from "/common/components.mjs";
import { mountHtml } from "/common/sandbox.mjs";
import { applyPatch } from "/common/json-patch.mjs";

// The STATIC pattern: a component registered for a tool name, written by us in advance.
const TOOL_RENDERERS = {
  show_sales_dashboard(args, el, ctx) {
    const top = args.regions?.[0]?.name ?? "West";
    paint(el, { type: "Card", props: { title: `★ ${args.title ?? "Sales"} (pre-built widget)` }, children: [
      { type: "Row", props: {}, children: [
        { type: "Metric", props: { label: "Revenue", value: args.revenue ?? "…", delta: args.growth } },
        { type: "Metric", props: { label: "Regions", value: String(args.regions?.length ?? "…") } },
      ] },
      { type: "BarChart", props: { title: "Revenue by region", labels: (args.regions ?? []).map((r) => r.name), values: (args.regions ?? []).map((r) => r.revenue) } },
      { type: "Button", props: { label: `Drill into ${top}`, action: "drill_region", params: { region: top } } },
    ] }, ctx);
    el.firstChild.classList.add("static-widget");
  },
  render_html(args, el, ctx, done) {
    if (!done) { el.textContent = `receiving html… ${args.__bytes ?? 0} bytes`; el.className = "c-skeleton"; return; }
    el.className = ""; el.replaceChildren();
    mountHtml(el, args.html, { title: args.title, onAction: ctx.onAction, allowedActions: ["drill_region"] });
  },
};

/** Best-effort parse of streaming JSON: complete objects parse, partial ones fall back to {}. */
function tryParse(text) { try { return JSON.parse(text); } catch { return null; } }

export function createRenderer(container, shell) {
  let state = {}, messages = new Map(), calls = new Map(), thread = "thread_demo";
  container.innerHTML = "";
  const chat = document.createElement("div");
  const tools = document.createElement("div");
  const ui = document.createElement("div");
  const detail = document.createElement("div");
  const stateBox = document.createElement("details");

  const onAction = (name, params) => shell.action({
    action: { name, params },
    runInput: { threadId: thread, runId: `run_${Math.random().toString(16).slice(2, 10)}`, state,
      messages: [{ id: "u2", role: "user", content: `[ui action] ${name} ${JSON.stringify(params)}` }], tools: [], context: [], forwardedProps: {} },
  });
  const ctx = { onAction };

  function layout() {
    container.replaceChildren(chat, tools, ui, detail, stateBox);
    chat.className = "agui-chat"; tools.className = "agui-tools"; ui.className = "agui-ui"; detail.className = "agui-ui";
    stateBox.className = "agui-state";
  }
  layout();

  const drawState = () => {
    if (state.ui?.children?.length) paint(ui, state.ui, ctx); else ui.replaceChildren();
    if (state.detail) paint(detail, state.detail, ctx);
    stateBox.innerHTML = `<summary>shared state (${JSON.stringify(state).length} bytes)</summary><pre></pre>`;
    stateBox.querySelector("pre").textContent = JSON.stringify(state, (k, v) => (k === "html" ? `<${v.length} chars>` : v), 1);
  };

  return {
    reset() { state = {}; messages = new Map(); calls = new Map(); layout(); chat.replaceChildren(); tools.replaceChildren(); ui.replaceChildren(); detail.replaceChildren(); },
    onMessage(e) {
      switch (e.type) {
        case "RUN_STARTED": thread = e.threadId; break;
        case "TEXT_MESSAGE_START": {
          const p = document.createElement("p"); p.className = "agui-bubble"; chat.append(p); messages.set(e.messageId, p); break;
        }
        case "TEXT_MESSAGE_CONTENT": messages.get(e.messageId).textContent += e.delta; break;
        case "TOOL_CALL_START": {
          const el = document.createElement("div");
          el.className = "agui-toolcall";
          calls.set(e.toolCallId, { name: e.toolCallName, raw: "", el });
          if (TOOL_RENDERERS[e.toolCallName]) tools.append(el);
          break;
        }
        case "TOOL_CALL_ARGS": {
          const c = calls.get(e.toolCallId); c.raw += e.delta;
          const r = TOOL_RENDERERS[c.name];
          if (r) r({ ...(tryParse(c.raw) ?? {}), __bytes: c.raw.length }, c.el, ctx, false);
          break;
        }
        case "TOOL_CALL_END": {
          const c = calls.get(e.toolCallId); const r = TOOL_RENDERERS[c.name];
          if (r) r(JSON.parse(c.raw), c.el, ctx, true);
          break;
        }
        case "STATE_SNAPSHOT": state = structuredClone(e.snapshot); drawState(); break;
        case "STATE_DELTA": state = applyPatch(state, e.delta); drawState(); break;
        case "RUN_ERROR": {
          const d = document.createElement("div"); d.className = "c-error"; d.textContent = `RUN_ERROR: ${e.message}`; chat.append(d); break;
        }
      }
    },
  };
}

export const label = (e) => {
  if (e.action) return `RunAgentInput + action ${e.action.name}`;
  const extra = e.toolCallName ? ` ${e.toolCallName}` : e.delta && Array.isArray(e.delta) ? ` ${e.delta.map((o) => `${o.op} ${o.path}`).join(", ")}` : "";
  return `${e.type}${extra}`;
};
