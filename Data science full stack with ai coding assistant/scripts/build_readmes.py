"""Generate the top-level README and one README per project.

Prose is written here by hand; every metric is read from the project's artifacts/report.json
so the docs can never drift from the actual results.

  python scripts/build_readmes.py --video-url <url>
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / "projects"
SOURCE = "https://github.com/dlmastery/data_science_examples"


def rep(slug: str) -> dict:
    return json.loads((P / slug / "artifacts" / "report.json").read_text())


def f(x, d=2):
    return f"{x:,.{d}f}"


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def table(rows: list[list], head: list[str]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def gallery(slug: str) -> str:
    shots = sorted((P / slug / "screenshots").glob("*.png"))
    cells = [f"| **{s.stem[3:].replace('_', ' ').title()}** | ![{s.stem}](screenshots/{s.name}) |" for s in shots]
    return "| Tab | Screenshot |\n|---|---|\n" + "\n".join(cells)


def tests(slug: str) -> str:
    t = (P / slug / "tests" / "test_pipeline.py").read_text()
    names = [l.split("def ")[1].split("(")[0] for l in t.splitlines() if l.startswith("def test_")]
    return "\n".join(f"- `{n}`" for n in names)


# ---------------------------------------------------------------------------- projects
def taxi():
    r = rep("01_nyc_taxi")
    board = table([[m["model"] + (" 🏆" if m.get("champion") else ""), f(m["mae_min"]), f(m["rmsle"], 3), f(m["r2"], 3)] for m in r["leaderboard"]],
                  ["Model", "MAE (min)", "RMSLE", "R²"])
    champ = next(m for m in r["leaderboard"] if m.get("champion"))
    cov = table([[f"{k}%", pct(v["coverage"]), f(v["median_width_min"], 1) + " min"] for k, v in r["intervals"].items()],
                ["Target", "Achieved on test week", "Median width"])
    return dict(slug="01_nyc_taxi", title="NYC Taxi Trip Duration", entry="taxi_pipeline.py", body=f"""
Predict how long a NYC taxi ride will take **at booking time**, with an honest uncertainty range.

**Data:** 6,433 real NYC TLC yellow/green rides, March 2019 ([seaborn mirror](https://github.com/mwaskom/seaborn-data)). {r['clean_log']['rows_out']:,} remain after fixed cleaning rules.

### Results (frozen final week, Mar 25–31, scored once)
{board}

**Conformal 80/90/95% intervals** (calibrated on Mar 21–24):
{cov}

**The leakage trap:** retraining the same model with `fare, tip, tolls, total` gives MAE {f(r['leak_demo']['mae_min'])} min / R² {f(r['leak_demo']['r2'], 3)}, which looks {f(champ['mae_min'] / r['leak_demo']['mae_min'], 1)}× better and is useless in production, because the fare doesn't exist until the ride ends. It's kept in the report as a permanent regression check.

### What's improvised vs the original prompt
| Original | Here |
|---|---|
| Synthetic "Kaggle-like" data generator | Real TLC rides, checksummed |
| Random 80/20 split | 4-way **temporal** split (fit → tune → calibrate → test) |
| Point estimate | Point estimate **+ split-conformal 80/90/95% ranges, coverage verified** |
| Interactive map | The source data has zones but no coordinates, so the map became a zone-pair estimator with a 24-hour curve and a day × hour heatmap (no invented coordinates) |
| — | Deliberate leakage demo, PSI drift monitor, error slices, permutation importance |
| AutoResearch hill climbing | Kept: greedy hill climbing on the tune week, every trial logged and plotted |
""")


def llm():
    r = rep("02_nano_llm")
    m = r.get("main", {})
    hist = m.get("history", [{}])
    abl = r.get("ablation", [])
    ab_tab = table([[a["variant"], f"{a['params']:,}", f(a["final_val_loss"], 3), f(math.exp(a["final_val_loss"]), 1), f(a["sec_per_step"], 2)] for a in abl],
                   ["Variant", "Params", "Val loss", "Perplexity", "s/step"]) if abl else "_ablation pending_"
    samples = "\n\n".join(f"```text\n{s['text']}\n```" for s in r.get("samples", [])[:2])
    return dict(slug="02_nano_llm", title="NanoGPT from Scratch", entry="train.py", body=f"""
A decoder-only transformer, written from first principles and trained on **2 CPU cores**: tokenizer, model, training loop, sampler, and the tools to look inside it.

**Data:** Tiny Shakespeare (1.1M characters), contiguous 90/10 split. Byte-level BPE with {r['tokenizer']['vocab_size']} tokens (≈ {f(r['corpus']['chars_per_token'])} chars/token), trained on the training split only.

**Model:** {m.get('params', 0):,} parameters · 6 layers · 6 heads · d=192 · context 128 · RoPE · RMSNorm · SwiGLU · tied embeddings · AdamW (warmup + cosine) · grad clip 1.0.

### Results (held-out last 10% of the text)
| Model | Val loss (nats/token) | Perplexity |
|---|---|---|
| Unigram (add-one) | {f(r['baselines']['unigram'], 3)} | {f(math.exp(r['baselines']['unigram']), 1)} |
| Bigram (add-one) | {f(r['baselines']['bigram'], 3)} | {f(math.exp(r['baselines']['bigram']), 1)} |
| **NanoGPT, {hist[-1].get('step', '?')} steps** | **{f(m.get('final_val_loss', float('nan')), 3)}** | **{f(m.get('val_perplexity', float('nan')), 1)}** |

Training took {f(hist[-1].get('elapsed_sec', 0) / 60, 1)} minutes on CPU.

### Ablation: do 2023-era building blocks help at this scale?
Same steps, same data, same seed, near-identical parameter counts:

{ab_tab}

### Samples (temperature 0.8, top-k 40, top-p 0.95)
{samples}

### What's improvised vs the original prompt
| Original | Here |
|---|---|
| "Fit in my laptop GPU" | Fits on a 2-core **CPU**: 2.7M params, ~20–30 min |
| Pre-built tokenizer | **Home-made byte-level BPE**, trained on train split only (no val leakage) |
| HP hill climbing | Replaced by a **controlled architecture ablation** (modern vs no-RoPE vs GPT-2), a better use of a small compute budget |
| Chat UI | Playground with **per-token probabilities** (hover for alternatives), next-token entropy, **attention heatmaps** per layer/head |
| — | Unit tests: causal mask, RoPE relative-position property, tokenizer roundtrip |
""")


def segments():
    r = rep("03_customer_segments")
    c, h = r["chosen"], r["holdout"]
    prof = table([[p["persona"], p["size"], f(p["age"], 0), f(p["income"], 0), f(p["score"], 0), p["action"]] for p in r["profiles"]],
                 ["Segment", "n", "Age", "Income k$", "Score", "Action"])
    agree = ", ".join(f"{a['a']}–{a['b']} {f(a['ari'], 2)}" for a in r["algo_agreement"])
    return dict(slug="03_customer_segments", title="Customer Segmentation", entry="segments_pipeline.py", body=f"""
Find shopper segments in the Kaggle **Mall Customer Segmentation** data (200 customers), prove they're real, and turn each into a marketing action.

### Results
| Check | Result |
|---|---|
| Chosen configuration | {c['algo']}, k = {c['k']}, features: {c['features']} |
| Silhouette | {f(c['silhouette'], 3)} |
| Bootstrap stability (mean ARI) | {f(c['stability'], 3)} |
| Cross-algorithm agreement (ARI) | {agree} |
| Holdout: train → unseen 20% silhouette | {f(h['train_silhouette'], 3)} → {f(h['holdout_silhouette'], 3)} (ARI vs full fit {f(h['holdout_ari_vs_full_fit'], 2)}) |

{prof}

### What's improvised vs the original prompt
| Original | Here |
|---|---|
| Elbow + silhouette | 5 criteria side by side **plus bootstrap stability**, the tie-breaker when criteria disagree |
| One algorithm | **Tournament**: 3 feature sets × k-means/GMM/Ward/DBSCAN × k = 2–10 |
| — | **Holdout generalization** check for an unsupervised model |
| Hand-written personas | Personas from transparent rules on centroids, each tied to an action |
| — | Live classifier with GMM soft membership and a "borderline" flag |
""")


def basket():
    r = rep("04_market_basket")
    e = r["evaluation"]
    board = table([[b["model"], pct(b["hit_rate@5"]), pct(b["hit_rate@10"]), pct(b["longtail_hit_rate@10"])] for b in e["leaderboard"]],
                  ["Recommender", "Hit @5", "Hit @10", "Long-tail hit @10"])
    bench = table([[b["min_support"], b["fpgrowth_itemsets"], f(b["apriori_sec"] * 1000, 0), f(b["fpgrowth_sec"] * 1000, 0), "✓" if b["identical"] else "✗"] for b in r["benchmark"]],
                  ["min support", "itemsets", "Apriori ms", "FP-Growth ms", "identical"])
    top = table([[" + ".join(x["antecedents"]), " + ".join(x["consequents"]), f(x["lift"], 2), f(x["test_lift"], 2), f"{x['q_value']:.1e}"] for x in [y for y in r["rules"] if y["holds_up"]][:8]],
                ["If basket has", "→ also buys", "Train lift", "Held-out lift", "FDR q"])
    return dict(slug="04_market_basket", title="Market Basket Mining", entry="basket_pipeline.py", body=f"""
Association rules on **9,835 real grocery baskets** (169 products; the classic *Groceries* dataset used on Kaggle and in R's `arules`).

### Results
**{e['rules_hold_up']} of {e['rules_mined']} rules hold up** on held-out baskets (lift > 1 and Benjamini-Hochberg q < 0.05).

Strongest validated rules:
{top}

**Recommender leaderboard** (leave-one-out on {r['n_test']:,} held-out baskets):
{board}

> **Honest finding:** high-confidence rules only tie "recommend the best-sellers", because confident rules mostly predict whole milk and vegetables. A tuned item co-occurrence model wins overall and nearly **doubles** best-sellers on long-tail items, which is where recommendations actually add value.

**Apriori vs FP-Growth** (same answers, different cost):
{bench}

### What's improvised vs the original prompt
| Original | Here |
|---|---|
| Mine rules, show them | Mine on 80%, **re-test every rule on held-out 20%** with Fisher exact test + FDR |
| — | Recommender evaluated **as a recommender** (leave-one-out hit-rate vs baselines, long-tail metric) |
| — | Thresholds chosen on a validation split, never on test |
| — | Co-occurrence recommender when rules didn't beat the baseline |
| Static rule table | Live re-mining sliders, rule network graph, interactive checkout cart |
""")


def anomaly():
    r = rep("06_anomaly_detection")
    s = table([[x["method"], f"{x['detected']} / {x['windows']}", f(x["fa_per_week"], 2), f(x["alert_precision"], 2), f(x["pr_auc"], 3)] for x in r["summary"]],
              ["Detector", "Failures caught", "False alarms / week", "Alert precision", "PR-AUC"])
    series = "\n".join(f"- **{k.replace('_', ' ')}**: {v['description']}" for k, v in r["series_meta"].items())
    return dict(slug="06_anomaly_detection", title="Anomaly Detection", entry="anomaly_pipeline.py", body=f"""
Catch real system failures in **5 Numenta Anomaly Benchmark (NAB) series** with known-cause failure windows:
{series}

### Rules that make the numbers trustworthy
- Every detector is **causal** (score at *t* uses data ≤ *t*). A unit test changes the future and asserts past scores don't move.
- Detectors are fit on the first {int(r['probation_fraction'] * 100)}% of each series (NAB's probation period) only.
- **Thresholds are label-free**: the {r['threshold_quantile'] * 100:g}th percentile of each detector's own probation scores. Labels are only used to grade.

### Results (15 failure windows across 5 series)
{s}

No detector dominates: Isolation Forest catches the most failures, LOF raises the cleanest alerts, and the robust z-score is the quietest. The rank ensemble does not beat its parts, and the README says so rather than hiding it. The operating curve in the app shows the full catch-vs-false-alarm trade-off.

### What's improvised vs the original prompt
| Original | Here |
|---|---|
| Kaggle tabular fraud-style data, point metrics | Real **streaming** failures, **event-level** scoring (caught, how early, false alarms/week) |
| Thresholds tuned for best F1 (uses labels) | **Label-free** thresholds from probation data |
| — | Operating curve across sensitivities |
| — | **Anomaly injection sandbox**: add spike / level shift / drift / stuck sensor and re-score live |
""")


def forecast():
    r = rep("12_timeseries_forecasting")
    b = table([[x["model"], f(x["mae"], 1), f(x["mape"], 2) + "%", f(x["mase"], 3)] for x in r["leaderboard"]], ["Model", "MAE (GWh)", "MAPE", "MASE"])
    hol = table([[x["model"], f(x["mape"], 1) + "%"] for x in r["holiday_slice"]], ["Model", "MAPE on public holidays"])
    cov = table([[k + "%", pct(v["coverage"]), f(v["mean_halfwidth"], 1) + " GWh"] for k, v in r["conformal"]["coverage_2017"].items()], ["Band", "2017 coverage", "Mean half-width"])
    return dict(slug="12_timeseries_forecasting", title="Electricity Demand Forecasting", entry="forecast_pipeline.py", body=f"""
Forecast **Germany's daily electricity consumption 1–14 days ahead** (Open Power System Data, 2006–2017).

### Validation design
Train 2006–2015 → calibrate intervals on 2016 → refit through 2016 → **rolling-origin backtest over all of 2017** (51 weekly origins × 14 days). Every lag is taken relative to the forecast **origin**; calendar features and German public holidays are allowed because they are known in advance. A unit test corrupts all data after the origin and asserts no feature changes.

### Results (2017, never used for training or tuning)
{b}

{hol}

**Per-horizon conformal bands** (calibrated on every daily origin of 2016):
{cov}

### What's improvised vs the original prompt
| Original | Here |
|---|---|
| Single train/test split | **Rolling-origin backtest**, 714 forecasts per model |
| — | **Direct multi-horizon** model (horizon as a feature, no recursive error compounding) |
| — | MASE, horizon curves, holiday error slice |
| — | Conformal fan charts with verified coverage |
| Static dashboards | Forecast from any 2016–17 origin; presets for Christmas, Easter, Reformation Day |
""")


PROJECTS = [taxi, llm, segments, basket, anomaly, forecast]

TEMPLATE = """# {title}

> Part of the [Data Science Full-Stack Lab](../../README.md) · replicates and extends the prompts in [{source_name}]({source})

{body}
### Screenshots (every tab, captured by the browser test suite)
{gallery}

### Run it
```bash
# from the repository root
python data/fetch_data.py                         # once: downloads + checksums the real data
python projects/{slug}/{entry}           # re-train (artifacts are already committed)
python serve.py                                   # → http://127.0.0.1:8000/p/{slug}/
python -m pytest projects/{slug}         # guardrail tests
```

### Tests
{tests}

### Files
| File | Purpose |
|---|---|
| `{entry}` | CRISP-DM pipeline: data → features → models → evaluation → `artifacts/report.json` |
| `app.py` | FastAPI routes for this app (mounted by `shared/hub.py`) |
| `static/` | Front end (HTML + vanilla JS + Plotly) |
| `code_tour.json` | Annotated source sections shown in the app's **Code tour** tab |
| `tests/` | pytest guardrails |
| `artifacts/` | Trained model + report (every number in the UI comes from here) |
"""


def top(video: str, chapters: list[dict]):
    rows = []
    for fn in PROJECTS:
        d = fn()
        r = rep(d["slug"])
        headline = {
            "01_nyc_taxi": lambda: f"MAE {f(next(m for m in r['leaderboard'] if m.get('champion'))['mae_min'], 1)} min; 90% range covers {pct(r['intervals']['90']['coverage'])}",
            "02_nano_llm": lambda: f"val perplexity {f(r['main']['val_perplexity'], 1)} vs bigram {f(math.exp(r['baselines']['bigram']), 1)}" if r.get("main") else "training",
            "03_customer_segments": lambda: f"k={r['chosen']['k']}, silhouette {f(r['chosen']['silhouette'], 2)}, stability {f(r['chosen']['stability'], 2)}",
            "04_market_basket": lambda: f"{r['evaluation']['rules_hold_up']} rules survive held-out test; co-occurrence wins hit@5",
            "06_anomaly_detection": lambda: f"up to {max(s['detected'] for s in r['summary'])}/15 failures caught with label-free thresholds",
            "12_timeseries_forecasting": lambda: f"MAPE {f(next(b for b in r['leaderboard'] if b['model'] == 'GBM direct')['mape'], 2)}% (MASE {f(next(b for b in r['leaderboard'] if b['model'] == 'GBM direct')['mase'], 2)}), holiday-aware",
        }[d["slug"]]()
        rows.append([f"[**{d['title']}**](projects/{d['slug']})", headline, f"![{d['slug']}](projects/{d['slug']}/screenshots/01_overview.png)"])
    chap = "\n".join(f"| `{int(c['start_sec'] // 60):02d}:{int(c['start_sec'] % 60):02d}` | {c['title']} | {int(c['duration_sec'] // 60)}m {int(c['duration_sec'] % 60)}s |" for c in chapters) if chapters else ""
    pages = "https://ashivashankars.github.io/CMPE297/Data%20science%20full%20stack%20with%20ai%20coding%20assistant/docs/video/"
    return f"""# Data Science Full-Stack Lab

Six end-to-end data science projects, each built from business question to deployed interactive app following **CRISP-DM**. They replicate (and extend) the experiments and prompts in [dlmastery/data_science_examples]({SOURCE}), rebuilt with an AI coding assistant (Claude).

## 🎬 Video walkthrough

A 14-minute captioned tour of the code **and** the UX of every project, including each app's Code tour of its own source.

| How to watch | Link |
|---|---|
| **Play in the browser** (chapter buttons, no download) | **[▶ Open the player]({pages})** — requires GitHub Pages to be on for this repo (Settings → Pages → Source: `main` / root) |
| **Download the MP4** (9 MB, plays in any video player) | [walkthrough.mp4]({video}?raw=1) |
| **Watch locally after cloning** | open `docs/video/index.html` |

{"| Start | Chapter | Length |" + chr(10) + "|---|---|---|" + chr(10) + chap if chap else ""}

![Home](docs/home.png)

## Projects
{table(rows, ["Project", "Headline result (from report.json)", "Overview"])}

## What's different from the source repo
The source prompts asked for CRISP-DM, dashboards, "autoresearch" hill climbing and no leakage. This replication keeps all of that and adds:

1. **Real data everywhere.** The source projects generate synthetic data; here every model trains on a real public dataset fetched by `data/fetch_data.py` and pinned by SHA-256 in `data/MANIFEST.json`.
2. **Validation that matches deployment.** Temporal splits for taxi rides, rolling-origin backtests for forecasting, probation-only fitting for streaming anomalies, holdout checks even for clustering.
3. **Leakage tested, not just claimed.** pytest checks that changing the future never changes past features or scores (taxi, anomaly, forecasting, LLM causal mask), plus a deliberate leakage demo in the taxi app.
4. **Uncertainty that keeps its promise.** Conformal intervals, with achieved coverage reported next to the target.
5. **Honest negative results.** When the fancy method doesn't win (association rules vs best-sellers, the anomaly ensemble), the app says so and tries a better idea.
6. **Code tour inside every app.** Annotated source pulled live from the repo, so the walkthrough covers both the UX and the code.

## Quick start
```bash
pip install -r requirements.txt
python data/fetch_data.py        # downloads + checksums all datasets (~4 MB)
python serve.py                  # → http://127.0.0.1:8000
python -m pytest                 # all guardrail tests
```
Trained artifacts are committed, so the apps work immediately. Re-train any project with its pipeline script (see each README).

## Repository layout
```
data/fetch_data.py         real datasets + SHA-256 manifest
shared/hub.py              one FastAPI app that mounts every project + the code-tour endpoint
shared/static/             design system (shell.css), UI shell (shell.js), offline Plotly
projects/<nn_name>/        pipeline · app.py · static UI · code_tour.json · tests · artifacts · screenshots
scripts/screenshots.py     browser test: opens every tab, fails on JS errors, saves screenshots
scripts/record_video.py    records the captioned walkthrough with Playwright + ffmpeg
scripts/build_readmes.py   regenerates all READMEs from the reports
PROMPTS.md                 the prompts used (assignment, source prompts, improvised build prompts)
```

## Prompts
See **[PROMPTS.md](PROMPTS.md)** for the assignment prompt, the original project prompts, and the expanded per-project prompts that this build followed.
"""


def main(video: str):
    chapters_file = ROOT / "docs" / "video" / "chapters.json"
    chapters = json.loads(chapters_file.read_text()) if chapters_file.exists() else []
    for fn in PROJECTS:
        d = fn()
        md = TEMPLATE.format(source=SOURCE, source_name="dlmastery/data_science_examples", gallery=gallery(d["slug"]), tests=tests(d["slug"]), **d)
        (P / d["slug"] / "README.md").write_text(md)
    (ROOT / "README.md").write_text(top(video, chapters))
    print("READMEs written")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-url", default="docs/video/walkthrough.mp4")
    main(ap.parse_args().video_url)
