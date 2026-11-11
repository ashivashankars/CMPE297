# 10.08 · Apply SO-RSI to a debugging task

**Purpose:** use second-order inquiry on a concrete failing test, and check whether inquiry memory carries over to a new round.

```bash
python3 labs/10.08_so_rsi_apply/debug_and_compare.py
```
Output: [`output.txt`](output.txt) · `results/10_08_so_rsi.json`

**The debugging task:** the early-warning pipeline fails its acceptance test, *steering-split F1 ≥ 0.70* (baseline 0.224). Each improver gets 20 units.

## Part A: 16 seeds
| | Test passed | Attempts to pass | Held-out F1 | RSI-Index | Repeated failed patches |
|---|---|---|---|---|---|
| Naive (first-order) | **0 / 16** | — | 0.393 ± 0.046 | −0.042 | 8.2 |
| **SO-RSI** | **16 / 16** | 8.6 | **0.811 ± 0.020** | **0.676** | 4.3 |

SO-RSI beats naive on held-out in 16/16 paired seeds (sign test p < 0.001). The naive improver ends *below* baseline on held-out (negative RSI-Index): it over-fits the alarm bar to the steering split.

## Part B: a second wind farm, with inherited memory (8 units)
Fleet seed 11 has different turbines, failure days and firmware dates. SO-RSI either starts fresh or inherits farm 1's inquiry memory. Inherited hypotheses are **re-verified by their probe** before any edit is tried.

| | Test passed | Held-out F1 | RSI-Index |
|---|---|---|---|
| Naive | 0 / 16 | 0.493 ± 0.013 | −0.022 |
| SO-RSI fresh | 2 / 16 | 0.538 ± 0.061 | 0.068 |
| **SO-RSI with inherited memory** | **16 / 16** | **0.845 ± 0.001** | **0.688** |

In the verbose run, three probes re-verify (firmware ×2.18, trend AUC 0.95, calibration spread 4.2), and three structural edits take steering F1 from 0.488 to 0.848 in three evaluations.

## Limits
- I wrote the probe library knowing which mechanisms the simulator plants. The claim is **"given good probes, second-order inquiry uses them well and its memory transfers"**, not "SO-RSI discovers mechanisms it has no probe for".
- Farm 2 has the same *kinds* of faults as farm 1. Memory would not help, and re-verification would correctly reject the hypotheses, on a farm without them (see the 10.07 control fleet).

## Quiz
**Q1. How does SO-RSI differ from standard debugging?** Standard debugging changes code and re-runs. SO-RSI watches the *pattern* of its own failed fixes, and treats recurrence, oscillation and surprise as signals to investigate instead of patching again.

**Q2. Can it be automated?** Detection and routing are automated here, and the probes are cheap code. Writing *new* probes for unknown mechanisms is the part that needs domain knowledge.

**Next:** [Group 03 · Scaling](../10.09_compare_scaling/README.md)
