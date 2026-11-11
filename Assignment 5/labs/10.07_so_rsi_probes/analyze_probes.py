"""
Lab 10.07 - Analyse the diagnostic probes.

1. What does each probe measure on the raw sensor data, and does it fire?
2. Control: run the probes on a fleet where the firmware unit change does NOT exist.
   A probe that fires anyway is a bad probe.
3. Over 16 SO-RSI runs: how often does each anomaly type trigger, which probes follow,
   and how often is each hypothesis supported vs refuted by a real test?
"""
import pathlib, sys
from collections import Counter, defaultdict
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import labkit
from turbinegym import TurbineGym
from methods import so_rsi as S

labkit.header("10.07", "Analyse diagnostic probes")
PROBES = [S.probe_firmware_drift, S.probe_sensor_calibration, S.probe_seasonal_confounding,
          S.probe_trend_vs_level, S.probe_dropout]

labkit.section("1. Probes on the real fleet vs a control fleet without the firmware unit change")
real, control = TurbineGym().sensor_view(), TurbineGym(firmware_factor=1.0).sensor_view()
print(f"   {'probe':30s} {'real fleet':55s} | control fleet (no firmware change)")
for p in PROBES:
    a, b = p(real), p(control)
    print(f"   {p.__name__:30s} {('FIRES ' if a['supported'] else 'quiet ') + a['evidence']:55s} | "
          f"{('FIRES ' if b['supported'] else 'quiet ') + b['evidence']}")

print("   The control fleet removes ONLY the firmware change, so only probe_firmware_drift should go quiet;")
print("   the other mechanisms still exist there and their probes should keep firing.")

labkit.section("2. Which anomalies trigger which probes (routing table)")
for a, fns in S.PROBES_FOR.items():
    print(f"   {a:10s} -> {', '.join(f.__name__ for f in fns)}")

labkit.section("3. 16 SO-RSI runs (budget 20): anomaly counts and hypothesis outcomes")
anoms, status, first_seen = Counter(), defaultdict(Counter), defaultdict(list)
for seed in range(16):
    r = S.run("so_rsi", seed, budget=20)
    for step, a, edit in r.anomalies:
        anoms[a] += 1
    for m in r.inquiry_memory:
        status[m["hypothesis"]][m["status"]] += 1
print(f"   anomaly triggers over 16 runs: {dict(anoms)}  (~{sum(anoms.values())/16:.1f} per run of ~19 attempts)")
print(f"\n   {'hypothesis':52s} supported  refuted-by-test  refuted-by-probe")
for h, c in status.items():
    print(f"   {h:52s} {c['supported']:9d}  {c['refuted-by-test']:15d}  {c['refuted-by-probe']:16d}")

labkit.section("4. Anomaly -> recommendation -> why it addresses a root cause")
TABLE = [
    ("recurrence", "C_down / threshold_up keep failing", "look for missing signal: trend & dropout probes",
     "a knob that keeps failing means the information is not in the features"),
    ("opposing", "C_down then C_up, threshold up then down", "freeze alarm-bar edits; probe drift & calibration",
     "oscillating precision/recall means scores don't separate classes - a representation problem"),
    ("mismatch", "'fewer alarms' patch lowered precision", "probe firmware drift & seasonal confounding",
     "the improver's model of the data is wrong: steering data differs from training data"),
]
for a, ex, rec, why in TABLE:
    print(f"   {a:10s} | e.g. {ex:40s} | {rec:48s} | {why}")
labkit.save("10_07_probes", dict(anomalies=dict(anoms), hypotheses={k: dict(v) for k, v in status.items()}))
