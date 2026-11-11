// The HOST side of MCP Apps in the browser: mount the view, enforce its CSP, answer
// its JSON-RPC, deliver tool-input/tool-result, proxy tools/call to host.py.

export const APP_MIME = "text/html;profile=mcp-app";

/** Restrictive default CSP, widened only by domains the resource declared in _meta.ui.csp. */
export function cspFor(uiMeta = {}) {
  const csp = uiMeta.csp ?? {};
  const ok = (d) => typeof d === "string" && !/[;\s'"]/.test(d);
  const extra = (list) => (list ?? []).filter(ok).join(" ");
  return [
    "default-src 'none'",
    `script-src 'unsafe-inline' ${extra(csp.resourceDomains)}`.trim(),
    `style-src 'unsafe-inline' ${extra(csp.resourceDomains)}`.trim(),
    "img-src data:",
    `connect-src ${extra(csp.connectDomains) || "'none'"}`,
    "base-uri 'none'",
  ].join("; ");
}

export function withCsp(html, csp) {
  const meta = `<meta http-equiv="Content-Security-Policy" content="${csp}">`;
  const m = /^\s*<!doctype[^>]*>/i.exec(html);
  const at = m ? m[0].length : 0;
  return html.slice(0, at) + meta + html.slice(at);
}

export function mountApp(container, { html, mimeType, meta, tool, toolInput, toolResult, log, onChat }) {
  if (mimeType !== APP_MIME) throw new Error(`not an MCP App view: ${mimeType}`);
  const frame = document.createElement("iframe");
  frame.setAttribute("sandbox", "allow-scripts");          // opaque origin: no access to this page
  frame.className = "mcp-view";
  frame.srcdoc = withCsp(html, cspFor(meta?.ui));
  container.append(frame);

  const send = (msg) => { log({ jsonrpc: "2.0", ...msg }, "out"); frame.contentWindow.postMessage({ jsonrpc: "2.0", ...msg }, "*"); };
  const reply = (id, result) => send({ id, result });

  async function handle(m) {
    switch (m.method) {
      case "ui/initialize":
        return reply(m.id, { protocolVersion: "2025-06-18", hostInfo: { name: "cmpe297-host", version: "1.0.0" },
          hostCapabilities: { serverTools: {}, message: { text: {} } },
          hostContext: { theme: "light", displayMode: "inline", toolInfo: { tool } } });
      case "ui/notifications/initialized":           // only now is the view ready for data
        send({ method: "ui/notifications/tool-input", params: { arguments: toolInput } });
        send({ method: "ui/notifications/tool-result", params: toolResult });
        return;
      case "tools/call": {
        const res = await fetch("/api/call-tool", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(m.params) });
        return reply(m.id, await res.json());
      }
      case "ui/message":
        onChat?.(m.params?.content?.[0]?.text ?? "");
        return reply(m.id, {});
      case "ui/notifications/size-changed":
        if (Number.isFinite(m.params?.height)) frame.style.height = Math.min(Math.max(m.params.height, 80), 1400) + "px";
        return;
      default:
        if (m.id !== undefined) send({ id: m.id, error: { code: -32601, message: `method not found: ${m.method}` } });
    }
  }
  const onMessage = (e) => {
    if (e.source !== frame.contentWindow) return;          // only this view
    const m = e.data;
    if (!m || m.jsonrpc !== "2.0" || typeof m.method !== "string") return;
    if (m.method !== "ui/notifications/size-changed") log(m, "in");
    handle(m);
  };
  window.addEventListener("message", onMessage);
  return () => window.removeEventListener("message", onMessage);
}
