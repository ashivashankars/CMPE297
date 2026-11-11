# 10.04 · Analyse the scoring mechanism

**Purpose:** find out what the linear readout actually learns, and whether it picks better edits.

```bash
python3 labs/10.04_budget_rsi_mechanism/analyze_readout.py
```
Output: [`output.txt`](output.txt) · `results/10_04_readout.json`

## Code walkthrough (`methods/budget_rsi.py`)
- `label_edits(gym, n, rng, readout)` grows a random pool of pipelines from the baseline. Each (parent, child) pair is labelled with the **cheap** `evaluate_fit` service (cost 0.25) and becomes one training row `[1, parent_rate, d1..d8] → child F1`.
- `LinearReadout.fit()` is ridge least squares: `w = (XᵀX + λI)⁻¹ Xᵀy`.
- `LinearReadout.score(parent_rate, diff)` is one dot product, and nothing runs.
- The lab then builds 60 proposal sets of K=8 edits and, **for the audit only**, fully evaluates every proposal so each selector can be graded.

## Results
**Coefficients (ranked):** parent_rate **+0.74**, alarm_rate_delta +0.26, funcs_net −0.10, intercept +0.10, ensemble_delta −0.04, features_delta +0.04; the rest are ≈0.

| Selector (one evaluation per step) | Mean F1 of the chosen edit |
|---|---|
| Random proposal (standard HGM) | 0.369 |
| Parent-rate ablation | **0.572** |
| Budget RSI readout (8 diff coords) | 0.552 (Spearman with truth 0.76) |
| Best of 8 (would need 8 full evaluations) | 0.613 |

| Ablation | Picked F1 | Spearman |
|---|---|---|
| 8 diff coords | 0.552 | 0.76 |
| 4 diff coords | 0.568 | 0.81 |
| 0 diff coords (parent rate only) | 0.572 | 0.72 |
| 24 / 48 / 96 labelled edits | 0.533 / 0.559 / 0.552 | 0.72 / 0.75 / 0.76 |

## What it means
- The mechanism **works**: with one evaluation per step, the readout captures **75%** of the benefit of evaluating all 8 proposals.
- But in my domain almost all of that comes from the **parent's rate**. The diff coordinates improve the *ranking* of all proposals (Spearman 0.72 → 0.76–0.81) but not the *top pick*. The paper's advantage over the parent-rate ablation **did not transfer**.
- Why: an edit's value depends on context (z-scoring only helps after the firmware fix), and a linear model on context-free diff counts cannot express that interaction.
- The largest diff weight is `alarm_rate_delta` (+0.26): raising the alarm rate tends to help on the fit split because the baseline under-alarms on those turbines.

## Quiz
**Q1. Why a linear model?** It is fast to train on 96 rows, scores in microseconds, and its coefficients are readable, which is exactly how this lab found that the parent rate dominates.

**Q2. What happens when two features are correlated?** The weight is split between them (here lines_net and funcs_net both rise when a transform is added, and get opposite signs). Ridge regularisation keeps that stable.

**Next:** [10.05](../10.05_budget_rsi_extend/README.md)
