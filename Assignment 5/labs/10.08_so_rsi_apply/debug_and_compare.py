"""
Lab 10.08 - Apply SO-RSI to a debugging task.

The task: the early-warning pipeline FAILS its acceptance test
        "steering-split F1 >= 0.70"   (baseline: 0.22 - it raises far too many false alarms).
Both improvers try to make the test pass with a 20-unit budget, 16 seeds each.

Part B - inquiry memory across RSI rounds: a second wind farm (fleet seed 11, different turbines,
failures and firmware dates) is debugged with only 8 units. SO-RSI either starts fresh or inherits the
inquiry memory from the first farm (it must re-verify each hypothesis with its probe before using it).
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
import labkit
from turbinegym.metrics import mean_ci, paired_sign_test, rsi_index
from methods import so_rsi as S

labkit.header("10.08", "Apply SO-RSI to a failing pipeline")
PASS = 0.70


def evals_to_pass(run):
    best = run.baseline_steer
    for k, st in enumerate(run.trace, 1):
        if st.accepted:
            best = st.after["f1"]
        if best >= PASS:
            return k
    return None


out = {}
labkit.section(f"Part A: make the acceptance test (steering F1 >= {PASS}) pass - 16 seeds, 20 units each")
for mode in ("naive", "so_rsi"):
    runs = [S.run(mode, s, budget=20) for s in range(16)]
    e2p = [evals_to_pass(r) for r in runs]
    th = [r.thrash() for r in runs]
    out[mode] = dict(heldout=[r.heldout for r in runs], steer=[r.steer for r in runs],
                     baseline=[r.baseline_heldout for r in runs], passed=sum(x is not None for x in e2p),
                     evals_to_pass=[x for x in e2p if x], repeated=[t["repeated_failed_patches"] for t in th],
                     opposing=[t["opposing_pairs"] for t in th])
    o = out[mode]
    print(f"   {mode:7s} test passed {o['passed']:2d}/16   attempts-to-pass {np.mean(o['evals_to_pass']) if o['evals_to_pass'] else float('nan'):4.1f}"
          f"   held-out F1 {mean_ci(o['heldout'])}   RSI-Index {rsi_index(list(zip(o['baseline'], o['heldout']))):.3f}"
          f"   repeated failed patches {np.mean(o['repeated']):.1f}   opposing pairs {np.mean(o['opposing']):.1f}")
print(f"   so_rsi vs naive (held-out): {paired_sign_test(out['so_rsi']['heldout'], out['naive']['heldout'])}")

labkit.section("Part B: a second wind farm (fleet 11), 8 units, inherit the inquiry memory?")
first = S.run("so_rsi", 0, budget=20)
memory = first.inquiry_memory
print("   inherited memory: " + "; ".join(f"{m['hypothesis']} [{m['status']}]" for m in memory))
print("\n   verbose run with inherited memory (seed 0):")
S.run("so_rsi", 0, budget=8, fleet_seed=11, memory=memory, log=print)
for name, kw in [("naive", dict(mode="naive")), ("so_rsi_fresh", dict(mode="so_rsi")),
                 ("so_rsi_inherited", dict(mode="so_rsi", memory=memory))]:
    runs = [S.run(seed=s, budget=8, fleet_seed=11, **kw) for s in range(16)]
    out["farm2_" + name] = dict(heldout=[r.heldout for r in runs], baseline=[r.baseline_heldout for r in runs],
                                passed=sum(r.steer >= PASS for r in runs))
    o = out["farm2_" + name]
    print(f"   {name:17s} passed {o['passed']:2d}/16   held-out F1 {mean_ci(o['heldout'])}   "
          f"RSI-Index {rsi_index(list(zip(o['baseline'], o['heldout']))):.3f}")
print(f"   inherited vs fresh: {paired_sign_test(out['farm2_so_rsi_inherited']['heldout'], out['farm2_so_rsi_fresh']['heldout'])}")
labkit.save("10_08_so_rsi", out)
