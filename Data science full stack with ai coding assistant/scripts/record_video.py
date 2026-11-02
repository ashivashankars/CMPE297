"""Record the captioned walkthrough video of every app (UX + code tour).

  python scripts/record_video.py            -> docs/video/walkthrough.mp4 + docs/video/chapters.json

Playwright drives a real Chromium through a scripted tour of each project. Captions and a
yellow spotlight are injected into the page (window.__caption / window.__spot from shell.js),
so the explanation is burned into the video. Each project is recorded as its own segment and
ffmpeg concatenates them; chapter start times are written for the README.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from screenshots import server  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "video"
SIZE = {"width": 1280, "height": 800}
SPEED = float(os.environ.get("VIDEO_SPEED", "1.0"))  # multiply all caption hold times (0.1 = fast dry run)


# --------------------------------------------------------------------------- tiny DSL
def hold(text: str) -> float:
    return max(3.2, 1.2 + len(text) * 0.052) * SPEED if SPEED >= 1 else 0.3


class Tour:
    def __init__(self, page: Page, base: str):
        self.p, self.base = page, base

    def goto(self, path: str, wait="nav.tabs button, .pcard"):
        self.p.goto(self.base + path)
        self.p.wait_for_selector(wait)
        self.p.wait_for_timeout(1800)

    def cap(self, text: str, spot: str | None = None, extra: float = 0.0):
        self.p.evaluate("([t, s]) => { window.__caption(t); window.__spot(s); }", [text, spot])
        self.p.wait_for_timeout(int((hold(text) + extra) * 1000))

    def tab(self, name: str):
        self.p.evaluate("() => window.scrollTo({top: 0})")
        self.p.click(f'nav.tabs button[data-tab="{name}"]')
        self.p.wait_for_timeout(1300)

    def scroll(self, sel: str):
        self.p.evaluate("(s) => document.querySelector(s).scrollIntoView({behavior: 'smooth', block: 'center'})", sel)
        self.p.wait_for_timeout(900)

    def range(self, sel: str, value, pause=0.6):
        self.p.eval_on_selector(sel, "(e, v) => { e.value = v; e.dispatchEvent(new Event('input', {bubbles: true})); }", str(value))
        self.p.wait_for_timeout(int(pause * 1000))

    def sweep(self, sel: str, values, pause=0.45):
        for v in values:
            self.range(sel, v, pause)

    def select(self, sel: str, value: str, pause=1.2):
        self.p.select_option(sel, value)
        self.p.eval_on_selector(sel, "e => e.dispatchEvent(new Event('input', {bubbles: true}))")
        self.p.wait_for_timeout(int(pause * 1000))

    def click(self, sel: str, pause=1.2):
        self.p.click(sel)
        self.p.wait_for_timeout(int(pause * 1000))

    def fill(self, sel: str, text: str, pause=1.0):
        self.p.fill(sel, text)
        self.p.eval_on_selector(sel, "e => e.dispatchEvent(new Event('input', {bubbles: true}))")
        self.p.wait_for_timeout(int(pause * 1000))

    def code(self, i: int, text: str):
        self.p.click(f'.tour .toc button[data-i="{i}"]')
        self.p.wait_for_timeout(500)
        self.cap(text, "#tour-code", extra=1.5)

    def end(self):
        self.p.evaluate("() => { window.__caption(''); window.__spot(null); }")
        self.p.wait_for_timeout(600)


# --------------------------------------------------------------------------- scripts
def intro(t: Tour):
    t.goto("/", wait=".pcard")
    t.cap("Data Science Full-Stack Lab: six end-to-end projects, replicated and extended from the dlmastery/data_science_examples prompts.")
    t.cap("Everything runs from one command: python serve.py. One FastAPI hub serves every app, and the front end is plain HTML + Plotly. No build step.")
    t.cap("Four rules throughout: real public datasets (checksummed), frozen test sets scored once, explicit leakage checks, and every number in the UI read from the pipeline's report.", ".principles")
    t.cap("Each app is organized by CRISP-DM phase, and each has a Code tour tab that shows the annotated source. Let's go through them.", "#cards")
    t.end()


def taxi(t: Tour):
    t.goto("/p/01_nyc_taxi/")
    t.cap("Project 01, NYC taxi trip duration. The question: at booking time, how long will this ride take, and how sure are we?")
    t.cap("Headline results on a week the model never saw: 2.9-minute MAE vs 7.0 for the distance rule of thumb, and a 90% range that contains the truth 89.8% of the time.", "#kpis")
    t.cap("The original project trained on synthetic data. This one uses 6,433 real NYC TLC rides from March 2019.", ".crisp")
    t.tab("Data")
    t.cap("Data understanding. Duration is right-skewed, so the model learns log(1 + minutes).", "#hist")
    t.cap("Distance explains a lot, but the vertical spread at the same distance is traffic. Time and zone features have to learn that.", "#scatter")
    t.cap("Rush hours show up clearly in the day × hour heatmap of median ride time.", "#heat")
    t.cap("Key finding: fare and total correlate 0.85 with duration because the meter charges by time. They don't exist at booking, so they are leakage.", "#corr", extra=1)
    t.tab("Preparation")
    t.cap("Cleaning rules were fixed before modeling: zero-duration, zero-distance, impossible speed, missing zone. Each rule's count is logged.", "#cleanlog")
    t.cap("A strict temporal split: fit, tune, calibrate, test, in date order. The final week is scored exactly once.", "#split")
    t.tab("Modeling")
    t.cap("Leaderboard: two naive baselines, Ridge, gradient boosting, and the champion after hill climbing.", "#board")
    t.cap("AutoResearch-style hill climbing: mutate the best config, keep it only if tune-week error improves. Gray dots were rejected.", "#trials")
    t.cap("Permutation importance on the test week: distance first, then zones and hour.", "#imp")
    t.tab("Evaluation")
    t.cap("Split-conformal intervals keep their promise: 79.8 / 89.8 / 96.2% coverage against 80 / 90 / 95% targets.", "#coverage")
    t.scroll("#sl_h")
    t.cap("Error slices: long trips and the Bronx are hardest. That's where to collect more data.", "#sl_d")
    t.scroll("#leak")
    t.cap("The leakage trap, trained on purpose: add fare and the model looks 2.4× better offline, and it's useless in production.", "#leak", extra=1)
    t.cap("A PSI drift monitor compares train vs test distributions. Everything is stable here.", "#drift")
    t.tab("Estimator")
    t.cap("Deployment: book a ride. Midtown to JFK on a Friday at 5pm gives about 54 minutes, with a 90% range.", "#est")
    t.sweep("#hour", [6, 8, 10, 13, 17, 20, 23, 3])
    t.cap("Dragging the hour slider re-queries the API. The chart shows the same trip at every hour, with the rush-hour bump and its uncertainty band.", "#hourly")
    t.select("#dz", "LaGuardia Airport")
    t.cap("Leave distance blank and the API uses the route's historical median, and says which fallback it used.", "#est")
    t.tab("Code tour")
    t.code(1, "Code tour: features are pure functions of a single row known at booking, so this step can't leak.")
    t.code(2, "The temporal split is four consecutive date ranges. A random split would let the model learn from the future.")
    t.code(5, "Split-conformal in 7 lines: a quantile of calibration residuals gives distribution-free intervals.")
    t.code(7, "Serving reuses the training featurizer, so there is no train/serve skew.")
    t.end()


def llm(t: Tour):
    t.goto("/p/02_nano_llm/")
    t.cap("Project 02, NanoGPT from scratch: tokenizer, transformer, training loop and sampler written by hand, trained on 2 CPU cores.")
    t.cap("A 2.7M-parameter model reaches a validation perplexity far below a bigram model on Shakespeare it never trained on.", "#kpis")
    t.cap("Modern building blocks: RoPE inside attention, RMSNorm, SwiGLU, tied embeddings.", "#arch")
    t.tab("Tokenizer")
    t.cap("A byte-level BPE tokenizer with 512 tokens, trained only on the training split. Type anything and see the tokens.", "#tk_out")
    t.fill("#tk_in", "JULIET:\nO Romeo, Romeo! wherefore art thou Romeo?")
    t.cap("Frequent words become single tokens, and rarer names split into pieces. About 1.9 characters per token.", "#tk_out")
    t.cap("The first merges are the most frequent English fragments; the longest tokens are words like shall, would and thou.", "#longest")
    t.tab("Training")
    t.cap("Training and validation loss fall well below the unigram and bigram baselines (dashed lines).", "#loss", extra=1)
    t.cap("Warmup then cosine decay. The generalization gap is reported, so overfitting can't hide.", "#lr")
    t.scroll("#snaps")
    t.cap("Same prompt, random weights vs trained: from noise to speaker names, line breaks and archaic English.", "#snaps", extra=1)
    t.tab("Ablation")
    t.cap("Controlled ablation at equal steps and size: modern block vs no position info vs the 2019 GPT-2 block.", "#abl", extra=1)
    t.cap("The result is read from the runs, with a caveat about single-seed noise.", "#ablnote", extra=1.5)
    t.tab("Playground")
    t.cap("Deployment: generate text. Each token is shaded by the probability the model gave it; darker means less sure.", "#gen", extra=1)
    t.p.hover("#gen .tok:nth-of-type(6)")
    t.cap("Hover any token to see the top-5 alternatives the model considered at that step.", None, extra=0.5)
    t.range("#temp", 1.4, 0.3)
    t.click("#go", 3)
    t.cap("Raise the temperature to 1.4 and the output gets wilder. Probabilities spread out, so more tokens look darker.", "#gen")
    t.range("#temp", 0.3, 0.3)
    t.click("#go", 3)
    t.cap("At 0.3 it plays safe and repetitive. The next-token chart shows the full distribution and its entropy.", "#nxt", extra=0.5)
    t.tab("Attention")
    t.cap("Attention viewer: everything above the diagonal is zero because of the causal mask. A token can never look ahead.", "#att", extra=1)
    t.select("#at_layer", "0", 0.6)
    t.select("#at_head", "2", 1.0)
    t.cap("Switch layers and heads: different heads learn different patterns. Some look mostly at the previous token, others spread attention further back.", "#att")
    t.tab("Code tour")
    t.code(1, "RMSNorm and RoPE: rotating query/key pairs makes attention depend on relative distance, with no learned position table.")
    t.code(4, "Sampling: temperature, top-k and nucleus top-p, plus the probabilities shown in the Playground.")
    t.code(5, "The training loop: AdamW with decoupled weight decay, warmup + cosine schedule, gradient clipping, fixed-seed validation.")
    t.end()


def segments(t: Tour):
    t.goto("/p/03_customer_segments/")
    t.cap("Project 03, customer segmentation on the Kaggle Mall Customers data. There is no label, so the question is: are the segments real?")
    t.cap("Five segments with silhouette 0.55, bootstrap stability 0.98, and held-out customers clustering just as well.", "#kpis")
    t.tab("Data")
    t.cap("Income vs spending score already shows structure by eye. The job is to confirm it rigorously.", "#raw")
    t.tab("Modeling")
    t.cap("Five k-selection criteria side by side. Silhouette, Davies-Bouldin and GMM BIC peak at k = 5; elbow and Calinski-Harabasz keep rising, so they can't decide alone.", "#ksel", extra=1)
    t.cap("Bootstrap stability breaks the tie: refit on resampled customers and compare labels. k = 5 stays at 0.98; above 5, stability declines.", "#stab", extra=0.5)
    t.scroll("#tourn_heat")
    t.cap("A tournament over 3 feature sets × 3 algorithms × 9 values of k. Adding age or gender hurts separation.", "#tourn_heat", extra=0.5)
    t.tab("Evaluation")
    t.cap("k-means, Gaussian mixture and Ward find the same segments (ARI ≥ 0.94), and the segments generalize to unseen customers.", "#evalkpis", extra=0.5)
    t.cap("Silhouette for every customer: almost no one is closer to another segment than to their own.", "#silplot")
    t.tab("Segments")
    t.cap("The five segments, named by transparent rules on their centroids, each with a marketing action.", "#seg")
    t.scroll("#personas")
    t.cap("High-income cautious savers are the biggest opportunity; high-income big spenders are the VIPs to protect.", "#personas", extra=0.5)
    t.tab("Classifier")
    t.cap("Deployment: score a new customer. Move income from 40 to 75 at spending score 50 and watch the boundary.", "#assign")
    t.range("#sc", 50, 0.3)
    t.range("#age", 40, 0.3)
    t.sweep("#inc", [30, 40, 50, 60, 70, 80, 95, 110, 125], 0.55)
    t.cap("Soft membership from the Gaussian mixture shows when a customer sits between two segments.", "#soft")
    t.tab("Code tour")
    t.code(1, "Bootstrap stability: resample, refit, and compare labels on shared customers with the Adjusted Rand Index.")
    t.code(3, "The holdout check: the scaler and model are fitted on 80% of customers; the unseen 20% are assigned and scored.")
    t.end()


def basket(t: Tour):
    t.goto("/p/04_market_basket/")
    t.cap("Project 04, market basket mining on 9,835 real grocery baskets. What sells together, and what should we suggest at checkout?")
    t.cap("368 of 502 rules hold up on held-out baskets after a Fisher test with false-discovery-rate control.", "#kpis")
    t.cap("And an honest headline: high-confidence rules only tie the 'most popular items' baseline.", ".note.warn", extra=0.5)
    t.tab("Data")
    t.cap("A long tail: whole milk is in 25% of baskets, most items in under 1%. That's why lift matters more than confidence.", "#tail")
    t.tab("Mining")
    t.cap("Live re-mining: every slider re-runs FP-Growth on the training baskets in milliseconds.", "#mined")
    t.sweep("#ml", [1.8, 2.2, 2.6, 3.0], 0.8)
    t.cap("Raise minimum lift and the obvious milk-and-vegetables rules drop out; only the surprising pairings remain.", "#mined", extra=0.5)
    t.scroll("#bench")
    t.cap("Apriori vs FP-Growth return identical itemsets; FP-Growth scales better as support drops.", "#bench")
    t.tab("Evaluation")
    t.cap("Out-of-sample check: training lift vs held-out lift for every rule. Gray rules didn't survive.", "#holdout", extra=0.5)
    t.cap("Recommender leaderboard with leave-one-out on held-out baskets. Item co-occurrence wins, and nearly doubles best-sellers on long-tail items.", "#board", extra=1)
    t.tab("Rule graph")
    t.cap("The strongest validated rules as a network. Clusters reveal shopping missions: produce, dairy, drinks.", "#graph", extra=0.5)
    t.tab("Checkout")
    t.cap("Deployment: a live cart. The champion ranks items by co-occurrence; the right column shows which rule fired, or that none did.", "#rec_rules", extra=0.5)
    t.click('#popular .chip[data-i="tropical fruit"]', 1.2)
    t.click('#popular .chip[data-i="root vegetables"]', 1.5)
    t.cap("Add items and both recommenders update. Rules fire only when their whole antecedent is in the cart.", "#rec_co")
    t.tab("Code tour")
    t.code(1, "Each rule is re-tested on held-out baskets with a one-sided Fisher exact test and Benjamini-Hochberg correction.")
    t.code(3, "The champion is a single matrix product, XᵀX, giving every pairwise count, so it uses signals that support thresholds throw away.")
    t.code(4, "Evaluating like a recommender: hide one item per basket and check the top-k, plus a long-tail variant.")
    t.end()


def anomaly(t: Tour):
    t.goto("/p/06_anomaly_detection/")
    t.cap("Project 06, anomaly detection on five Numenta Anomaly Benchmark series with real, labeled failures.")
    t.cap("Rule: labels are never used to train a detector or choose a threshold, only to grade the result.", ".note", extra=0.5)
    t.tab("Data")
    t.cap("Red bands are the known failure windows; gray is the probation period the detectors learn normal behavior from.", "#gallery")
    t.tab("Detectors")
    t.cap("Five causal detectors: robust z-score, seasonal residual, Isolation Forest, LOF, and a rank ensemble.", "#det_plot", extra=1)
    t.cap("Thresholds sit at the 99.9th percentile of each detector's own probation scores. Label-free.", ".note")
    t.tab("Evaluation")
    t.cap("Event-level scoring: failure windows caught, how early, and false alarms per week.", "#summary", extra=0.5)
    t.cap("The operating curve: each threshold trades caught failures against false alarms. No detector dominates.", "#curve", extra=1)
    t.tab("Monitor")
    t.cap("Deployment: a live monitor. Green triangles are alerts inside real failures; red ones are false alarms.", "#m_plot", extra=0.5)
    t.sweep("#m_q", [2, 1, 0], 1.0)
    t.cap("Turn the sensitivity up and you catch more failures, at the cost of more false pages.", "#m_stats")
    t.range("#m_q", 3, 0.5)
    t.select("#i_kind", "drift", 0.4)
    t.range("#i_pos", 60, 0.2)
    t.click("#i_go", 4)
    t.cap("Injection sandbox: add a slow 2-day drift and re-run every detector end to end. Drifts are much harder to catch than spikes.", "#i_table", extra=1)
    t.tab("Code tour")
    t.code(1, "Causal features: every rolling window ends at time t. A unit test confirms changing the future never changes past scores.")
    t.code(3, "Label-free thresholds plus a refractory period, so a burst of alerts becomes one page.")
    t.end()


def forecast(t: Tour):
    t.goto("/p/12_timeseries_forecasting/")
    t.cap("Project 12, forecasting Germany's daily electricity demand 1 to 14 days ahead.")
    t.cap("1.9% MAPE over a full year of rolling forecasts, half the error of seasonal naive, with calibrated bands.", "#kpis")
    t.tab("Data")
    t.cap("Twelve years of daily consumption, with strong yearly and weekly cycles.", "#full")
    t.cap("MSTL separates trend, yearly season, weekly season and residual.", "#decomp")
    t.cap("Holidays look like Sundays. A model that doesn't know the calendar will miss them badly.", "#hol")
    t.tab("Preparation")
    t.cap("Rolling-origin evaluation: train to 2015, calibrate on 2016, backtest every Sunday of 2017.", "#origins")
    t.cap("Lags are always relative to the forecast origin, never the target day. Calendar and holidays are known in advance.", "table.data", extra=1)
    t.tab("Evaluation")
    t.cap("714 forecasts per model. Gradient boosting reaches MASE 0.51, beating Holt-Winters and seasonal naive.", "#board")
    t.cap("On public holidays the baselines collapse to ~29% error; the holiday-aware model stays under 4%.", "#holslice", extra=0.5)
    t.scroll("#cov")
    t.cap("Conformal bands calibrated on 2016 land on target for 2017.", "#cov")
    t.tab("Forecast")
    t.cap("Deployment: a forecast made on December 17, 2017. Seasonal naive expects a normal week; the model sees Christmas coming.", "#fan", extra=1)
    t.click('#presets .chip[data-d="2017-04-09"]', 2.5)
    t.cap("Easter week: compare how each model handles Good Friday and Easter Monday (the red bars) against the actuals.", "#fan")
    t.click('#mchips .chip[data-m="Holt-Winters"]', 2)
    t.cap("Toggle models to compare. Per-forecast MAPE is on the left.", "#fstats")
    t.tab("Code tour")
    t.code(1, "The anti-leakage core: every lag is read at a position ≤ the origin. A test corrupts the future and checks no feature changes.")
    t.code(3, "Conformal bands per horizon, calibrated on every daily origin of 2016.")
    t.end()


def outro(t: Tour):
    t.goto("/", wait=".pcard")
    t.cap("That's all six. Each project has its README with screenshots, tests (pytest), and a Code tour inside the app.")
    t.cap("Reproduce it: python data/fetch_data.py, then python serve.py, then open http://127.0.0.1:8000. Thanks for watching.")
    t.end()


SEGMENTS = [("Introduction", intro), ("01 · NYC taxi trip duration", taxi), ("02 · NanoGPT from scratch", llm),
            ("03 · Customer segmentation", segments), ("04 · Market basket mining", basket),
            ("06 · Anomaly detection", anomaly), ("12 · Electricity demand forecasting", forecast), ("Wrap-up", outro)]


def main(only: list[str]) -> None:
    raw = OUT / "raw"
    shutil.rmtree(raw, ignore_errors=True)
    raw.mkdir(parents=True)
    parts = []
    with server() as base, sync_playwright() as pw:
        browser = pw.chromium.launch()
        for i, (title, fn) in enumerate(SEGMENTS):
            if only and not any(o in title for o in only):
                continue
            ctx = browser.new_context(viewport=SIZE, record_video_dir=str(raw / f"{i:02d}"), record_video_size=SIZE)
            page = ctx.new_page()
            fn(Tour(page, base))
            page.close()
            ctx.close()
            webm = next((raw / f"{i:02d}").glob("*.webm"))
            parts.append((title, webm))
            print(f"recorded {title}", flush=True)
        browser.close()

    # trim the blank first ~1s of each segment (page load), encode, then concat
    mp4s, chapters, t = [], [], 0.0
    for i, (title, webm) in enumerate(parts):
        mp4 = raw / f"{i:02d}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.0", "-i", str(webm), "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "23", "-pix_fmt", "yuv420p", "-r", "25", str(mp4)], check=True)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                                   capture_output=True, text=True, check=True).stdout)
        chapters.append({"title": title, "start_sec": round(t, 1), "duration_sec": round(dur, 1)})
        t += dur
        mp4s.append(mp4)
    (raw / "list.txt").write_text("".join(f"file '{m.name}'\n" for m in mp4s))
    final = OUT / "walkthrough.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(raw / "list.txt"), "-c", "copy",
                    "-movflags", "+faststart", str(final)], check=True)
    (OUT / "chapters.json").write_text(json.dumps(chapters, indent=1))
    print(f"wrote {final} ({final.stat().st_size / 1e6:.1f} MB, {t / 60:.1f} min)")
    for c in chapters:
        print(f"  {int(c['start_sec'] // 60):02d}:{int(c['start_sec'] % 60):02d}  {c['title']}")


if __name__ == "__main__":
    main(sys.argv[1:])
