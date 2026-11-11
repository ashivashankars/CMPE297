# 10.06 · Run the SO-RSI demo, then watch first-order vs second-order improvement

**Purpose:** see anomaly detection and diagnostic probes work on a real failing pipeline.

```bash
python3 labs/10.06_so_rsi_run_demo/run_demo.py
```
Output: [`output.txt`](output.txt)

## Code walkthrough (`methods/so_rsi.py`)
| Piece | What it is |
|---|---|
| `symptom(r)` + `PATCHES` | The **shared first-order policy**. "False alarms" → raise the alarm bar / lower C / drop class weights; "missed failures" → the opposite; "weak signal" → more model capacity. 25% of moves are random edits from the full catalogue. Both improvers use exactly this. |
| `Step` | One trace entry: the edit, its *predicted* effect, metrics before and after, accepted or not |
| `detect_anomalies` | **Recurrence:** this patch already failed. **Opposing:** it inverts one of the last 3 edits. **Mismatch:** the predicted effect did not happen. |
| `probe_*` (5 functions) | Read-only statistics on raw sensors via `gym.sensor_view()` (0.05 units each; steering labels hidden) |
| `PROBES_FOR` | Routes each anomaly type to the mechanism investigations that could explain it |
| `inquiry_memory` + `queue` | Each probe that fires adds a hypothesis with a proposed **structural** edit. The edit is tested next, and the hypothesis is marked *supported* or *refuted-by-test*. |
| `banned`, `stale` | **The improver revising itself:** after an opposing anomaly on the alarm bar it stops spending evaluations there; a patch that recurred-and-failed is skipped until the incumbent changes |

## What I observed (seed 0, 20 units)
**Naive:** 19 attempts, almost all `threshold_up` / `C_down`. It inches from F1 0.224 to 0.319 and its **held-out F1 drops below baseline** (0.354 vs 0.417), because it over-tuned the alarm bar to the steering split.

**SO-RSI:**
1. Step 1, `C_down` was predicted to raise precision and did not → **mismatch**. The firmware-drift probe finds "vibration jumps ×2.18 at firmware v2 over 12 turbines". `firmware_rescale` is tested: **0.224 → 0.522**.
2. Step 5, a recurrence → the trend probe (AUC of 14-day trend 0.96 vs raw level 0.68). `vib_slope14`: **0.522 → 0.692**.
3. Step 10, an opposing edit (`C_up` after `C_down`) → the calibration probe (between/within-turbine spread 3.0). `turbine_zscore`: **0.763 → 0.795**.
4. Final: steering 0.820, **held-out 0.822** (baseline 0.417). Memory: 3 hypotheses supported, 2 refuted by test.

## Quiz
**Q1. Key difference between naive RSI and SO-RSI?** Naive RSI maps a symptom straight to a patch. SO-RSI treats a pattern in its *own* failed patches as evidence that the problem lies elsewhere, investigates, and then makes a structural change.

**Q2. Why didn't I hard-code success rates like the course demo?** Then the result would say nothing about the mechanism (see 10.01). Here every F1 comes from a real model fit.

**Next:** [10.07](../10.07_so_rsi_probes/README.md)
