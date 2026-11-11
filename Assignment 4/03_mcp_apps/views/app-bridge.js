// The VIEW side of the MCP Apps bridge: JSON-RPC 2.0 over postMessage to the host.
//   view -> host  ui/initialize (request), ui/notifications/initialized,
//                 tools/call (request, proxied by the host to the MCP server),
//                 ui/message, ui/notifications/size-changed
//   host -> view  ui/notifications/tool-input, ui/notifications/tool-result
const app = (() => {
  let nextId = 1;
  const pending = new Map();
  const handlers = {};
  const post = (msg) => parent.postMessage({ jsonrpc: "2.0", ...msg }, "*");
  window.addEventListener("message", (e) => {
    if (e.source !== parent) return;                       // only the host may talk to the view
    const m = e.data;
    if (!m || m.jsonrpc !== "2.0") return;
    if (m.id !== undefined && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); return; }
    if (m.method && handlers[m.method]) handlers[m.method](m.params || {});
  });
  const request = (method, params) => new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, (m) => (m.error ? reject(new Error(m.error.message)) : resolve(m.result)));
    post({ id, method, params });
  });
  const notify = (method, params) => post({ method, params });
  return {
    on(method, fn) { handlers[method] = fn; },
    async connect(name) {
      const init = await request("ui/initialize", { protocolVersion: "2025-06-18", appInfo: { name, version: "1.0.0" }, appCapabilities: {} });
      notify("ui/notifications/initialized", {});
      new ResizeObserver(() => notify("ui/notifications/size-changed", { height: Math.ceil(document.body.getBoundingClientRect().height) + 24 }))
        .observe(document.body);
      return init;
    },
    callTool: (name, args) => request("tools/call", { name, arguments: args }),
    say: (text) => request("ui/message", { role: "user", content: [{ type: "text", text }] }),
  };
})();
