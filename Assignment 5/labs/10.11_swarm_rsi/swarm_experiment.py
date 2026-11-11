"""
Lab 10.11 - SwarmRSI: an evolving swarm of five scientist agents.

Verbose run, then a matched-budget comparison over 16 seeds at 30 and 60 units:
  swarm             mutation guided by shared (context-conditional) experience + complementary
                    recombination + recursive revision of the swarm's own procedure
  swarm_no_recomb   ablation: no recombination
  swarm_no_meta     ablation: no recursive procedure revision
  independent       five agents, same directions, no sharing at all
  hill_climber      one greedy agent with the whole budget
"""
import pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
import labkit
from turbinegym.metrics import mean_ci, paired_sign_test, rsi_index
from methods import swarm_rsi as W

labkit.header("10.11", "SwarmRSI: mutation, recombination, recursive swarm evolution")
labkit.section("Verbose run (seed 3, 30 units)")
r = W.run("swarm", 3, budget=30, log=print)
print("\n   events where an agent improved:")
for g, who, what, before, after in r.events:
    if after > before:
        print(f"   gen {g:2d} {who:11s} {what:58s} {before:.3f} -> {after:.3f}")
print(f"   best pipeline: transforms={r.best_cfg['transforms']} model={r.best_cfg['model']}")
print(f"   steering {r.best_steer:.3f}  held-out {r.best_heldout:.3f}  (baseline held-out {r.baseline_heldout:.3f})")

out = {}
for budget in (30, 60):
    labkit.section(f"16 seeds, {budget} units each")
    for mode in ("swarm", "swarm_no_recomb", "swarm_no_meta", "independent", "hill_climber"):
        t = time.time()
        runs = [W.run(mode, s, budget=budget) for s in range(16)]
        k = f"{mode}@{budget}"
        out[k] = dict(heldout=[x.best_heldout for x in runs], steer=[x.best_steer for x in runs],
                      baseline=[x.baseline_heldout for x in runs])
        print(f"   {mode:16s} held-out F1 {mean_ci(out[k]['heldout'])}   steering {np.mean(out[k]['steer']):.3f}   "
              f"RSI-Index {rsi_index(list(zip(out[k]['baseline'], out[k]['heldout']))):.3f}   ({time.time()-t:.0f}s)")
    for other in ("independent", "hill_climber", "swarm_no_recomb", "swarm_no_meta"):
        print(f"   swarm vs {other:16s}: {paired_sign_test(out[f'swarm@{budget}']['heldout'], out[f'{other}@{budget}']['heldout'])}")
labkit.save("10_11_swarm", out)
