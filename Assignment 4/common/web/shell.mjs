// The page frame every codelab shares: mode tabs, a prompt, the rendered surface,
// and a "wire log" that shows every protocol message as it arrives.
//
// A part supplies:
//   title, subtitle, modes: {static, declarative, open_ended, mixed} -> one-line explanation
//   createRenderer(surfaceEl, ctx) -> { reset(), onMessage(msg) }
//   label(msg) -> short string for the wire log (e.g. "updateComponents", "STATE_DELTA")
// ctx.action(body) posts a user action back to the server and streams the answer
// into the same renderer.

const MODE_NAMES = { static: "Static", declarative: "Declarative", open_ended: "Open-ended", mixed: "Mixed" };

export async function* readSSE(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const data = block.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trimStart()).join("\n");
      if (data) yield JSON.parse(data);
    }
  }
}

export function mountShell(part) {
  document.title = part.title;
  const params = new URLSearchParams(location.search);
  let mode = params.get("mode") || "static";
  document.body.innerHTML = `
    <header class="top">
      <div><h1>${part.title}</h1><p>${part.subtitle}</p></div>
      <span class="llm-pill" id="llm">model: scripted fixtures</span>
    </header>
    <nav class="tabs" id="tabs"></nav>
    <p class="mode-doc" id="modedoc"></p>
    <form class="prompt" id="form">
      <input id="prompt" value="${part.prompt || "Show me Q3 sales by region"}" aria-label="prompt">
      <button type="submit">Run</button>
    </form>
    <main class="split">
      <section class="pane"><h2>Rendered UI</h2><div id="surface" class="surface"></div></section>
      <section class="pane"><h2>Wire log <small id="stats"></small></h2><ol id="log" class="log"></ol></section>
    </main>`;
  const surface = document.getElementById("surface");
  const log = document.getElementById("log");
  const stats = document.getElementById("stats");

  const tabs = document.getElementById("tabs");
  for (const key of Object.keys(MODE_NAMES)) {
    const b = document.createElement("button");
    b.textContent = MODE_NAMES[key];
    b.dataset.mode = key;
    b.onclick = () => { mode = key; drawTabs(); run(); };
    tabs.append(b);
  }
  function drawTabs() {
    for (const b of tabs.children) b.classList.toggle("on", b.dataset.mode === mode);
    document.getElementById("modedoc").textContent = part.modes[mode];
    history.replaceState(null, "", `?mode=${mode}`);
  }

  let started = 0, count = 0, firstPaint = null;
  function record(msg, direction = "in") {
    count++;
    if (firstPaint === null && direction === "in") firstPaint = Math.round(performance.now() - started);
    const li = document.createElement("li");
    li.className = direction;
    const head = document.createElement("div");
    head.className = "log-head";
    head.textContent = `${direction === "in" ? "⬇" : "⬆"} ${part.label(msg)}`;
    const pre = document.createElement("pre");
    const text = JSON.stringify(msg, null, 1);
    pre.textContent = text.length > 1400 ? text.slice(0, 1400) + "\n… (" + text.length + " chars)" : text;
    li.append(head, pre);
    log.append(li);
    log.scrollTop = log.scrollHeight;
    stats.textContent = `${count} messages · first message ${firstPaint ?? "–"} ms`;
  }

  async function pump(response) {
    for await (const msg of readSSE(response)) {
      if (msg.error) { record(msg); surface.prepend(Object.assign(document.createElement("div"), { className: "c-error", textContent: msg.error })); continue; }
      if (msg.__meta) { document.getElementById("llm").textContent = `model: ${msg.__meta.backend}`; continue; }
      record(msg);
      renderer.onMessage(msg);
    }
    document.body.dataset.state = "idle";
  }

  const ctx = {
    async action(body) {
      const payload = { mode, ...body };
      record(payload, "out");
      document.body.dataset.state = "busy";
      await pump(await fetch("/api/action", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }));
    },
    log: record,
    get mode() { return mode; },
  };
  const renderer = part.createRenderer(surface, ctx);

  async function run() {
    renderer.reset();
    log.replaceChildren();
    started = performance.now(); count = 0; firstPaint = null;
    document.body.dataset.state = "busy";
    const prompt = document.getElementById("prompt").value;
    await pump(await fetch(`/api/run?mode=${mode}&prompt=${encodeURIComponent(prompt)}`));
  }
  document.getElementById("form").onsubmit = (e) => { e.preventDefault(); run(); };
  drawTabs();
  run();
  window.genuiShell = { run, setMode: (m) => { mode = m; drawTabs(); return run(); } };
}
