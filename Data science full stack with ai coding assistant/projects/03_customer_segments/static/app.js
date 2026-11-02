const { api, plot, kpis, table, fmt } = Shell;
const SEG = ["#c0703a", "#8a6aa8", "#7d8a6a", "#2f5d50", "#5b6fa8", "#b7791f", "#a64d5d", "#3f8f8a", "#999", "#555"];

(async () => {
  await Shell.init();
  const r = await api("report");
  const P = r.points, C = r.chosen, H = r.holdout;
  const name = (c) => r.profiles[c].persona;

  kpis("kpis", [
    { label: "Segments", value: C.k, sub: `${C.algo} on ${C.features}` },
    { label: "Silhouette", value: fmt(C.silhouette, 3), sub: "> 0.5 = well separated" },
    { label: "Bootstrap stability", value: fmt(C.stability, 3), sub: "mean ARI over resamples" },
    { label: "Holdout silhouette", value: fmt(H.holdout_silhouette, 3), sub: `${H.n_holdout} unseen customers` },
  ]);

  // ---------- Data
  ["age", "income", "score"].forEach((f) => plot(`h_${f}`, [{ type: "histogram", x: P.map((p) => p[f]), nbinsx: 18, marker: { color: Shell.css("--accent") } }], { bargap: 0.05, margin: { t: 6, b: 30 } }));
  plot("raw", [{ type: "scatter", mode: "markers", x: P.map((p) => p.income), y: P.map((p) => p.score), marker: { size: 8, color: "#6b675e", opacity: 0.7 }, text: P.map((p) => `${p.gender}, ${p.age}`) }],
    { xaxis: { title: "income (k$)" }, yaxis: { title: "spending score" } });
  plot("corr", [{ type: "heatmap", z: r.eda.corr, x: r.eda.corr_cols, y: r.eda.corr_cols, zmin: -1, zmax: 1, colorscale: "RdBu", reversescale: true,
    text: r.eda.corr.map((row) => row.map((v) => fmt(v, 2))), texttemplate: "%{text}" }], { yaxis: { autorange: "reversed" }, margin: { l: 70 } });

  // ---------- Preparation
  const T = r.tournament;
  const fsRows = [...new Set(T.map((t) => t.features))].map((f) => {
    const rows = T.filter((t) => t.features === f && t.stability !== null);
    const b = rows.reduce((a, c) => (c.silhouette > a.silhouette ? c : a));
    return { f, best: `${b.algo}, k=${b.k}`, sil: b.silhouette, stab: b.stability };
  });
  table("fsets", fsRows, [{ key: "f", label: "Feature set" }, { key: "best", label: "Best config" }, { key: "sil", label: "Silhouette", num: true }, { key: "stab", label: "Stability", num: true }],
    { best: fsRows.findIndex((x) => x.f === C.features) });

  // ---------- Modeling
  const K = r.k_selection, ks = K.map((d) => d.k);
  const norm = (arr, invert) => { const mn = Math.min(...arr), mx = Math.max(...arr); return arr.map((v) => (invert ? (mx - v) : (v - mn)) / (mx - mn)); };
  plot("ksel", [
    { x: ks, y: norm(K.map((d) => d.inertia), true), name: "elbow (1 − inertia)", mode: "lines+markers" },
    { x: ks, y: norm(K.map((d) => d.silhouette)), name: "silhouette ↑", mode: "lines+markers" },
    { x: ks, y: norm(K.map((d) => d.calinski_harabasz)), name: "Calinski-Harabasz ↑", mode: "lines+markers" },
    { x: ks, y: norm(K.map((d) => d.davies_bouldin), true), name: "Davies-Bouldin ↓ (inverted)", mode: "lines+markers" },
    { x: ks, y: norm(K.map((d) => d.gmm_bic), true), name: "GMM BIC ↓ (inverted)", mode: "lines+markers", line: { dash: "dot" } },
  ], { xaxis: { title: "k", dtick: 1 }, yaxis: { title: "normalized score (higher = better)" },
    shapes: [{ type: "line", x0: C.k, x1: C.k, y0: 0, y1: 1, line: { color: "#1e1d1a", dash: "dash" } }] });
  plot("stab", [{ type: "bar", x: ks, y: K.map((d) => d.stability), marker: { color: ks.map((k) => (k === C.k ? Shell.css("--accent") : "#c9c2b3")) },
    text: K.map((d) => fmt(d.stability, 2)), textposition: "outside" }], { xaxis: { title: "k", dtick: 1 }, yaxis: { title: "mean ARI", range: [0, 1.1] } });
  const algos = ["k-means", "GMM", "Ward"], fsets = [...new Set(T.map((t) => t.features))];
  const rows = fsets.flatMap((f) => algos.map((a) => `${a} | ${f}`));
  plot("tourn_heat", [{ type: "heatmap", x: ks, y: rows, z: rows.map((row) => { const [a, f] = row.split(" | "); return ks.map((k) => T.find((t) => t.algo === a && t.features === f && t.k === k)?.silhouette ?? null); }),
    colorscale: [[0, "#f3f0e8"], [1, "#5b6fa8"]], colorbar: { title: "silh." } }], { xaxis: { title: "k", dtick: 1 }, margin: { l: 10 }, yaxis: { automargin: true } });
  const top = T.filter((t) => t.stability !== null && t.min_cluster >= 8).map((t) => ({ ...t, score: t.silhouette * 0.5 + t.stability * 0.5 })).sort((a, b) => b.score - a.score).slice(0, 12);
  table("tourn_table", top, [{ key: "features", label: "Features" }, { key: "algo", label: "Algo" }, { key: "k", label: "k", num: true, d: 0 }, { key: "silhouette", label: "Silh.", num: true }, { key: "stability", label: "Stab.", num: true }], { best: 0 });

  // ---------- Evaluation
  kpis("evalkpis", [
    { label: "Algorithms agree (min ARI)", value: fmt(Math.min(...r.algo_agreement.map((a) => a.ari)), 3), sub: "k-means vs GMM vs Ward" },
    { label: "Train → holdout silhouette", value: `${fmt(H.train_silhouette, 2)} → ${fmt(H.holdout_silhouette, 2)}`, sub: "no drop = segments generalize" },
    { label: "Customers with silhouette < 0", value: P.filter((p) => p.silhouette < 0).length, sub: "would be mis-assigned" },
  ]);
  const sorted = [...P].sort((a, b) => a.cluster - b.cluster || b.silhouette - a.silhouette);
  plot("silplot", r.profiles.map((pr) => {
    const pts = sorted.filter((p) => p.cluster === pr.cluster);
    return { type: "bar", orientation: "h", name: pr.persona, y: pts.map((p) => `c${p.id}`), x: pts.map((p) => p.silhouette), marker: { color: SEG[pr.cluster] } };
  }), { bargap: 0, yaxis: { showticklabels: false, autorange: "reversed" }, xaxis: { title: "silhouette" }, legend: { y: -0.15 } });
  table("agree", r.algo_agreement, [{ key: "a", label: "Algorithm A" }, { key: "b", label: "Algorithm B" }, { key: "ari", label: "Adjusted Rand Index", num: true }]);
  document.getElementById("holdout").innerHTML = `<p>Fit on ${H.n_train} customers, then assign ${H.n_holdout} customers the model never saw. Holdout silhouette <b class="num">${fmt(H.holdout_silhouette, 3)}</b> vs train <b class="num">${fmt(H.train_silhouette, 3)}</b>; the holdout labels match a full-data fit with ARI <b class="num">${fmt(H.holdout_ari_vs_full_fit, 3)}</b>.</p>
    <div class="note">If segments were artifacts of this particular sample, held-out customers would land in fuzzy, overlapping regions and their silhouette would drop.</div>`;

  // ---------- Segments
  const segTraces = (x, y, extra = {}) => r.profiles.map((pr) => {
    const pts = P.filter((p) => p.cluster === pr.cluster);
    return { type: "scatter", mode: "markers", name: pr.persona, x: pts.map(x), y: pts.map(y), marker: { size: 9, color: SEG[pr.cluster], line: { width: 1, color: "#fff" } }, text: pts.map((p) => `#${p.id} ${p.gender}, ${p.age}`), ...extra };
  });
  plot("seg", segTraces((p) => p.income, (p) => p.score), { xaxis: { title: "income (k$)" }, yaxis: { title: "spending score" }, legend: { y: -0.25 } });
  plot("seg3d", r.profiles.map((pr) => {
    const pts = P.filter((p) => p.cluster === pr.cluster);
    return { type: "scatter3d", mode: "markers", name: pr.persona, x: pts.map((p) => p.age), y: pts.map((p) => p.income), z: pts.map((p) => p.score), marker: { size: 4, color: SEG[pr.cluster] } };
  }), { scene: { xaxis: { title: "age" }, yaxis: { title: "income" }, zaxis: { title: "score" } }, margin: { l: 0, r: 0, t: 0, b: 0 }, showlegend: false });
  document.getElementById("personas").innerHTML = r.profiles.map((p) => `
    <div class="card" style="border-top:4px solid ${SEG[p.cluster]}">
      <h2 style="font-size:1.05rem">${p.persona}</h2>
      <p class="muted num" style="margin:0 0 8px">${p.size} customers · ${fmt(p.share * 100, 0)}% · age ${fmt(p.age, 0)} · $${fmt(p.income, 0)}k · score ${fmt(p.score, 0)} · ${fmt(p.male_share * 100, 0)}% male</p>
      <p style="margin:0"><b>Action:</b> ${p.action}</p></div>`).join("");

  // ---------- Classifier
  const run = async () => {
    agev.textContent = age.value; incv.textContent = inc.value; scv.textContent = sc.value;
    const a = await api("assign", { age: +age.value, income: +inc.value, score: +sc.value, is_male: +male.value });
    document.getElementById("assign").innerHTML = `<div style="display:flex;gap:16px;align-items:center">
      <div style="width:14px;height:56px;border-radius:4px;background:${SEG[a.cluster]}"></div>
      <div><h2 style="margin:0">${a.persona}</h2><p style="margin:4px 0 0"><b>Action:</b> ${a.action}</p>
      <p class="muted" style="margin:4px 0 0">${a.confidence}. Uses: ${a.features_used.join(", ")}.</p></div></div>`;
    plot("where", [...segTraces((p) => p.income, (p) => p.score, { marker: undefined }).map((t, i) => ({ ...t, marker: { size: 7, color: SEG[i], opacity: 0.35 }, showlegend: false })),
      { type: "scatter", mode: "markers", x: [+inc.value], y: [+sc.value], name: "new customer", marker: { size: 22, symbol: "star", color: SEG[a.cluster], line: { width: 2, color: "#1e1d1a" } } }],
    { xaxis: { title: "income (k$)" }, yaxis: { title: "spending score" } });
    plot("soft", [{ type: "bar", orientation: "h", y: r.profiles.map((p) => p.persona), x: a.soft_membership, marker: { color: r.profiles.map((p) => SEG[p.cluster]) },
      text: a.soft_membership.map((v) => `${fmt(v * 100, 0)}%`), textposition: "outside" }], { xaxis: { title: "P(segment)", range: [0, 1.2] }, yaxis: { automargin: true, autorange: "reversed" }, margin: { l: 10 } });
  };
  ["age", "inc", "sc", "male"].forEach((id) => document.getElementById(id).addEventListener("input", run));
  run();
})();
