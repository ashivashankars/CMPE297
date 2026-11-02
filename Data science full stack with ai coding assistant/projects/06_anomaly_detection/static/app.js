const { api, plot, kpis, table, fmt } = Shell;
const QS = [0.98, 0.99, 0.995, 0.999, 0.9995, 1.0];
const MCOL = { "Rolling robust z": "#5b6fa8", "Seasonal residual z": "#b7791f", "Isolation Forest": "#a64d5d", "Local Outlier Factor": "#3f8f8a", "Ensemble (rank mean)": "#1e1d1a" };
const cache = {};
const getSeries = async (n) => (cache[n] ??= await api(`series/${n}`));

// red failure windows + gray probation, as layout shapes
const shapes = (s) => [
  { type: "rect", xref: "x", yref: "paper", x0: s.timestamps[0], x1: s.timestamps[s.n_probation], y0: 0, y1: 1, fillcolor: "rgba(120,110,95,.12)", line: { width: 0 } },
  ...s.windows.map(([a, b]) => ({ type: "rect", xref: "x", yref: "paper", x0: a, x1: b, y0: 0, y1: 1, fillcolor: "rgba(178,59,59,.16)", line: { width: 0 } })),
];
// client-side re-thresholding: scores are probation percentiles, so "alert if score > q"
const alertsAt = (scores, nProb, q, refractory) => {
  const out = []; let last = -1e9;
  for (let i = nProb; i < scores.length; i++) if (scores[i] > q && i - last > refractory) { out.push(i); last = i; }
  return out;
};

(async () => {
  await Shell.init();
  const r = await api("report");
  const S = r.summary, names = Object.keys(r.series_meta);
  const best = (k, lower) => S.reduce((a, c) => ((lower ? c[k] < a[k] : c[k] > a[k]) ? c : a));
  const iso = best("detected"), lof = best("pr_auc"), quiet = best("fa_per_week", true);

  kpis("kpis", [
    { label: "Most failures caught", value: `${iso.detected} / ${iso.windows}`, sub: iso.method },
    { label: "Best PR-AUC", value: fmt(lof.pr_auc, 3), sub: `${lof.method} (base rate ≈ ${fmt(r.per_series.reduce((a, c) => a + c.pr_auc_base_rate, 0) / r.per_series.length, 2)})` },
    { label: "Quietest detector", value: `${fmt(quiet.fa_per_week, 2)}`, sub: `false alarms / week · ${quiet.method}` },
    { label: "Series × detectors", value: `${names.length} × ${S.length}`, sub: "62k points, 15 failure windows" },
  ]);

  // ---------- Data gallery
  document.getElementById("gallery").innerHTML = names.map((n) => `<div class="card"><h3>${n.replaceAll("_", " ")}</h3><p class="muted" style="margin:0">${r.series_meta[n].description}</p><div id="g_${n}" class="plot" style="min-height:220px"></div></div>`).join("");
  for (const n of names) {
    const s = await getSeries(n);
    plot(`g_${n}`, [{ type: "scattergl", mode: "lines", x: s.timestamps, y: s.values, line: { width: 1, color: "#3a3833" } }], { shapes: shapes(s), margin: { t: 6, b: 30 } });
  }

  // ---------- Detectors
  const methods = Object.keys(MCOL);
  det_series.innerHTML = m_series.innerHTML = names.map((n) => `<option>${n}</option>`).join("");
  m_method.innerHTML = methods.map((m) => `<option>${m}</option>`).join("");
  const drawDet = async () => {
    const s = await getSeries(det_series.value);
    const rows = methods.length + 1, gap = 0.02, h = (1 - gap * (rows - 1)) / rows;
    const dom = (i) => [1 - (i + 1) * h - i * gap, 1 - i * h - i * gap];
    const traces = [{ type: "scattergl", mode: "lines", x: s.timestamps, y: s.values, line: { width: 1, color: "#3a3833" }, yaxis: "y" }];
    const lay = { showlegend: false, margin: { l: 50, r: 10, t: 10, b: 30 }, xaxis: { anchor: `y${rows}` }, yaxis: { domain: dom(0) }, annotations: [], shapes: [] };
    const label = (txt, i) => lay.annotations.push({ text: `<b>${txt}</b>`, xref: "paper", yref: "paper", x: 0.005, y: dom(i)[1], xanchor: "left", yanchor: "top", showarrow: false, font: { size: 11 }, bgcolor: "rgba(255,253,248,.85)" });
    label("value", 0);
    methods.forEach((m, i) => {
      const ax = `y${i + 2}`;
      traces.push({ type: "scattergl", mode: "lines", x: s.timestamps, y: s.scores[m].map((v) => Math.min(v, 1.02)), line: { width: 1, color: MCOL[m] }, yaxis: ax });
      lay[`yaxis${i + 2}`] = { domain: dom(i + 1), range: [0.9, 1.025], tickvals: [0.9, 0.999], ticktext: ["90%", "99.9%"], gridcolor: "#ebe6da" };
      lay.shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, yref: ax, y0: 0.999, y1: 0.999, line: { color: "#b23b3b", width: 1, dash: "dot" } });
      label(m, i + 1);
    });
    // failure windows + probation span across every panel
    shapes(s).forEach((sh) => lay.shapes.push(sh));
    plot("det_plot", traces, lay);
  };
  det_series.onchange = drawDet; det_series.value = "machine_temperature"; drawDet();

  // ---------- Evaluation
  table("summary", S, [
    { key: "method", label: "Detector" }, { label: "Windows caught", render: (x) => `${x.detected} / ${x.windows}` },
    { key: "recall_events", label: "Event recall", num: true, d: 2 }, { key: "fa_per_week", label: "False alarms / wk", num: true, d: 2 },
    { key: "alert_precision", label: "Alert precision", num: true, d: 2 }, { key: "pr_auc", label: "PR-AUC", num: true, d: 3 },
    { key: "detection_position", label: "Detected at (0 = window start)", num: true, d: 2 }]);
  plot("curve", methods.map((m) => {
    const pts = r.operating_curve.filter((c) => c.method === m);
    return { x: pts.map((p) => p.fa_per_week), y: pts.map((p) => p.detected), mode: "lines+markers", name: m, line: { color: MCOL[m], width: 2 },
      text: pts.map((p) => `threshold: probation ${p.quantile * 100}th pct`), marker: { size: 8 } };
  }), { xaxis: { title: "false alarms per week (avg per series)", rangemode: "tozero" }, yaxis: { title: "failure windows caught (of 15)", range: [0, 15.5] }, legend: { y: -0.3 } });
  plot("perseries", methods.map((m) => ({ type: "bar", name: m, x: names.map((n) => n.replaceAll("_", "<br>")), marker: { color: MCOL[m] },
    y: names.map((n) => r.per_series.find((p) => p.series === n && p.method === m).detected) })),
  { barmode: "group", yaxis: { title: "windows caught", dtick: 1 }, legend: { y: -0.35 } });

  // ---------- Monitor
  let injected = null;
  const drawMon = async () => {
    const s = await getSeries(m_series.value), m = m_method.value, q = QS[+m_q.value];
    qv.textContent = q === 1 ? "max (100th)" : `${fmt(q * 100, 2)}th`;
    const al = injected ? injected.methods[m].alerts : alertsAt(s.scores[m], s.n_probation, q, Math.floor(s.points_per_day / 2));
    const vals = injected ? injected.values : s.values;
    const inW = (i) => s.windows.some(([a, b]) => s.timestamps[i] >= a.slice(0, 16) && s.timestamps[i] <= b.slice(0, 16));
    const hits = al.filter(inW).length;
    m_title.textContent = `${m_series.value.replaceAll("_", " ")} · ${m}`;
    m_stats.innerHTML = `<table class="data"><tr><td>Alerts</td><td class="n">${al.length}</td></tr><tr><td>Inside failure windows</td><td class="n">${hits}</td></tr>
      <tr><td>Windows caught</td><td class="n">${s.windows.filter(([a, b]) => al.some((i) => s.timestamps[i] >= a.slice(0, 16) && s.timestamps[i] <= b.slice(0, 16))).length} / ${s.windows.length}</td></tr></table>`;
    const sh = shapes(s);
    if (injected) sh.push({ type: "rect", xref: "x", yref: "paper", x0: s.timestamps[injected.start], x1: s.timestamps[Math.min(injected.end, s.n - 1)], y0: 0, y1: 1, fillcolor: "rgba(242,183,5,.35)", line: { width: 0 } });
    plot("m_plot", [
      { type: "scattergl", mode: "lines", x: s.timestamps, y: vals, line: { width: 1, color: "#3a3833" }, name: "value" },
      { type: "scatter", mode: "markers", x: al.map((i) => s.timestamps[i]), y: al.map((i) => vals[i]), name: "alert",
        marker: { size: 11, symbol: "triangle-down", color: al.map((i) => (inW(i) ? "#2f7a4b" : "#b23b3b")), line: { width: 1, color: "#fff" } } },
    ], { shapes: sh, legend: { y: -0.15 } });
  };
  ["m_series", "m_method", "m_q"].forEach((id) => document.getElementById(id).addEventListener("input", () => { if (id === "m_series") reset(); else drawMon(); }));
  const syncLabels = () => { posv.textContent = i_pos.value; magv.textContent = i_mag.value; };
  [i_pos, i_mag].forEach((e) => e.addEventListener("input", syncLabels)); syncLabels();
  const reset = () => { injected = null; i_result.style.display = "none"; drawMon(); };
  i_reset.onclick = reset;
  i_go.onclick = async () => {
    i_go.disabled = true; i_go.textContent = "Scoring…";
    injected = await api("inject", { series: m_series.value, kind: i_kind.value, position: +i_pos.value / 100, magnitude: +i_mag.value, quantile: QS[+m_q.value] });
    i_go.disabled = false; i_go.textContent = "Inject & re-score";
    i_result.style.display = "block";
    const rows = Object.entries(injected.methods).map(([m, v]) => ({ m, caught: v.caught, delay: v.delay_points }));
    table("i_table", rows, [{ key: "m", label: "Detector" },
      { label: "Caught?", render: (x) => (x.caught ? '<span class="pill good">caught</span>' : '<span class="pill bad">missed</span>') },
      { label: "Delay", render: (x) => (x.caught ? `${x.delay} points (${fmt((x.delay / injected.points_per_day) * 24, 1)} h)` : "—") }]);
    drawMon();
  };
  m_series.value = "machine_temperature"; m_method.value = "Isolation Forest";
  drawMon();
})();
