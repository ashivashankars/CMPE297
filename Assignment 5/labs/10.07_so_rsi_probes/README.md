# 10.07 · Analyse the diagnostic probes

**Purpose:** check that each probe measures what it claims, see which anomalies fire, and see how often each hypothesis survives a real test.

```bash
python3 labs/10.07_so_rsi_probes/analyze_probes.py
```
Output: [`output.txt`](output.txt) · `results/10_07_probes.json`

## The probes
| Probe | Statistic on raw sensor data | Fires when | Structural edit proposed |
|---|---|---|---|
| `probe_firmware_drift` | Median vibration ratio, 20 days after vs before each turbine's firmware change | ratio > 1.4 | `firmware_rescale` |
| `probe_sensor_calibration` | Between-turbine spread of healthy vibration ÷ within-turbine spread | > 2.0 | `turbine_zscore` |
| `probe_seasonal_confounding` | corr(oil temperature, ambient temperature) | > 0.6 | `oil_residual` |
| `probe_trend_vs_level` | AUC of 14-day vibration trend vs AUC of raw level (TRAIN labels only) | trend > level + 0.05 | `vib_slope14` |
| `probe_dropout` | Share of missing particle readings | > 5% | `impute_particles` + use `particles` |

## Results
**Control fleet** (same seed, firmware unit change removed): `probe_firmware_drift` goes **quiet** (ratio ×0.99 vs ×2.18). The other probes still fire, which is correct, because their mechanisms still exist in that fleet.

**16 SO-RSI runs:** 54 mismatch, 69 recurrence, 11 opposing (about 8 anomalies per run of about 19 attempts).

| Hypothesis | Supported | Refuted by test |
|---|---|---|
| Firmware v2 changed vibration units | 15 | 0 |
| Wear shows up as a trend, not a level | 16 | 0 |
| Each sensor has its own calibration offset | 6 | 0 |
| Oil temperature dominated by weather | 2 | 13 |
| Particle counter offline, signal unused | 2 | 14 |

| Anomaly | Typical example | Recommendation | Why it targets a root cause |
|---|---|---|---|
| recurrence | `C_down` / `threshold_up` keep failing | Look for missing signal (trend, dropout probes) | A knob that keeps failing means the information isn't in the features |
| opposing | `C_down` then `C_up` | Freeze alarm-bar edits; probe drift and calibration | Oscillating precision/recall means the scores don't separate the classes, which is a representation problem |
| mismatch | A "fewer alarms" patch lowered precision | Probe firmware drift and seasonal confounding | The improver's model of the data is wrong: steering data differs from training data |

## What it means
A probe that fires is a **hypothesis, not a fix**. Two of the five fire correctly (the mechanism exists) but usually fail their test: once the firmware and trend fixes are in, the oil residual and the particle signal add little. Keeping "supported" and "refuted-by-test" apart is what makes the memory useful in 10.08.

## Quiz
**Q1. Can several anomalies fire at once?** Yes. Step 16 of the seed-0 run is both recurrence and mismatch, and each triggers its own probes. A probe runs only once per campaign (`probed`).

**Q2. What if a probe finds nothing?** It is stored as `refuted-by-probe` and no edit is queued, so the improver does not pay to test a hypothesis with no evidence.

**Next:** [10.08](../10.08_so_rsi_apply/README.md)
