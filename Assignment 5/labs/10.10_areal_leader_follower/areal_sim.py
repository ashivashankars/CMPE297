"""
Lab 10.10 - Simulate AReaL-RSI leader-follower coordination with conditional memory.

1 leader + 2 researchers, 6 campaigns, 30 units. Compared with the same team WITHOUT memory sharing
(leader rotates orientations round-robin, each researcher only knows what it tried itself).
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import labkit
from turbinegym.metrics import mean_ci, paired_sign_test, rsi_index
from methods import areal_rsi as A

labkit.header("10.10", "AReaL-RSI: leader + researchers + conditional memory")
labkit.section("Verbose run (seed 0)")
r = A.run("areal", 0, log=print)
print("\n   conditional memory (last 8 findings):")
for m in r["memory"][-8:]:
    print(f"   - [{m['status']:10s}] {m['orientation']:11s} {m['edit']:32s} gain {m['gain']:+.3f}")
print(f"   final: steering {r['steer']:.3f}  held-out {r['heldout']:.3f}  transforms={r['cfg']['transforms']}")

labkit.section("16 seeds, 30 units each")
out = {}
for mode in ("areal", "no_sharing"):
    runs = [A.run(mode, s) for s in range(16)]
    out[mode] = dict(heldout=[x["heldout"] for x in runs], baseline=[x["baseline_heldout"] for x in runs],
                     orientations=[[h[1] for h in x["history"]] for x in runs])
    print(f"   {mode:11s} held-out F1 {mean_ci(out[mode]['heldout'])}   "
          f"RSI-Index {rsi_index(list(zip(out[mode]['baseline'], out[mode]['heldout']))):.3f}")
print(f"   areal vs no_sharing: {paired_sign_test(out['areal']['heldout'], out['no_sharing']['heldout'])}")
print("   orientation choices by the leader (first 4 seeds):")
for o in out["areal"]["orientations"][:4]:
    print("     " + " -> ".join(o))
labkit.save("10_10_areal", out)
