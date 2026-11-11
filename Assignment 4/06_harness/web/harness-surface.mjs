// The web SURFACE of the harness: a transcript of the agent loop on the left
// (turns, tool calls, tool results - including validation errors the model fixes),
// and every render_ui result drawn below it. Clicks go back as user messages.
import { paint } from "/common/components.mjs";

export function createRenderer(container, ctx) {
  const transcript = document.createElement("ol");
  transcript.className = "h-transcript";
  const surfaces = document.createElement("div");
  const add = (cls, text) => { const li = document.createElement("li"); li.className = cls; li.textContent = text; transcript.append(li); return li; };
  return {
    reset() { container.replaceChildren(transcript, surfaces); transcript.replaceChildren(); surfaces.replaceChildren(); },
    onMessage(e) {
      switch (e.event) {
        case "user": add("h-user", `user: ${e.content}`); break;
        case "turn": add("h-turn", `── model turn ${e.n} ──`); break;
        case "text": add("h-text", `assistant: ${e.content}`); break;
        case "tool_call": add("h-call", `→ ${e.name}(${JSON.stringify(e.arguments).slice(0, 160)})`); break;
        case "tool_result": add(e.ok ? "h-ok" : "h-err", `${e.ok ? "✓" : "✗"} ${e.name}: ${e.content.slice(0, 200)}`); break;
        case "done": add("h-turn", `── loop ended after ${e.turns} turn(s)${e.stopped ? " · " + e.stopped : ""} ──`); break;
        case "error": add("h-err", e.content); break;
        case "render": {
          const box = document.createElement("div");
          box.className = "h-render";
          surfaces.append(box);
          paint(box, e.tree, { onAction: (action, params) => ctx.action({ action, params }) });
          box.scrollIntoView({ block: "nearest" });
          break;
        }
      }
    },
  };
}

export const label = (e) => e.action ? `ui action → user message: ${e.action}` : `${e.event}${e.name ? " " + e.name : ""}${e.ok === false ? " (error)" : ""}`;
