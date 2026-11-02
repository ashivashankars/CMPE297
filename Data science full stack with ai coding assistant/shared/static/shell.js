// Shared UI shell: header, tabs, API helper, Plotly theme, KPI/table helpers,
// and the code-tour tab. Each project page only writes its own sections.
const Shell = (() => {
  const api = async (path, body) => {
    const opts = body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    };
    const res = await fetch(`api/${path}`, opts);
    if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
    return res.json();
  };

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  const plot = (el, traces, layout = {}, config = {}) => {
    const node = typeof el === "string" ? document.getElementById(el) : el;
    const base = {
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Inter, Segoe UI, system-ui, sans-serif", size: 12, color: css("--ink") },
      margin: { l: 56, r: 18, t: layout.title ? 40 : 14, b: 46 },
      xaxis: { gridcolor: "#ebe6da", zerolinecolor: "#d8d2c4", ...(layout.xaxis || {}) },
      yaxis: { gridcolor: "#ebe6da", zerolinecolor: "#d8d2c4", ...(layout.yaxis || {}) },
      legend: { orientation: "h", y: -0.2, ...(layout.legend || {}) },
      // accent first, then a fixed palette minus whichever colour equals the accent
      colorway: [css("--accent"), ...["#c0703a", "#5b6fa8", "#8a6aa8", "#b7791f", "#3f8f8a", "#a64d5d", "#2f5d50"].filter((c) => c !== css("--accent"))],
    };
    return Plotly.react(node, traces, { ...base, ...layout, xaxis: base.xaxis, yaxis: base.yaxis, legend: base.legend },
      { displayModeBar: false, responsive: true, ...config });
  };

  const fmt = (v, d = 2) => (typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: Math.min(d, Number.isInteger(v) ? 0 : d) }) : v);

  const kpis = (el, items) => {
    document.getElementById(el).innerHTML = items.map((k) =>
      `<div class="kpi"><div class="label">${k.label}</div><div class="value">${k.value}</div><div class="sub">${k.sub || ""}</div></div>`).join("");
  };

  const table = (el, rows, cols, opts = {}) => {
    const head = cols.map((c) => `<th${c.num ? ' style="text-align:right"' : ""}>${c.label}</th>`).join("");
    const body = rows.map((r, i) => `<tr class="${opts.best === i ? "best" : ""}">` + cols.map((c) => {
      const v = c.render ? c.render(r) : r[c.key];
      return `<td class="${c.num ? "n" : ""}">${c.num && typeof v === "number" ? fmt(v, c.d ?? 3) : v ?? ""}</td>`;
    }).join("") + "</tr>").join("");
    document.getElementById(el).innerHTML = `<table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  };

  const showTab = (name) => {
    document.querySelectorAll("section[data-tab]").forEach((s) => s.classList.toggle("on", s.dataset.tab === name));
    document.querySelectorAll("nav.tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
    window.dispatchEvent(new CustomEvent("tab", { detail: name }));
    // Plotly charts drawn while hidden need a resize once visible
    document.querySelectorAll(`section[data-tab="${name}"] .js-plotly-plot`).forEach((p) => Plotly.Plots.resize(p));
    history.replaceState(null, "", `#${encodeURIComponent(name)}`);
  };

  const renderTour = async () => {
    const sec = document.querySelector('section[data-tab="Code tour"]');
    const items = await api("code_tour");
    sec.innerHTML = `<p class="lead">A guided read of the source that produced everything in this app. Each section is pulled live from the repo, so the line numbers match GitHub.</p>
      <div class="tour"><div class="toc">${items.map((it, i) => `<button data-i="${i}"><b>${it.title}</b><small>${it.file}:${it.start}-${it.end}</small></button>`).join("")}</div>
      <div><div class="note" id="tour-note"></div><div id="tour-code" style="margin-top:12px"></div></div></div>`;
    const pick = (i) => {
      sec.querySelectorAll(".toc button").forEach((b) => b.classList.toggle("on", +b.dataset.i === i));
      sec.querySelector("#tour-note").innerHTML = items[i].note;
      sec.querySelector("#tour-code").innerHTML = items[i].html;
    };
    sec.querySelectorAll(".toc button").forEach((b) => b.onclick = () => pick(+b.dataset.i));
    if (items.length) pick(0);
  };

  const init = async () => {
    const meta = await api("meta");
    document.title = meta.title;
    if (meta.accent) {
      document.documentElement.style.setProperty("--accent", meta.accent);
      document.documentElement.style.setProperty("--accent-soft", meta.accent_soft || "#eef");
    }
    const tour = document.createElement("section");
    tour.dataset.tab = "Code tour"; tour.dataset.phase = "How it's built";
    document.querySelector("main").appendChild(tour);
    const sections = [...document.querySelectorAll("section[data-tab]")];
    const header = document.createElement("header");
    header.className = "topbar";
    header.innerHTML = `<div class="inner"><div class="brand"><a class="back" href="/">&larr; All projects</a>
      <h1>${meta.title}</h1><span class="tag">${meta.tag}</span><p>${meta.blurb}</p></div>
      <nav class="tabs">${sections.map((s) => `<button data-tab="${s.dataset.tab}">${s.dataset.tab}<small>${s.dataset.phase || ""}</small></button>`).join("")}</nav></div>`;
    document.body.prepend(header);
    header.querySelectorAll("nav.tabs button").forEach((b) => b.onclick = () => showTab(b.dataset.tab));
    const cap = document.createElement("div"); cap.id = "caption"; document.body.appendChild(cap);
    renderTour();
    const start = decodeURIComponent(location.hash.slice(1));
    showTab(sections.some((s) => s.dataset.tab === start) ? start : sections[0].dataset.tab);
    return meta;
  };

  return { api, plot, kpis, table, fmt, init, showTab, css };
})();

// Hooks for the walkthrough recorder (captions + spotlight on an element)
window.__caption = (t) => { const c = document.getElementById("caption"); if (c) c.textContent = t || ""; };
window.__spot = (sel) => {
  document.querySelectorAll(".spot").forEach((e) => e.classList.remove("spot"));
  const el = sel && document.querySelector(sel);
  if (el) { el.classList.add("spot"); el.scrollIntoView({ behavior: "smooth", block: "center" }); }
};
