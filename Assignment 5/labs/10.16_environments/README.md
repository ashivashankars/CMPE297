# 10.16 · Compare environments: TurbineGym as an RSIGym-style service environment

**Purpose:** compare the environment I built with RSIGym, and reproduce RSIGym's three improvement tracks.

```bash
python3 labs/10.16_environments/environment_tracks.py      # ~3 min
```
Output: [`output.txt`](output.txt) · `results/10_16_tracks.json`

## Everything-as-a-Service surface (`turbinegym/services.py`)
| Service | What it does | Cost |
|---|---|---|
| `evaluate(cfg)` | Train on TRAIN, score STEERING | 1.0 (repeats are charged too, as a real agent re-running an experiment would be) |
| `evaluate_fit(cfg)` | Cheap noisy label: train on 10 turbines, score 8 others | 0.25 |
| `evaluate_suite(cfg, ids)` | Score a subset of steering turbines (a harness) | 0.1 + 0.9 × share |
| `sensor_view()` | Read-only raw sensors for probes; steering labels hidden | 0.05 |
| `audit_heldout(cfg)` | Final report only; never used for selection | 0 (logged) |

Every call goes to `gym.ledger`, and `BudgetExceeded` stops an improver. That makes every comparison in this repo a matched-budget comparison.

## RSIGym's three tracks on TurbineGym (greedy improver, 20 units, 16 seeds)
| Track | May edit | Held-out F1 | RSI-Index |
|---|---|---|---|
| Data | Cleaning, calibration, features | 0.639 ± 0.074 | 0.380 |
| Harness | Model, capacity, alerting policy | 0.450 ± 0.006 | 0.055 |
| Joint | Both | 0.645 ± 0.080 | 0.391 |

**Finding:** in this domain almost all of the headroom is in the data track, because the firmware drift and calibration problems live in the data. Harness-only search barely moves (RSI-Index 0.055). Joint ≈ data here; RSIGym reports joint > either alone on its benchmarks.

## TurbineGym vs RSIGym vs the course demos
| | RSIGym (paper) | TurbineGym (this repo) | Course laptop demos |
|---|---|---|---|
| Tasks | 5 benchmarks | 1 task, 24 turbines × 360 days | Synthetic numbers |
| Edited | Data, harness, both | Data, harness, both | Nothing real |
| Evaluation | Services + budget | Services + ledger + held-out audit | A formula |
| Metric | RSI-Index | F1, RSI-Index, thrash, steering→held-out gap | Success counts |
| Budget | $500 per benchmark | 16–60 cost units | None |

**Next:** [10.17](../10.17_metrics/README.md)
