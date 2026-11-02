# Prompt catalog

This file records the prompts behind this repository so anyone can reproduce it with any AI coding assistant (Claude, Claude Code, Gemini CLI, Codex, …).

There are three layers:

1. **The assignment prompt**: what I asked the assistant to do.
2. **The source prompts**: the original project prompts from [`dlmastery/data_science_examples/PROMPTS.md`](https://github.com/dlmastery/data_science_examples/blob/main/PROMPTS.md) that this repo replicates.
3. **The improvised build prompts**: the expanded, per-project specification the assistant actually built against. This is where the "use your creativity, improvise" part of the assignment lives.

---

## 1. Assignment prompt

```text
Replicate the data science experiments i did in your favorite coding assistant - i provided the prompts in the repository
https://github.com/dlmastery/data_science_examples

make sure you publish them in github repo and walk thru these in a video and upload and link to README.md

Note: use your creativity and not need to do exactly like above - improvise if possible. the minimum bar is above
Checking all artifacts
Publish a link to video which walkthrough the code and ux of each of the projects thoroughly in readme.md

I provided prompts.md with what prompts I used

Use your creativity to do more in each app and explain
```

Scoping answers given to the assistant before it started:

| Question | Answer |
|---|---|
| Which projects? | The core 6, done deeply: NYC taxi regression, nano LLM, customer clustering, market basket, anomaly detection, time series |
| Video narration | On-screen captions |
| Publish to | `ashivashankars/CMPE297` → `Data science full stack with ai coding assistant/` |

---

## 2. Source prompts (from the original repo)

| # here | Original # | Original prompt (verbatim, abridged where it repeats) |
|---|---|---|
| 01 | 1 | `You will do end2end a data science project of including data, training, deployment, crisp-dm framework, and an awesome front end. you can use Kaggle NYC taxi challenge. make sure that frontend includes interactive map and trip estimation.` Follow-ups: `make the admin dashboard even better with more data scientist related details…`, `please follow the autoresearch repo skills deligently for hill climbing…` |
| 02 | 2 | `build a simple llm and chatbot (with state of art primitives but fit in my laptop gpu) - make sure you follow crisp-dm framework and also include nice data science admin dashboard. you can research the papers and implement autoresearch to do hill climbing… include all details a data scientist and ai engineer will care.` |
| 03 | 3 | `clustering using popular kaggle data set - make sure you follow crisp-dm framework and also include nice data science admin dashboard…` |
| 04 | 4 | `associative pattern mining using popular kaggle data set - make sure you follow crisp-dm framework and also include nice data science admin dashboard…` |
| 06 | 6 | `anomaly detection using popular kaggle data set and popular methods - make sure you follow crisp-dm framework and also include nice data science admin dashboard…` |
| 12 | 12 | `build a similar website … for timeseries forcasting similar to other projects you built - including detailed crisp-dm steps and admin and other dashboards` |

Repository-wide follow-ups from the original that also apply here: *use screenshots to check*, *do very detailed data science audit … to ensure there is no leakage and reward hacking*, *make sure every aspect of the website is tested with browser testing not just final inference*, *render markup properly*.

---

## 3. Improvised build prompts (what was actually built)

These were derived from the source prompts plus one cross-cutting rule. They are written so you can paste them into a coding assistant.

### Cross-cutting rule (applied to every project)

```text
Build this as one module of a shared FastAPI hub with a dependency-free HTML/JS front end (Plotly, offline).
Follow CRISP-DM and make each phase a tab in the UI. Use a REAL public dataset, downloaded by
data/fetch_data.py and pinned by SHA-256. No synthetic stand-ins. Every number displayed must be
read from the pipeline's report.json, never hard-coded. Choose the validation design to match how
the model will be used (temporal split for time-ordered data, holdout for unsupervised work),
freeze the test set and score it once. Add an explicit leakage check, at least two honest
baselines, and pytest guardrail tests (leakage/causality, metric sanity, API contract).
Add a "Code tour" tab that pulls annotated source ranges live from the repo.
If a fancy model doesn't beat the baseline, say so in the UI.
```

### 01 · NYC taxi trip duration

```text
Kaggle NYC taxi → use the real March-2019 TLC sample (6,433 rides, seaborn mirror).
Predict duration at BOOKING time. Explicitly exclude fare/tip/tolls/total (post-trip) and
train a deliberately leaky model to show what leakage looks like. Temporal split:
fit Mar 1-14 / tune Mar 15-20 / calibrate Mar 21-24 / test Mar 25-31.
Baselines: global median, distance ÷ median speed, Ridge. Champion: HistGradientBoosting with
AutoResearch-style greedy hill climbing on the tune week. Add split-conformal 80/90/95%
intervals and verify their coverage on the test week. Add permutation importance, error
slices (borough, time of day, distance) and a PSI drift monitor. Estimator tab: zone pickers,
hour slider, 24-hour curve with the 90% band.
(The source dataset has zones but no coordinates, so the "map" became a zone-pair estimator
plus a day × hour heatmap instead of inventing coordinates.)
```

### 02 · NanoGPT from scratch

```text
"Fit in my laptop GPU" → make it run on a 2-core CPU. Write everything by hand: byte-level BPE
(512 tokens, trained on the train split only), decoder-only transformer with RoPE, RMSNorm,
SwiGLU, tied embeddings, AdamW + warmup/cosine + grad clipping. Data: Tiny Shakespeare with a
contiguous 90/10 split. Baselines: unigram and bigram cross-entropy on the same val tokens.
Instead of HP hill-climbing (too expensive on CPU), run a controlled ablation at equal steps and
size: modern block vs no-RoPE vs GPT-2 block (LayerNorm + GELU + learned positions).
UI: live training dashboard, tokenizer playground, generation with every token shaded by its
probability (hover for top-5 alternatives), next-token distribution with entropy, attention
heatmaps per layer/head. Tests: causal mask, RoPE relative-position property, tokenizer roundtrip.
```

### 03 · Customer segmentation

```text
Kaggle Mall Customers (200 customers). Don't stop at an elbow plot: run a tournament over
3 feature sets × {k-means, GMM, Ward, DBSCAN} × k=2..10, scored by silhouette AND bootstrap
stability (ARI over resamples). Show 5 k-selection criteria side by side. Check agreement
between algorithms (ARI) and generalization (fit on 80%, assign the unseen 20%). Name
segments with transparent rules and attach a marketing action to each. Classifier tab:
sliders → hard segment, Gaussian-mixture soft membership, "borderline" flag.
```

### 04 · Market basket mining

```text
Groceries dataset (9,835 real baskets, 169 items; Kaggle/arules). Benchmark Apriori vs
FP-Growth (must return identical itemsets). Mine on 80% of baskets; re-measure every rule on
the held-out 20% with a one-sided Fisher exact test and Benjamini-Hochberg FDR. Evaluate the
recommender as a recommender: hide one item per held-out basket, hit-rate@5/@10 vs random and
best-seller baselines, plus a long-tail metric that excludes the 10 best-sellers. Tune
support/confidence on a validation split, not on test. Add an item co-occurrence recommender
if the rules can't beat popularity. UI: live re-mining sliders, rule network graph, checkout cart.
```

### 06 · Anomaly detection

```text
Use 5 real Numenta Anomaly Benchmark series with known-cause failures (machine temperature,
ambient temperature, AWS CPU misconfiguration, EC2 latency, NYC taxi demand). Detectors must be
causal: rolling robust z, seasonal-residual z, Isolation Forest, LOF, rank ensemble. Fit on the
first 15% (probation) only. Thresholds come from the probation score distribution (label-free).
Evaluate at event level: windows caught, detection lead, false alarms/week, plus PR-AUC.
Show the operating curve across thresholds. Monitor tab: sensitivity dial and an anomaly-
injection sandbox (spike / level shift / drift / stuck sensor). Test: changing the future must
not change past scores.
```

### 12 · Time-series forecasting

```text
OPSD German daily electricity consumption 2006-2017. Forecast 1-14 days ahead. Rolling-origin
backtest over 2017 (51 weekly origins). Baselines: seasonal naive and Holt-Winters refit per
origin. Champion: one direct multi-horizon gradient-boosting model with horizon as a feature.
Lags are always relative to the ORIGIN; calendar + German public holidays are allowed because
they're known in advance. Report MAE/MAPE/MASE overall, by horizon, and on holidays.
Per-horizon conformal bands calibrated on 2016 (daily origins), coverage checked on 2017.
UI: MSTL decomposition, ACF/PACF, holiday effect, fan chart from any 2016-17 origin.
Test: corrupting data after the origin must not change any feature.
```

---

## 4. Iteration prompts used during the build

Small corrections the assistant made while building, kept here because they're part of the honest record:

- *"Heatmap cells with no rides became NaN, which isn't valid JSON."* → `shared/report_io.py` strict JSON writer.
- *"Every project's module is named `pipeline`, so Python's import cache hands the wrong module to the others."* → unique module names (`taxi_pipeline.py`, …).
- *"Rules tie the popularity baseline."* → added the co-occurrence recommender and the long-tail metric instead of hiding the result.
- *"Bands don't widen with horizon."* → with Sunday-only origins, horizon is confounded with weekday and each band had only 52 residuals; calibration switched to daily origins.
- *"An input with `id="origin"` collides with `window.origin`."* → renamed.
