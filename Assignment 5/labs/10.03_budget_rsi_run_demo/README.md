# 10.03 · Run the Budget RSI demo, and meet TurbineGym

**Purpose:** see the mechanism run in the course demo, then see what changes when the "code edit" is real.

```bash
python3 labs/10.03_budget_rsi_run_demo/run_demo.py
```
Output: [`output.txt`](output.txt)

## My problem area: wind-turbine gearbox failure early warning
`turbinegym/fleet.py` simulates 24 turbines for 360 days. The task: every day, for every turbine, predict "will this gearbox fail in the next 14 days?" Time-based splits: train (days 0–209), **steering** (210–284, used for all selection), **held-out** (285–359, audited once at the end).

The simulator plants four mechanisms that surface knobs cannot fix:
1. **Per-sensor calibration offsets.** Raw vibration varies 0.5–3× between sensors.
2. **Firmware-v2 unit change.** Half the fleet updates between day 150 and 230, and vibration is reported ×2.2 afterwards. Train data is 98% pre-update; steering/held-out are about 50% post-update, which floods the baseline with false alarms.
3. **Seasonal confounding.** The +8 °C wear signal in oil temperature is hidden inside a ±12 °C seasonal swing.
4. **Sensor dropout.** The particle counter is offline 15% of the time.

## Code walkthrough
| File / function | Role |
|---|---|
| `turbinegym/pipeline.py: render(cfg)` | Turns a config into a **real Python module** (`build_features`, `make_model`, `ALARM_RATE`). This module is the program being improved. |
| `turbinegym/services.py: TurbineGym.load` | `exec()`s that module, so every evaluation runs the generated code |
| `pipeline.py: unified_diff, diff_features` | The 8 Budget RSI coordinates, parsed from the diff **text**: lines_net, funcs_net, groupby_ops_delta, window_ops_delta, features_delta, alarm_rate_delta, ensemble_delta, balanced_delta |
| `services.py: evaluate` | Trains on TRAIN, scores STEERING, charges 1.0 unit to the ledger |
| `ALARM_RATE` | The pipeline calibrates its own alarm bar as a quantile of its TRAIN scores, so no steering labels leak into the threshold |

## What I observed
- Course demo: runs in under a second and prints a large "improvement over random" (see 10.01 for why).
- The baseline pipeline scores steering F1 0.224 (precision 0.13, recall 0.82): the firmware-v2 turbines raise constant false alarms.
- One edit (`firmware_rescale` + raise the alarm bar) produces a 15-line diff with coordinates `lines_net +14, funcs_net +1, groupby +1, alarm_rate −0.019`. Run, it lifts F1 to 0.50.
- Scoring a diff costs about 0.1 ms; a full evaluation costs tens of ms on a laptop. All labs therefore compare **cost units** from the ledger, not wall-clock time.

## Quiz
**Q1. What is the purpose of the steering split?** Selection happens on it, so the held-out split stays an honest, untouched estimate. In TurbineGym, `audit_heldout` is logged separately and never feeds back into any improver.

**Q2. Why render configs to real code instead of scoring configs directly?** Because Budget RSI's claim is about reading a *code diff* before running it. A real diff keeps that question honest: the scorer only sees text.

**Next:** [10.04](../10.04_budget_rsi_mechanism/README.md)
