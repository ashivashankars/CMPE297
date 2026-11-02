const { api, plot, kpis, table, fmt } = Shell;
const pct = (v, d = 1) => `${fmt(v * 100, d)}%`;
const itemset = (a) => a.map((x) => `<code>${x}</code>`).join(" + ");

(async () => {
  await Shell.init();
  const r = await api("report");
  const E = r.evaluation, B = E.leaderboard;
  const champ = B.find((b) => b.model.startsWith("Item")), pop = B.find((b) => b.model.startsWith("Most"));

  kpis("kpis", [
    { label: "Baskets", value: fmt(r.n_baskets, 0), sub: `${r.n_items} products · avg ${fmt(r.eda.avg_basket, 1)} items` },
    { label: "Rules that hold up", value: `${E.rules_hold_up} / ${E.rules_mined}`, sub: "out-of-sample lift > 1, FDR < 5%" },
    { label: "Champion hit rate @5", value: pct(champ["hit_rate@5"]), sub: `vs ${pct(pop["hit_rate@5"])} best-sellers` },
    { label: "Long-tail hits @10", value: `${fmt(champ["longtail_hit_rate@10"] / pop["longtail_hit_rate@10"], 1)}×`, sub: "co-occurrence vs best-sellers" },
  ]);

  // ---------- Data
  const top = [...r.eda.top_items].reverse();
  plot("top", [{ type: "bar", orientation: "h", y: top.map((t) => t[0]), x: top.map((t) => t[1] * 100), marker: { color: Shell.css("--accent") } }],
    { xaxis: { title: "% of baskets" }, yaxis: { automargin: true }, margin: { l: 10 } });
  plot("sizes", [{ type: "bar", x: r.eda.basket_sizes.map((d) => d[0]), y: r.eda.basket_sizes.map((d) => d[1]), marker: { color: Shell.css("--accent") } }],
    { xaxis: { title: "items in basket", range: [0, 25] }, yaxis: { title: "baskets" }, margin: { t: 6 } });
  plot("tail", [{ x: r.eda.item_rank_support.map((_, i) => i + 1), y: r.eda.item_rank_support.map((v) => v * 100), mode: "lines", line: { color: Shell.css("--accent"), width: 3 } }],
    { xaxis: { title: "product rank" }, yaxis: { title: "% of baskets", type: "log" }, margin: { t: 6 } });

  // ---------- Mining (live)
  const remine = async () => {
    sv.textContent = (+ms.value).toFixed(3); cv.textContent = (+mc.value).toFixed(2); lv.textContent = (+ml.value).toFixed(1);
    const m = await api("mine", { min_support: +ms.value, min_confidence: +mc.value, min_lift: +ml.value, algorithm: algo.value });
    mstat.innerHTML = `<b class="num">${m.n_rules}</b> rules in <b class="num">${fmt(m.seconds * 1000, 0)} ms</b> on ${fmt(r.n_train, 0)} training baskets`;
    table("mined", m.rules, [{ label: "If basket has", render: (x) => itemset(x.antecedents) }, { label: "→ also buys", render: (x) => itemset(x.consequents) },
      { key: "support", label: "Supp.", num: true }, { key: "confidence", label: "Conf.", num: true }, { key: "lift", label: "Lift", num: true, d: 2 }]);
  };
  let timer; ["ms", "mc", "ml", "algo"].forEach((id) => document.getElementById(id).addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(remine, 150); }));
  remine();
  const bn = r.benchmark;
  plot("bench", [
    { type: "bar", name: "Apriori", x: bn.map((b) => b.min_support), y: bn.map((b) => b.apriori_sec * 1000) },
    { type: "bar", name: "FP-Growth", x: bn.map((b) => b.min_support), y: bn.map((b) => b.fpgrowth_sec * 1000), text: bn.map((b) => `${b.fpgrowth_itemsets} sets${b.identical ? " ✓" : " ✗"}`), textposition: "outside" },
  ], { barmode: "group", xaxis: { title: "min support", type: "category" }, yaxis: { title: "ms" } });
  const sw = r.sweep, sups = [...new Set(sw.map((s) => s.min_support))], confs = [...new Set(sw.map((s) => s.min_confidence))];
  plot("sweep", [{ type: "heatmap", x: confs.map(String), y: sups.map(String), z: sups.map((s) => confs.map((c) => sw.find((d) => d.min_support === s && d.min_confidence === c)["val_hit_rate@5"] * 100)),
    text: sups.map((s) => confs.map((c) => { const d = sw.find((q) => q.min_support === s && q.min_confidence === c); return `${fmt(d["val_hit_rate@5"] * 100, 1)}%<br>${d.n_rules} rules`; })),
    texttemplate: "%{text}", colorscale: [[0, "#f3f0e8"], [1, "#3f8f8a"]], showscale: false }],
  { xaxis: { title: "min confidence", type: "category" }, yaxis: { title: "min support", type: "category" } });

  // ---------- Evaluation
  kpis("evkpis", B.map((b) => ({ label: b.model, value: pct(b["hit_rate@5"]), sub: `@10 ${pct(b["hit_rate@10"])} · long-tail @10 ${pct(b["longtail_hit_rate@10"])}` })));
  const R = r.rules;
  plot("holdout", [true, false].map((ok) => {
    const rs = R.filter((x) => x.holds_up === ok);
    return { type: "scatter", mode: "markers", name: ok ? "holds up" : "fails out-of-sample", x: rs.map((x) => x.lift), y: rs.map((x) => x.test_lift),
      text: rs.map((x) => `${x.antecedents.join(" + ")} → ${x.consequents}<br>q=${x.q_value.toExponential(1)}`),
      marker: { size: 7, opacity: 0.7, color: ok ? Shell.css("--accent") : "#c9c2b3" } };
  }).concat([{ x: [1, 4.5], y: [1, 4.5], mode: "lines", line: { dash: "dot", color: "#888" }, name: "same lift" }]),
  { xaxis: { title: "lift on training baskets" }, yaxis: { title: "lift on held-out baskets" },
    shapes: [{ type: "line", x0: 0.8, x1: 5, y0: 1, y1: 1, line: { color: "#b23b3b", width: 1 } }] });
  table("board", B, [{ key: "model", label: "Recommender" }, { key: "hit_rate@5", label: "Hit @5", num: true }, { key: "hit_rate@10", label: "Hit @10", num: true }, { key: "longtail_hit_rate@10", label: "Long-tail @10", num: true }],
    { best: B.indexOf(champ) });
  plot("boardplot", ["hit_rate@5", "longtail_hit_rate@10"].map((k) => ({ type: "bar", name: k.replace("_", " "), x: B.map((b) => b.model.replace(" (", "<br>(")), y: B.map((b) => b[k] * 100) })),
    { barmode: "group", yaxis: { title: "%" } });

  // ---------- Graph
  const G = r.graph, nodes = Object.fromEntries(G.nodes.map((n) => [n.id, n]));
  const maxL = Math.max(...G.edges.map((e) => e.lift));
  const edgeTraces = G.edges.map((e) => ({ type: "scatter", mode: "lines", x: [nodes[e.a].x, nodes[e.b].x], y: [nodes[e.a].y, nodes[e.b].y], hoverinfo: "skip", showlegend: false,
    line: { width: 1 + 3 * (e.lift - 1) / (maxL - 1), color: `rgba(63,143,138,${0.25 + 0.6 * (e.lift - 1) / (maxL - 1)})` } }));
  const arrows = G.edges.map((e) => ({ x: nodes[e.b].x, y: nodes[e.b].y, ax: nodes[e.a].x, ay: nodes[e.a].y, xref: "x", yref: "y", axref: "x", ayref: "y", showarrow: true, arrowhead: 2, arrowsize: 1, arrowwidth: 1, arrowcolor: "rgba(63,143,138,.5)", standoff: 10, text: "" }));
  plot("graph", [...edgeTraces, { type: "scatter", mode: "markers+text", x: G.nodes.map((n) => n.x), y: G.nodes.map((n) => n.y), text: G.nodes.map((n) => n.id), textposition: "top center",
    textfont: { size: 11 }, marker: { size: G.nodes.map((n) => 8 + Math.sqrt(n.support) * 70), color: "#fffdf8", line: { width: 2, color: Shell.css("--accent") } },
    hovertext: G.nodes.map((n) => `${n.id}: ${fmt(n.support * 100, 1)}% of baskets, ${n.degree} links`), hoverinfo: "text", showlegend: false }],
  { xaxis: { visible: false }, yaxis: { visible: false }, annotations: arrows, margin: { l: 10, r: 10, t: 10, b: 10 } });

  // ---------- Checkout
  const it = await api("items");
  itemlist.innerHTML = it.items.map((i) => `<option value="${i}">`).join("");
  const cart = new Set(["whipped/sour cream", "butter"]);
  const draw = async () => {
    document.getElementById("cart").innerHTML = [...cart].map((i) => `<span class="chip on" data-i="${i}">${i} ✕</span>`).join("") || '<span class="muted">empty: add something</span>';
    document.getElementById("popular").innerHTML = it.popular.filter((i) => !cart.has(i)).slice(0, 16).map((i) => `<span class="chip" data-i="${i}">+ ${i}</span>`).join("");
    document.querySelectorAll("#cart .chip").forEach((c) => c.onclick = () => { cart.delete(c.dataset.i); draw(); });
    document.querySelectorAll("#popular .chip").forEach((c) => c.onclick = () => { cart.add(c.dataset.i); draw(); });
    const rec = await api("recommend", { items: [...cart] });
    const mx = Math.max(...rec.co_occurrence.map((x) => x.score), 1e-9);
    document.getElementById("rec_co").innerHTML = rec.co_occurrence.map((x, i) => `
      <div style="display:flex;align-items:center;gap:10px;margin:6px 0"><span class="num muted" style="width:18px">${i + 1}</span>
      <span style="flex:0 0 46%">${x.item}</span><div style="flex:1;background:#eee9de;border-radius:4px;height:10px"><div style="width:${(x.score / mx) * 100}%;height:10px;border-radius:4px;background:var(--accent)"></div></div>
      <span class="num" style="width:52px;text-align:right">${fmt(x.score * 100, 1)}%</span></div>`).join("") + '<p class="muted" style="font-size:.85rem">Score = average P(item | each cart item) from training baskets.</p>';
    document.getElementById("rec_rules").innerHTML = rec.rules.map((x) => `<div style="margin:8px 0"><b>${x.item}</b><br>
      <span class="muted" style="font-size:.85rem">${x.confidence === null ? "no rule fires: back-filled with a best-seller" : `because ${itemset(x.because)} · conf ${pct(x.confidence, 0)} · lift ${fmt(x.lift, 2)}`}</span></div>`).join("");
  };
  search.addEventListener("change", () => { if (it.items.includes(search.value)) { cart.add(search.value); search.value = ""; draw(); } });
  draw();
})();
