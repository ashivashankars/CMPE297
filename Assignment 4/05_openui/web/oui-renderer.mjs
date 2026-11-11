// Streams program text into a growing buffer, re-parses after every chunk,
// paints the resolved tree, and shows the program itself next to the UI.
import { paint } from "/common/components.mjs";
import { parse, resolve } from "/openui.mjs";

export function createRenderer(container, ctx) {
  let program = "", done = false;
  const ui = document.createElement("div");
  const code = document.createElement("pre");
  code.className = "oui-code";
  const draw = () => {
    const stmts = parse(program, { partial: !done });
    const names = Object.keys(stmts);
    paint(ui, resolve(stmts), {
      onAction: (action, params) => ctx.action({ action, params, program }),
    });
    code.textContent = `# ${names.length} statement(s) parsed${done ? "" : " (streaming…)"}\n` +
      program.replace(/"<!doctype html>(?:[^"\\]|\\.)*"/gi, (m) => `"<html… ${m.length} chars>"`);
  };
  return {
    reset() { program = ""; done = false; container.replaceChildren(ui, code); ui.replaceChildren(); code.textContent = ""; },
    onMessage(m) {
      if (m.delta) program += m.delta;
      if (m.append) program += (program.endsWith("\n") ? "" : "\n") + m.append;
      if (m.done) { done = true; program += program.endsWith("\n") ? "" : "\n"; }
      if (m.append) done = true;
      draw();
      if (m.done) {
        const s = document.createElement("div");
        s.className = "oui-stats";
        s.textContent = `program: ${m.bytes} bytes · same UI as a JSON tree: ${m.jsonTreeBytes} bytes (${Math.round(100 * m.bytes / m.jsonTreeBytes)}%)`;
        container.insertBefore(s, code);
      }
    },
  };
}

export const label = (m) => m.delta !== undefined ? `text delta (${m.delta.length} chars)` : m.done ? "done · validated"
  : m.append ? "append (app patch)" : m.action ? `action ${m.action}` : "message";
