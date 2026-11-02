const { api, plot, kpis, table, fmt } = Shell;
const VCOL = ["#8a6aa8", "#c9c2b3", "#3f8f8a"];
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
const show = (s) => esc(s).replace(/\n/g, "↵\n").replace(/ /g, "·");
const shade = (p) => `rgba(138,106,168,${0.08 + 0.55 * (1 - p)})`; // low probability = darker
const tip = document.getElementById("tip");
const hover = (el, html) => {
  el.onmousemove = (e) => { tip.style.display = "block"; tip.style.left = `${e.clientX + 12}px`; tip.style.top = `${e.clientY + 12}px`; tip.innerHTML = html; };
  el.onmouseleave = () => (tip.style.display = "none");
};

let R;
const draw = async () => {
  R = await api("report");
  const main = R.main, prog = R.progress?.main || [], last = prog[prog.length - 1];
  const val = main ? main.final_val_loss : last?.val_loss;
  const params = main?.params ?? 2755008;
  const bigram = R.baselines.bigram;
  kpis("kpis", [
    { label: "Parameters", value: `${fmt(params / 1e6, 2)}M`, sub: "6 layers · 6 heads · d=192" },
    { label: "Val perplexity", value: val ? fmt(Math.exp(val), 1) : "…", sub: `bigram model: ${fmt(Math.exp(bigram), 1)}` },
    { label: "Val loss", value: val ? fmt(val, 3) : "…", sub: `nats/token · bigram ${fmt(bigram, 3)}` },
    { label: "Status", value: R.status === "done" ? "trained" : "training", sub: `serving checkpoint @ step ${R.serving_step ?? "—"}` },
  ]);
  const c = R.corpus;
  table("corpus", [
    { k: "Characters (train / val)", v: `${fmt(c.train_chars, 0)} / ${fmt(c.val_chars, 0)}` },
    { k: "Tokens (train / val)", v: `${fmt(c.train_tokens, 0)} / ${fmt(c.val_tokens, 0)}` },
    { k: "Compression", v: `${fmt(c.chars_per_token, 2)} chars per token` },
    { k: "Vocabulary", v: `${R.tokenizer.vocab_size} = 256 bytes + ${R.tokenizer.vocab_size - 256} merges` },
    { k: "Tokenizer training time", v: `${fmt(c.tokenizer_train_sec, 1)} s (train split only)` },
    { k: "Unigram / bigram val loss", v: `${fmt(R.baselines.unigram, 3)} / ${fmt(R.baselines.bigram, 3)} nats` },
  ], [{ key: "k", label: "" }, { key: "v", label: "" }]);
  merges.innerHTML = R.tokenizer.first_merges.map((m) => `<span class="tokchip">${show(m)}</span>`).join("");
  longest.innerHTML = R.tokenizer.longest_tokens.map((m) => `<span class="tokchip">${show(m)}</span>`).join("");

  // training curves
  const H = main?.history || prog;
  if (H.length) {
    const base = (y, name, dash) => ({ x: [0, H[H.length - 1].step], y: [y, y], mode: "lines", name, line: { dash, color: "#a8a293", width: 1.5 } });
    plot("loss", [
      { x: H.map((h) => h.step), y: H.map((h) => h.train_loss), name: "train", mode: "lines", line: { color: "#c9b8dc", width: 3 } },
      { x: H.map((h) => h.step), y: H.map((h) => h.val_loss), name: "validation (unseen text)", mode: "lines+markers", line: { color: Shell.css("--accent"), width: 3 } },
      base(R.baselines.bigram, "bigram baseline", "dash"), base(R.baselines.unigram, "unigram baseline", "dot"),
    ], { xaxis: { title: "optimizer step" }, yaxis: { title: "loss", range: [Math.min(...H.map((h) => h.train_loss)) - 0.2, 6.4] } });
    plot("lr", [{ x: H.map((h) => h.step), y: H.map((h) => h.lr), mode: "lines", line: { color: Shell.css("--accent"), width: 3, shape: "spline" } }], { xaxis: { title: "step" }, yaxis: { title: "learning rate" } });
    const lastH = H[H.length - 1];
    lossnote.textContent = `Generalization gap at step ${lastH.step}: ${fmt(lastH.val_loss - lastH.train_loss, 3)} nats. ${lastH.val_loss - lastH.train_loss > 0.25 ? "The model is starting to memorize; more data or more dropout would help." : "Small gap: no meaningful overfitting yet."}`;
    kpis("trkpis", [
      { label: "Steps", value: fmt(lastH.step, 0), sub: `${fmt(lastH.step * 32 * 128 / 1e6, 1)}M tokens seen` },
      { label: "Wall clock", value: `${fmt(lastH.elapsed_sec / 60, 1)} min`, sub: "2 CPU cores, no GPU" },
      { label: "Val loss drop", value: fmt(H[0].val_loss - lastH.val_loss, 2), sub: `from ${fmt(H[0].val_loss, 2)} (≈ ln ${R.tokenizer.vocab_size} = random)` },
      { label: "vs bigram", value: `${fmt((1 - Math.exp(lastH.val_loss) / Math.exp(bigram)) * 100, 0)}%`, sub: "lower perplexity" },
    ]);
  }
  if (R.learning_snapshots) snaps.innerHTML = R.learning_snapshots.map((s) => `<div><h3>${s.label}</h3><div class="gen"><span class="prompt">${esc(s.text)}</span></div></div>`).join("");

  // ablation (finished runs from report, in-progress runs from progress.json)
  const ab = R.ablation?.length ? Object.fromEntries(R.ablation.map((a) => [a.variant, a.history])) : {};
  Object.entries(R.progress?.ablation || {}).forEach(([k, v]) => (ab[k] ??= v));
  const names = Object.keys(ab);
  if (names.length) {
    plot("abl", names.map((n, i) => ({ x: ab[n].map((h) => h.step), y: ab[n].map((h) => h.val_loss), name: n, mode: "lines+markers", line: { color: VCOL[i], width: 3 } })),
      { xaxis: { title: "step" }, yaxis: { title: "validation loss" }, legend: { y: -0.3 } });
    const rows = (R.ablation || []).map((a) => ({ ...a, ppl: Math.exp(a.final_val_loss) }));
    if (rows.length) {
      const bestI = rows.reduce((b, r, i) => (r.final_val_loss < rows[b].final_val_loss ? i : b), 0);
      table("abltable", rows, [{ key: "variant", label: "Variant" }, { key: "params", label: "Params", num: true, d: 0 },
        { key: "final_val_loss", label: "Val loss", num: true }, { key: "ppl", label: "Perplexity", num: true, d: 1 }, { key: "sec_per_step", label: "s/step", num: true, d: 2 }], { best: bestI });
      if (rows.length === 3) {
        const [m, nope, g2] = rows;
        ablnote.innerHTML = `<div class="note">${m.final_val_loss < g2.final_val_loss
          ? `Modern primitives win: ${fmt(g2.final_val_loss - m.final_val_loss, 3)} nats lower validation loss than the GPT-2 block at the same step count and near-identical size, for ~${fmt((m.sec_per_step / g2.sec_per_step - 1) * 100, 0)}% more compute per step (SwiGLU's third matrix).`
          : `At this tiny budget the GPT-2 block is ahead by ${fmt(m.final_val_loss - g2.final_val_loss, 3)} nats: modern primitives don't automatically win at small scale and short training.`}
          Removing position information (no RoPE) costs ${fmt(nope.final_val_loss - m.final_val_loss, 3)} nats: word order matters. Caveat: one seed, ${R.ablation[0].history.at(-1).step} steps; differences under ~0.03 nats are within noise.</div>`;
      }
    } else abltable.innerHTML = '<p class="muted">Ablation runs in progress…</p>';
  } else abltable.innerHTML = '<p class="muted">Ablation runs start after the main model finishes.</p>';
  return R.status;
};

(async () => {
  await Shell.init();
  arch.innerHTML = `<div>Text → byte-level BPE → token ids (vocab 512)</div><div>Token embedding (512 × 192) <span class="muted">· no position embedding: RoPE inside attention</span></div>
    <div class="blk"><b>× 6 transformer blocks (pre-norm residual)</b>
      <div class="new">RMSNorm → causal self-attention, 6 heads × 32 dims, <b>RoPE</b> on q, k</div><div>+ residual</div>
      <div class="new">RMSNorm → <b>SwiGLU</b> MLP (192 → 512 → 192)</div><div>+ residual</div></div>
    <div>Final RMSNorm → LM head (weights <b>tied</b> to embedding) → softmax over 512 tokens</div>`;
  const status = await draw();
  if (status !== "done") setInterval(draw, 15000); // live dashboard while training

  // tokenizer
  const tk = async () => {
    const t = await api("tokenize", { prompt: tk_in.value });
    tk_out.innerHTML = t.tokens.map((x, i) => `<span class="tokchip" style="background:hsl(${(i * 47) % 360},55%,90%)" title="id ${x.id}">${show(x.piece)}</span>`).join("");
    tk_stats.textContent = `${t.chars} characters → ${t.n_tokens} tokens (${fmt(t.chars / t.n_tokens, 2)} chars/token). · = space, ↵ = newline.`;
  };
  tk_in.addEventListener("input", tk); tk();

  // playground
  const lab = () => { tv.textContent = temp.value; kv.textContent = topk.value === "0" ? "off" : topk.value; pv.textContent = topp.value; nv.textContent = maxn.value; };
  [temp, topk, topp, maxn].forEach((e) => e.addEventListener("input", lab)); lab();
  const P = ["ROMEO:\n", "JULIET:\nO Romeo,", "First Citizen:\nWe are", "KING RICHARD III:\nNow is the", "MENENIUS:\n"];
  prompts.innerHTML = P.map((p) => `<span class="chip" data-p="${esc(p)}">${esc(p.split("\n")[0])}</span>`).join("");
  prompts.querySelectorAll(".chip").forEach((c) => (c.onclick = () => { pr.value = c.dataset.p.replace(/&lt;/g, "<").replace(/&amp;/g, "&"); gen_(); }));
  const nextTok = async () => {
    const n = await api("next", { prompt: pr.value });
    const c = [...n.candidates].reverse();
    plot("nxt", [{ type: "bar", orientation: "h", y: c.map((x) => `"${show(x.piece)}"`), x: c.map((x) => x.p * 100), marker: { color: Shell.css("--accent") }, text: c.map((x) => `${fmt(x.p * 100, 1)}%`), textposition: "outside" }],
      { xaxis: { title: "probability %" }, yaxis: { automargin: true, tickfont: { family: "monospace" } }, margin: { l: 10 },
        title: { text: `entropy ${fmt(n.entropy_nats, 2)} nats ≈ choosing among ${fmt(n.perplexity_of_choice, 1)} tokens`, font: { size: 12 } } });
  };
  const gen_ = async () => {
    go.disabled = true; go.textContent = "Generating…";
    const g = await api("generate", { prompt: pr.value, max_new: +maxn.value, temperature: +temp.value, top_k: +topk.value, top_p: +topp.value, seed: +seed.value });
    gen.innerHTML = `<span class="prompt">${esc(g.prompt)}</span>`;
    g.tokens.forEach((t) => {
      const s = document.createElement("span"); s.className = "tok"; s.textContent = t.piece; s.style.background = shade(t.p);
      hover(s, `p(chosen) = ${fmt(t.p * 100, 1)}%<br>${t.alts.map((a) => `${fmt(a.p * 100, 1).padStart(5)}%  ${show(a.piece)}`).join("<br>")}`);
      gen.appendChild(s);
    });
    const mean = g.tokens.reduce((a, t) => a + Math.log(t.p), 0) / g.tokens.length;
    genstat.textContent = `${g.tokens.length} tokens from checkpoint step ${g.step}. Mean log-prob ${fmt(mean, 2)} (perplexity of this sample under the model: ${fmt(Math.exp(-mean), 1)}). Darker = the model was less sure.`;
    go.disabled = false; go.textContent = "Generate";
    nextTok();
  };
  go.onclick = gen_; gen_();

  // attention
  at_layer.innerHTML = [...Array(6).keys()].map((i) => `<option value="${i}">Layer ${i + 1}</option>`).join("");
  at_head.innerHTML = [...Array(6).keys()].map((i) => `<option value="${i}">Head ${i + 1}</option>`).join("") + '<option value="avg">Average of heads</option>';
  let A;
  const drawAtt = () => {
    const L = A.layers[+at_layer.value];
    const M = at_head.value === "avg" ? L[0].map((row, i) => row.map((_, j) => L.reduce((s, h) => s + h[i][j], 0) / L.length)) : L[+at_head.value];
    const labels = A.pieces.map((p, i) => `${i}:${show(p)}`);
    plot("att", [{ type: "heatmap", z: M.map((r, i) => r.map((v, j) => (j > i ? null : v))), x: labels, y: labels, colorscale: [[0, "#fbfaf6"], [1, "#5b3f78"]], zmin: 0, zmax: 1, hoverongaps: false }],
      { yaxis: { autorange: "reversed", tickfont: { family: "monospace", size: 10 } }, xaxis: { tickangle: -60, tickfont: { family: "monospace", size: 10 } }, margin: { l: 90, b: 100 } });
  };
  at_go.onclick = async () => { A = await api("attention", { prompt: at_in.value }); drawAtt(); };
  [at_layer, at_head].forEach((e) => e.addEventListener("change", () => A && drawAtt()));
  at_head.value = "avg"; at_go.onclick();
})();
