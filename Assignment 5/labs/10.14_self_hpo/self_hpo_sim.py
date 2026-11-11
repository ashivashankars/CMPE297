"""
Lab 10.14 - Self-HPO: alternate harness (test-suite) and policy (pipeline) optimisation.
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import labkit
from turbinegym.metrics import mean_ci, paired_sign_test, rsi_index
from methods import self_hpo as H

labkit.header("10.14", "Self-HPO: harness-policy alternation")
labkit.section("Verbose run (seed 0) - watch the harness move to the policy's hardest turbines")
r = H.run("self_hpo", 0, log=print)
print(f"   held-out {r['heldout']:.3f}")
labkit.section("16 seeds, 25 units each")
out = {}
for mode in ("self_hpo", "fixed_harness", "full_eval"):
    runs = [H.run(mode, s) for s in range(16)]
    out[mode] = dict(heldout=[x["heldout"] for x in runs], baseline=[x["baseline_heldout"] for x in runs],
                     rounds=[len(x["rounds"]) for x in runs])
    print(f"   {mode:14s} held-out F1 {mean_ci(out[mode]['heldout'])}   RSI-Index "
          f"{rsi_index(list(zip(out[mode]['baseline'], out[mode]['heldout']))):.3f}   "
          f"rounds/run {sum(out[mode]['rounds'])/16:.1f}")
for o in ("fixed_harness", "full_eval"):
    print(f"   self_hpo vs {o}: {paired_sign_test(out['self_hpo']['heldout'], out[o]['heldout'])}")
labkit.save("10_14_self_hpo", out)
