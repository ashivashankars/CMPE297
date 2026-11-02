const { api, plot, kpis, table, fmt } = Shell;
const COL = { "Seasonal naive": "#8a8577", "Holt-Winters": "#5b6fa8", "GBM direct": "#b7791f" };

(async () => {
  await Shell.init();
  const r = await api("report");
  const B = r.leaderboard, gbm = B.find((b) => b.model === "GBM direct"), sn = B.find((b) => b.model === "Seasonal naive");
  const hs = r.holiday_slice, cov = r.conformal.coverage_2017;

  kpis("kpis", [
    { label: "MAPE, 1–14 days", value: `${fmt(gbm.mape, 2)}%`, sub: `vs ${fmt(sn.mape, 2)}% seasonal naive` },
    { label: "MASE", value: fmt(gbm.mase, 3), sub: "< 1 beats weekly naive" },
    { label: "Holiday MAPE", value: `${fmt(hs.find((h) => h.model === "GBM direct").mape, 1)}%`, sub: `baselines ≈ ${fmt(hs.find((h) => h.model === "Seasonal naive").mape, 0)}%` },
    { label: "80% band coverage", value: `${fmt(cov["80"].coverage * 100, 1)}%`, sub: "2017, never seen in training" },
  ]);

  // ---------- Data
  const E = r.eda;
  plot("full", [{ type: "scattergl", mode: "lines", x: E.dates, y: E.values, line: { width: 1, color: Shell.css("--accent") } }], { yaxis: { title: "GWh" }, margin: { t: 6 } });
  const D = E.decomp, comps = [["trend", "trend"], ["yearly", "yearly season"], ["weekly", "weekly season"], ["resid", "residual"]];
  plot("decomp", comps.map(([k, label], i) => ({ type: "scattergl", mode: "lines", x: D.dates, y: D[k], name: label, xaxis: "x", yaxis: `y${i ? i + 1 : ""}`, line: { width: 1 } })),
    Object.assign({ showlegend: false, margin: { l: 50, t: 6 }, xaxis: { anchor: "y4" }, annotations: comps.map(([, l], i) => ({ text: `<b>${l}</b>`, xref: "paper", yref: "paper", x: 0, y: 1 - i * 0.25, xanchor: "left", yanchor: "top", showarrow: false, font: { size: 11 } })) },
      ...comps.map((_, i) => ({ [`yaxis${i ? i + 1 : ""}`]: { domain: [1 - (i + 1) * 0.25 + 0.03, 1 - i * 0.25], gridcolor: "#ebe6da" } }))));
  const lags = E.acf.map((_, i) => i).slice(1);
  plot("acf", [{ type: "bar", name: "ACF", x: lags, y: E.acf.slice(1), marker: { color: Shell.css("--accent") } }, { type: "bar", name: "PACF", x: lags, y: E.pacf.slice(1), marker: { color: "#5b6fa8" } }],
    { barmode: "group", xaxis: { title: "lag (days)", dtick: 7 }, margin: { t: 6 } });
  plot("dow", [{ type: "bar", x: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], y: E.weekly_profile, marker: { color: Shell.css("--accent") } }], { yaxis: { range: [1000, 1500] }, margin: { t: 6 } });
  const hv = E.holiday_vs_normal;
  plot("hol", [{ type: "bar", x: ["weekday", "holiday", "Sunday"], y: [hv.weekday, hv.holiday, hv.sunday], marker: { color: ["#8a8577", "#b23b3b", "#8a8577"] }, text: [hv.weekday, hv.holiday, hv.sunday].map((v) => fmt(v, 0)), textposition: "outside" }],
    { yaxis: { range: [0, 1700] }, margin: { t: 6 } });

  // ---------- Preparation
  const O = r.test_origins;
  plot("origins", [
    { type: "bar", orientation: "h", y: ["data"], x: [3652], base: [0], name: "train 2006–15", marker: { color: "#d9c39a" }, hoverinfo: "name" },
    { type: "bar", orientation: "h", y: ["data"], x: [366], base: [3652], name: "calibrate 2016", marker: { color: "#b7791f" }, hoverinfo: "name" },
    { type: "bar", orientation: "h", y: ["data"], x: [365], base: [4018], name: "backtest 2017", marker: { color: "#3a3833" }, hoverinfo: "name" },
    ...O.slice(0, 51).filter((_, i) => i % 5 === 0).map((o, i) => ({ type: "scatter", mode: "lines", y: ["origins", "origins"], x: [4018 + i * 35, 4018 + i * 35 + 14], line: { width: 6, color: "#b7791f" }, showlegend: false, hoverinfo: "skip" })),
  ], { barmode: "overlay", xaxis: { title: "days since 2006-01-01" }, legend: { y: -0.45 }, margin: { l: 70 } });
  document.getElementById("rows").textContent = `Rows: ${Object.entries(r.n_rows).map(([k, v]) => `${k} ${fmt(v, 0)}`).join(" · ")}`;

  // ---------- Evaluation
  table("board", B, [{ key: "model", label: "Model" }, { key: "mae", label: "MAE (GWh)", num: true, d: 1 }, { key: "mape", label: "MAPE %", num: true, d: 2 },
    { key: "mase", label: "MASE", num: true }, { key: "bias", label: "Bias (GWh)", num: true, d: 1 }], { best: B.indexOf(gbm) });
  plot("byh", Object.keys(COL).map((m) => { const rows = r.by_horizon.filter((x) => x.model === m); return { x: rows.map((x) => x.horizon), y: rows.map((x) => x.mape), name: m, mode: "lines+markers", line: { color: COL[m], width: 3 } }; }),
    { xaxis: { title: "horizon (days ahead)", dtick: 1 }, yaxis: { title: "MAPE %", rangemode: "tozero" } });
  plot("holslice", [{ type: "bar", x: hs.map((h) => h.model), y: hs.map((h) => h.mape), marker: { color: hs.map((h) => COL[h.model]) }, text: hs.map((h) => `${fmt(h.mape, 1)}%`), textposition: "outside" }],
    { yaxis: { title: "MAPE on public holidays %", range: [0, Math.max(...hs.map((h) => h.mape)) * 1.2] } });
  const lv = ["50", "80", "95"];
  plot("cov", [{ type: "bar", name: "target", x: lv.map((l) => `${l}% band`), y: lv.map(Number), marker: { color: "#e2dccd" } },
    { type: "bar", name: "achieved 2017", x: lv.map((l) => `${l}% band`), y: lv.map((l) => cov[l].coverage * 100), marker: { color: Shell.css("--accent") }, text: lv.map((l) => `${fmt(cov[l].coverage * 100, 1)}%`), textposition: "outside" }],
  { barmode: "group", yaxis: { range: [0, 110], title: "% of actuals inside band" } });
  const worst = lv.reduce((w, l) => (Math.abs(cov[l].coverage * 100 - +l) > Math.abs(cov[w].coverage * 100 - +w) ? l : w));
  const gap = cov[worst].coverage * 100 - +worst;
  document.getElementById("covnote").textContent = Math.abs(gap) < 2.5
    ? `All three bands land within ${fmt(Math.abs(gap), 1)} points of their target on a year the model never saw. Bands are calibrated on every daily origin of 2016 (≈5k residuals), so each horizon gets its own width.`
    : gap > 0
      ? `Every band covers at least its target. The ${worst}% band is ${fmt(gap, 1)} points conservative (slightly too wide) on 2017. Erring wide is the safe direction for grid reserve; recalibrating on a rolling window would tighten it.`
      : `The ${worst}% band under-covers by ${fmt(-gap, 1)} points on 2017. That suggests a shift between the calibration year and the test year; recalibrating on a rolling window is the production fix.`;
  const imp = [...r.importance].reverse();
  plot("imp", [{ type: "bar", orientation: "h", y: imp.map((i) => i.feature), x: imp.map((i) => i.importance), marker: { color: Shell.css("--accent") } }],
    { xaxis: { title: "MAE increase when shuffled (GWh)" }, yaxis: { automargin: true }, margin: { l: 10 } });

  // ---------- Forecast
  const presets = { "Christmas 2017": "2017-12-17", "Easter 2017": "2017-04-09", "Ordinary June": "2017-06-11", "Reformation Day (Oct 31)": "2017-10-22" };
  const presets_el = document.getElementById("presets");
  presets_el.innerHTML = Object.entries(presets).map(([k, v]) => `<span class="chip" data-d="${v}">${k}</span>`).join("");
  const on = new Set(["GBM direct", "Seasonal naive"]);
  mchips.innerHTML = Object.keys(COL).map((m) => `<span class="chip ${on.has(m) ? "on" : ""}" data-m="${m}">${m}</span>`).join("");
  const run = async () => {
    const f = await api(`forecast?origin=${orig.value}`);
    const band = f.bands[band_el()], g = f["GBM direct"];
    const traces = [{ x: f.history.dates, y: f.history.values, mode: "lines", name: "history", line: { color: "#3a3833", width: 2 } },
      { x: f.targets, y: g.map((v, i) => v + band[i]), mode: "lines", line: { width: 0 }, showlegend: false, hoverinfo: "skip" },
      { x: f.targets, y: g.map((v, i) => v - band[i]), mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: "rgba(183,121,31,.2)", name: `${band_el()}% band (GBM)` }];
    Object.keys(COL).filter((m) => on.has(m)).forEach((m) => traces.push({ x: f.targets, y: f[m], mode: "lines+markers", name: m, line: { color: COL[m], width: m === "GBM direct" ? 3 : 2, dash: m === "GBM direct" ? "solid" : "dot" } }));
    traces.push({ x: f.targets, y: f.actual, mode: "markers", name: "actual", marker: { size: 9, color: "#1e1d1a", symbol: "x" } });
    const holShapes = f.targets.map((d, i) => (f.holiday[i] ? { type: "rect", xref: "x", yref: "paper", x0: d, x1: d, y0: 0, y1: 1, line: { color: "rgba(178,59,59,.5)", width: 6 } } : null)).filter(Boolean);
    plot("fan", traces, { yaxis: { title: "GWh" }, shapes: [{ type: "line", xref: "x", yref: "paper", x0: orig.value, x1: orig.value, y0: 0, y1: 1, line: { dash: "dash", color: "#888" } }, ...holShapes] });
    ftitle.textContent = `14-day forecast made at the end of ${orig.value}${f.in_sample ? " (2016: calibration year)" : " (out-of-sample)"}`;
    const err = (m) => { const e = f.actual.map((a, i) => (a == null ? null : Math.abs(f[m][i] - a) / a)).filter((x) => x != null); return e.length ? (e.reduce((a, b) => a + b) / e.length) * 100 : null; };
    fstats.innerHTML = `<table class="data">${Object.keys(COL).map((m) => `<tr><td>${m}</td><td class="n">${err(m) == null ? "—" : fmt(err(m), 2) + "%"}</td></tr>`).join("")}</table><p class="muted" style="font-size:.84rem">MAPE for this one forecast. Red bars mark public holidays.</p>`;
  };
  const band_el = () => document.getElementById("band").value;
  presets_el.querySelectorAll(".chip").forEach((c) => (c.onclick = () => { orig.value = c.dataset.d; run(); }));
  mchips.querySelectorAll(".chip").forEach((c) => (c.onclick = () => { on.has(c.dataset.m) ? on.delete(c.dataset.m) : on.add(c.dataset.m); c.classList.toggle("on"); run(); }));
  orig.addEventListener("change", run); document.getElementById("band").addEventListener("change", run);
  run();
})();
