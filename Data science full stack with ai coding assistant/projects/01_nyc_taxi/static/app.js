const { api, plot, kpis, table, fmt } = Shell;

(async () => {
  await Shell.init();
  const r = await api("report");
  const champ = r.leaderboard.find((m) => m.champion);
  const rule = r.leaderboard[1];

  kpis("kpis", [
    { label: "Test MAE", value: `${fmt(champ.mae_min, 1)} min`, sub: `vs ${fmt(rule.mae_min, 1)} min rule of thumb` },
    { label: "90% range coverage", value: `${fmt(r.intervals["90"].coverage * 100, 1)}%`, sub: "on the unseen final week" },
    { label: "R² (test)", value: fmt(champ.r2, 3), sub: "HistGBM + hill climbing" },
    { label: "Rides used", value: fmt(r.clean_log.rows_out, 0), sub: `${r.clean_log.rows_in - r.clean_log.rows_out} removed by cleaning rules` },
  ]);

  // ---------- Data
  const e = r.eda;
  plot("hist", [{ type: "bar", x: e.duration_hist.map((_, i) => i * 2 + 1), y: e.duration_hist, marker: { color: Shell.css("--accent") } }],
    { xaxis: { title: "minutes" }, yaxis: { title: "rides" }, bargap: 0.05 });
  const boroughs = [...new Set(e.scatter.borough)];
  plot("scatter", boroughs.map((b) => {
    const idx = e.scatter.borough.map((x, i) => (x === b ? i : -1)).filter((i) => i >= 0);
    return { type: "scattergl", mode: "markers", name: b, x: idx.map((i) => e.scatter.distance[i]), y: idx.map((i) => e.scatter.duration[i]), marker: { size: 5, opacity: 0.55 } };
  }), { xaxis: { title: "distance (mi)", range: [0, 20] }, yaxis: { title: "minutes", range: [0, 90] } });
  plot("heat", [{ type: "heatmap", z: e.heatmap.z, x: e.heatmap.hours, y: e.heatmap.days, colorscale: [[0, "#fbf3ea"], [1, "#9c4a1c"]], colorbar: { title: "min" } }],
    { xaxis: { title: "pickup hour" }, yaxis: { autorange: "reversed" } });
  const corr = Object.entries(e.correlations).filter(([k]) => k !== "duration_min").sort((a, b) => b[1] - a[1]);
  const leaky = ["fare", "tip", "tolls", "total"];
  plot("corr", [{ type: "bar", orientation: "h", y: corr.map((c) => c[0]), x: corr.map((c) => c[1]),
    marker: { color: corr.map((c) => (leaky.includes(c[0]) ? "#b23b3b" : Shell.css("--accent"))) } }],
    { xaxis: { title: "Pearson r with duration", range: [0, 1] }, yaxis: { autorange: "reversed" }, margin: { l: 90 } });

  // ---------- Preparation
  const cl = r.clean_log;
  table("cleanlog", [
    { rule: "Duration under 1 minute", n: cl.zero_or_negative_duration },
    { rule: "Zero distance", n: cl.zero_distance },
    { rule: "Implied speed over 60 mph", n: cl.implausible_speed_gt_60mph },
    { rule: "Missing pickup or dropoff zone", n: cl.missing_zone },
    { rule: "<b>Kept</b>", n: cl.rows_out },
  ], [{ key: "rule", label: "Rule" }, { key: "n", label: "Rows", num: true, d: 0 }]);
  const sp = r.split_sizes;
  const spans = [["fit", "Mar 1–14"], ["tune", "Mar 15–20"], ["calibrate", "Mar 21–24"], ["test", "Mar 25–31"]];
  plot("split", spans.map(([k, d], i) => ({ type: "bar", orientation: "h", name: `${k} (${d})`, y: ["rides"], x: [sp[k]],
    text: [`${k}<br>${sp[k]}`], textposition: "inside", marker: { color: ["#d9b89c", "#c0703a", "#8f5a3a", "#2f2a25"][i] } })),
  { barmode: "stack", showlegend: true, xaxis: { title: "rides, in time order" }, yaxis: { visible: false }, legend: { y: -0.6 } });

  // ---------- Modeling
  const best = r.leaderboard.findIndex((m) => m.champion);
  table("board", r.leaderboard, [
    { key: "model", label: "Model" }, { key: "mae_min", label: "MAE (min)", num: true, d: 2 },
    { key: "median_ae_min", label: "Median AE", num: true, d: 2 }, { key: "rmsle", label: "RMSLE", num: true },
    { key: "r2", label: "R²", num: true }], { best });
  const t = r.autoresearch.trials;
  plot("trials", [
    { type: "scatter", mode: "markers", name: "trial", x: t.map((d) => d.trial), y: t.map((d) => d.tune_rmsle),
      marker: { size: 9, color: t.map((d) => (d.accepted ? Shell.css("--accent") : "#c9c2b3")) }, text: t.map((d) => JSON.stringify(d.params)), hoverinfo: "text+y" },
    { type: "scatter", mode: "lines", line: { shape: "hv", width: 2 }, name: "best so far", x: t.map((d) => d.trial), y: t.map((d) => d.best_so_far) },
  ], { xaxis: { title: "trial" }, yaxis: { title: "RMSLE (tune week)" } });
  document.getElementById("bestparams").innerHTML = "Winning config: " + Object.entries(r.autoresearch.best_params).map(([k, v]) => `<code>${k}=${v}</code>`).join(" ");
  const imp = r.importance.slice(0, 10).reverse();
  plot("imp", [{ type: "bar", orientation: "h", y: imp.map((d) => d.feature), x: imp.map((d) => d.importance), error_x: { type: "data", array: imp.map((d) => d.std) }, marker: { color: Shell.css("--accent") } }],
    { xaxis: { title: "RMSE increase when shuffled (log scale)" }, margin: { l: 120 } });

  // ---------- Evaluation
  const lv = ["80", "90", "95"];
  plot("coverage", [
    { type: "bar", name: "target", x: lv.map((l) => `${l}% range`), y: lv.map((l) => +l), marker: { color: "#d8d2c4" } },
    { type: "bar", name: "achieved on test", x: lv.map((l) => `${l}% range`), y: lv.map((l) => r.intervals[l].coverage * 100), marker: { color: Shell.css("--accent") },
      text: lv.map((l) => `${fmt(r.intervals[l].coverage * 100, 1)}%<br>±width ${fmt(r.intervals[l].median_width_min, 1)} min`), textposition: "outside" },
  ], { barmode: "group", yaxis: { range: [0, 110], title: "% of rides inside range" } });
  const tr = r.test_residuals;
  plot("pva", [{ type: "scattergl", mode: "markers", x: tr.actual, y: tr.pred, marker: { size: 5, opacity: 0.5, color: Shell.css("--accent") }, name: "rides" },
    { type: "scatter", mode: "lines", x: [0, 80], y: [0, 80], line: { dash: "dot", color: "#888" }, name: "perfect" }],
  { xaxis: { title: "actual minutes", range: [0, 80] }, yaxis: { title: "predicted minutes", range: [0, 80] } });
  const slice = (id, rows, key) => table(id, rows, [{ key, label: "Slice" }, { key: "n", label: "n", num: true, d: 0 }, { key: "mae", label: "MAE (min)", num: true, d: 2 }]);
  slice("sl_b", r.slices.pickup_borough, "pickup_borough");
  slice("sl_h", r.slices.hour_bucket, "hour_bucket");
  slice("sl_d", r.slices.distance_bucket, "distance_bucket");
  const L = r.leak_demo;
  document.getElementById("leak").innerHTML = `
    <p>Same algorithm, plus <code>${L.features_added.join(", ")}</code>:</p>
    <table class="data"><tr><th></th><th style="text-align:right">MAE</th><th style="text-align:right">R²</th></tr>
    <tr><td>Honest champion</td><td class="n">${fmt(champ.mae_min)} min</td><td class="n">${fmt(champ.r2, 3)}</td></tr>
    <tr><td><span class="pill bad">leaky</span> with post-trip fields</td><td class="n">${fmt(L.mae_min)} min</td><td class="n">${fmt(L.r2, 3)}</td></tr></table>
    <div class="note bad" style="margin-top:10px">The leaky model looks ${fmt(champ.mae_min / L.mae_min, 1)}× better offline and is useless in production: the fare does not exist until the ride is over. A suspiciously large jump in validation score is the most common symptom of leakage.</div>`;
  plot("drift", [{ type: "bar", x: r.drift.map((d) => d.feature), y: r.drift.map((d) => d.psi),
    marker: { color: r.drift.map((d) => (d.psi > 0.25 ? "#b23b3b" : d.psi > 0.1 ? "#b7791f" : "#2f7a4b")) }, text: r.drift.map((d) => fmt(d.psi, 3)), textposition: "outside" }],
  { yaxis: { title: "PSI", range: [0, Math.max(0.3, ...r.drift.map((d) => d.psi * 1.3))] } });

  // ---------- Estimator
  const opt = await api("options");
  const zoneOpts = opt.zones.map(([z, b]) => `<option value="${z}">${z} · ${b}</option>`).join("");
  pz.innerHTML = zoneOpts; dz.innerHTML = zoneOpts;
  pz.value = "Midtown Center"; dz.value = "JFK Airport"; dow.value = 4;
  const run = async () => {
    hourv.textContent = `${hour.value}:00`;
    const body = { pickup_zone: pz.value, dropoff_zone: dz.value, hour: +hour.value, dow: +dow.value, color: color.value, passengers: 1 };
    if (dist.value) body.distance = +dist.value;
    const p = await api("predict", body);
    const [lo, hi] = p.interval["90"];
    kpis("est", [
      { label: "Estimated ride", value: `${fmt(p.minutes, 0)} min`, sub: `${p.pickup_borough} → ${p.dropoff_borough}` },
      { label: "90% range", value: `${fmt(lo, 0)}–${fmt(hi, 0)}`, sub: `80%: ${fmt(p.interval["80"][0], 0)}–${fmt(p.interval["80"][1], 0)} min` },
      { label: "Route distance", value: `${fmt(p.distance, 1)} mi`, sub: p.distance_source },
    ]);
    const h = [...Array(24).keys()];
    plot("hourly", [
      { x: h, y: p.by_hour.hi, mode: "lines", line: { width: 0 }, showlegend: false, hoverinfo: "skip" },
      { x: h, y: p.by_hour.lo, mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: "rgba(192,112,58,.18)", name: "90% range" },
      { x: h, y: p.by_hour.minutes, mode: "lines+markers", name: "estimate", line: { color: Shell.css("--accent"), width: 3 } },
      { x: [+hour.value], y: [p.minutes], mode: "markers", marker: { size: 16, color: "#2f2a25", symbol: "diamond" }, name: "your pickup" },
    ], { xaxis: { title: "pickup hour", dtick: 2 }, yaxis: { title: "minutes", rangemode: "tozero" } });
  };
  ["pz", "dz", "dow", "hour", "dist", "color"].forEach((id) => document.getElementById(id).addEventListener("input", run));
  run();
})();
