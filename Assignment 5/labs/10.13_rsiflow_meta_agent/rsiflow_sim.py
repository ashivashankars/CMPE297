"""
Lab 10.13 - RSIFlow: an evolving meta-agent routes improvement effort to the current bottleneck.
Compared with a fixed round-robin workflow over the same five stages and the same 25-unit budget.
"""
import pathlib, sys
from collections import Counter
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import labkit
from turbinegym.metrics import mean_ci, paired_sign_test, rsi_index
from methods import rsiflow as R

labkit.header("10.13", "RSIFlow meta-agent: adaptive workflow orchestration")
labkit.section("Verbose run (seed 0)")
r = R.run("rsiflow", 0, log=print)
print(f"   held-out {r['heldout']:.3f}   route usage {dict(Counter(r['route']))}")
labkit.section("16 seeds, 25 units each")
out = {}
for mode in ("rsiflow", "fixed_workflow"):
    runs = [R.run(mode, s) for s in range(16)]
    out[mode] = dict(heldout=[x["heldout"] for x in runs], baseline=[x["baseline_heldout"] for x in runs],
                     route=dict(sum((Counter(x["route"]) for x in runs), Counter())))
    print(f"   {mode:15s} held-out F1 {mean_ci(out[mode]['heldout'])}   RSI-Index "
          f"{rsi_index(list(zip(out[mode]['baseline'], out[mode]['heldout']))):.3f}   stage usage {out[mode]['route']}")
print(f"   rsiflow vs fixed: {paired_sign_test(out['rsiflow']['heldout'], out['fixed_workflow']['heldout'])}")
labkit.save("10_13_rsiflow", out)
