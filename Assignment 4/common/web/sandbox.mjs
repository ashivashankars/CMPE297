// The open-ended boundary: model-written HTML runs here and nowhere else.
//
// Three layers, from outside in:
//   1. <iframe sandbox="allow-scripts">  - no allow-same-origin, so the frame gets an
//      opaque origin: it cannot read the page, its cookies, or its storage.
//   2. A Content-Security-Policy <meta> injected before the document: no network
//      (connect-src 'none'), no external scripts, styles or frames.
//   3. One message shape back to the page: {genui:"action", name, params}. The page
//      checks the sender (event.source) and the action name before doing anything.
//
// The generated document gets a tiny helper, window.genui.action(name, params),
// so it can close the loop exactly like a catalog Button does.

export const CSP = [
  "default-src 'none'",
  "script-src 'unsafe-inline'",
  "style-src 'unsafe-inline'",
  "img-src data:",
  "font-src data:",
  "connect-src 'none'",
  "frame-src 'none'",
  "form-action 'none'",
  "base-uri 'none'",
].join("; ");

const BRIDGE = `<script>
window.genui = {
  action(name, params) { parent.postMessage({ genui: "action", name: String(name), params: params || {} }, "*"); }
};
addEventListener("DOMContentLoaded", () => {
  const report = () => parent.postMessage({ genui: "resize", height: Math.ceil(document.body.getBoundingClientRect().height) + 28 }, "*");
  new ResizeObserver(report).observe(document.body);
  report();
});
<\/script>`;

export function buildSrcdoc(html) {
  const meta = `<meta http-equiv="Content-Security-Policy" content="${CSP}">`;
  // The policy must come before any markup the model wrote, so it governs all of it.
  const m = /^\s*<!doctype[^>]*>/i.exec(html);
  const at = m ? m[0].length : 0;
  return html.slice(0, at) + meta + BRIDGE + html.slice(at);
}

export function mountHtml(container, html, { title = "Generated view", onAction, allowedActions } = {}) {
  const wrap = document.createElement("div");
  wrap.className = "htmlview";
  wrap.dataset.type = "HtmlView";
  const label = document.createElement("div");
  label.className = "htmlview-label";
  label.textContent = `⚠ ${title} · model-generated HTML · sandboxed`;
  const frame = document.createElement("iframe");
  frame.setAttribute("sandbox", "allow-scripts");
  frame.setAttribute("referrerpolicy", "no-referrer");
  frame.title = title;
  frame.srcdoc = buildSrcdoc(html);
  frame.style.height = "160px";
  wrap.append(label, frame);
  container.append(wrap);

  const onMessage = (event) => {
    if (event.source !== frame.contentWindow) return;          // only this frame
    const msg = event.data;
    if (!msg || typeof msg !== "object") return;
    if (msg.genui === "resize" && Number.isFinite(msg.height)) {
      frame.style.height = Math.min(Math.max(msg.height, 60), 900) + "px";
    } else if (msg.genui === "action" && typeof msg.name === "string") {
      if (allowedActions && !allowedActions.includes(msg.name)) {
        console.warn("blocked action from sandbox:", msg.name);
        return;
      }
      onAction?.(msg.name, msg.params && typeof msg.params === "object" ? msg.params : {}, "HtmlView");
    }
  };
  window.addEventListener("message", onMessage);
  wrap.dispose = () => window.removeEventListener("message", onMessage);
  return wrap;
}
