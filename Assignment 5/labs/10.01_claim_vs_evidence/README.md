# 10.01 · Distinguish claim from evidence

**Purpose:** a headline score does not prove the mechanism. Before building three RSI methods, I tested whether the course's own laptop demos are *evidence* for their mechanisms or only *illustrations*.

```bash
python3 labs/10.01_claim_vs_evidence/audit_course_demos.py     # clones the course repo on first run
```
The full console output is in [`output.txt`](output.txt), and the numbers are in `results/10_01_demo_audit.json`.

## Code walkthrough
| Step | Code | What it does |
|---|---|---|
| 1 | `load(...)` | Imports the course's `demo.py` files as modules, so their functions can be called directly |
| 2 | loop over 30 seeds | Re-runs the Budget RSI demo's `compare_selection_strategies`, which the original runs with one unseeded draw |
| 3 | `np.corrcoef(steering, held_out)` | Measures how much of the "result" is built into `generate_synthetic_edits` |
| 4 | `agent.detector.monitor_trace = lambda trace: []` | **Ablation:** SO-RSI with the anomaly detector switched off, so no probe can ever run |

## What I observed
| Demo | Claim the demo prints | What the audit shows |
|---|---|---|
| Budget RSI | "Budget RSI outperforms random" | True in 30/30 seeds, but held-out is generated as `6 × steering + noise` (corr 0.92), and steering is linear in the 8 features. A linear scorer *must* win. The "~88% cost reduction" is a printed constant, not a measurement. |
| SO-RSI | "+20 points from diagnostics" | Naive 30.0%, SO-RSI 50.5%, **SO-RSI with diagnostics removed 50.5%**. The success probabilities are hard-coded (`random() < 0.5` vs `< 0.3`), and the probe recommendations are never used. |

## Three claims, their evidence, and my adaptation (Budget RSI paper)

| Claim (as summarised by the course) | Supporting experiment | What limits it | Laptop demo preserves | My TurbineGym version preserves |
|---|---|---|---|---|
| A linear readout on parent rate + 8 diff coordinates predicts which edit to expand | GPT-4o, HumanEval+, 96 labelled scaffold edits | One model, two benchmarks, one search algorithm | The formula only | Real diffs of a real program, real model fits, measured in 10.04 |
| It beats the parent-rate ablation (87.0% vs 84.2%) | Same | 2.8 points on one benchmark | Nothing: the data is constructed so it wins | Tested directly in 10.04/10.05 |
| It saves most of the evaluation cost | Scores 100+ edits in seconds | Cost of labelling the scorer must be counted | A printed constant | Ledger-measured cost; Budget RSI pays for its own labels out of the same budget |

## Quiz
**Q1. Can the Budget RSI paper claim linear readout scoring works for all code-editing tasks?**
No. It was tested on HumanEval+ and Polyglot with GPT-4o. In my domain (10.04) the diff coordinates added almost nothing beyond the parent rate.

**Q2. Why does it matter that the SO-RSI demo's gap survives with zero diagnostics?**
Because then the demo cannot be evidence that diagnostics help. So in my version the two improvers share one proposal policy, and the only difference is the monitor, probes and memory.

**Next:** [10.02 · Audit three papers](../10.02_audit_paper/README.md)
