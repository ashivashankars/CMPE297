"""
Lab 10.15 - Calculate RSI-Index (RSIGym's metric) for every method in this repo.

RSI-Index = mean over runs of  (final - baseline) / (ceiling - baseline)
i.e. the fraction of the REMAINING gap that the improver closed. Two ceilings are reported:
  * 1.0          - perfect F1 (RSIGym's definition: gap to the maximum score)
  * oracle F1    - a hand-built pipeline that uses ground-truth knowledge of the simulator
                   (never shown to any improver); "how much of the achievable gap was closed"
All numbers are held-out F1 from earlier labs (run ./run_all.sh first).
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
import labkit
from turbinegym import TurbineGym, ORACLE_CONFIG
from turbinegym.metrics import rsi_index, gap_closed

labkit.header("10.15", "RSI-Index across all methods")
labkit.section("Worked example")
print("   baseline held-out F1 0.417, improver reaches 0.811:")
print(f"   gap closed = (0.811 - 0.417) / (1.0 - 0.417) = {gap_closed(0.417, 0.811):.3f}")
oracle = TurbineGym().audit_heldout(ORACLE_CONFIG)["f1"]
print(f"   oracle pipeline held-out F1 = {oracle:.3f}  ->  vs oracle: {gap_closed(0.417, 0.811, oracle):.3f}")

SOURCES = [
    ("Budget RSI", "10_05_budget_search", ["budget_rsi@16", "hgm_random@16", "parent_rate@16",
                                            "budget_rsi@32", "hgm_random@32"]),
    ("SO-RSI", "10_08_so_rsi", ["so_rsi", "naive", "farm2_so_rsi_inherited", "farm2_so_rsi_fresh", "farm2_naive"]),
    ("SwarmRSI", "10_11_swarm", ["swarm@30", "independent@30", "hill_climber@30", "swarm@60",
                                 "independent@60", "hill_climber@60"]),
    ("AReaL-RSI", "10_10_areal", ["areal", "no_sharing"]),
    ("RSIFlow", "10_13_rsiflow", ["rsiflow", "fixed_workflow"]),
    ("Self-HPO", "10_14_self_hpo", ["self_hpo", "fixed_harness", "full_eval"]),
    ("RSIGym tracks", "10_16_tracks", ["data", "harness", "joint"]),
]
labkit.section("RSI-Index table (held-out F1)")
print(f"   {'family':14s} {'variant':24s} {'mean F1':>8s} {'RSI-Index':>10s} {'vs oracle':>10s} {'runs':>5s}")
table = []
for fam, src, keys in SOURCES:
    try:
        res = labkit.load(src)
    except SystemExit as e:
        print(f"   {fam:14s} (skipped: {e})"); continue
    for k in keys:
        if k not in res:
            continue
        pairs = list(zip(res[k]["baseline"], res[k]["heldout"]))
        row = dict(family=fam, variant=k, mean=float(np.mean(res[k]["heldout"])),
                   rsi_index=rsi_index(pairs), vs_oracle=rsi_index(pairs, oracle), n=len(pairs))
        table.append(row)
        print(f"   {fam:14s} {k:24s} {row['mean']:8.3f} {row['rsi_index']:10.3f} {row['vs_oracle']:10.3f} {row['n']:5d}")
print("\n   Read with care: rows use different budgets (16-60 units) - only compare rows inside one family.")
labkit.save("10_15_rsi_index", dict(oracle_heldout=oracle, table=table))
