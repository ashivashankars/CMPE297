"""
Lab 10.05 - Extend Budget RSI to our own edits: a matched-budget search experiment.

Every strategy starts from the same baseline pipeline and gets the same budget in cost units
(full evaluation = 1.0, fit-split evaluation = 0.25). Budget RSI pays for its own 32 labelled
edits OUT OF that budget (8 units), so it gets fewer full evaluations than the baselines.

  hgm_random     Huxley-Goedel-style tree search, expand what the Thompson-sampled parent proposes
  parent_rate    of K=8 proposals, expand the one whose parent scores best (paper's ablation)
  budget_rsi     of K=8 proposals, expand the one the linear diff readout scores best
  budget_rsi_online   same, and the readout is refit after every full evaluation
                       (the improver revises its own scorer during the run)

Selection uses the steering split only. Held-out F1 is audited once, at the end.
"""
import pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
import labkit
from turbinegym.metrics import mean_ci, paired_sign_test, rsi_index
from methods import budget_rsi as B

labkit.header("10.05", "Budget RSI on real pipeline edits, matched budgets")
SEEDS = range(16)
STRATS = {"hgm_random": ("random", {}), "parent_rate": ("parent_rate", {}),
          "budget_rsi": ("budget_rsi", {"n_label": 32}),
          "budget_rsi_online": ("budget_rsi", {"n_label": 32, "online_refit": True})}

labkit.section("One verbose Budget RSI run (seed 0, budget 24)")
r = B.run("budget_rsi", 0, budget=24, n_label=32, log=print)
print(f"   full evaluations: {r.n_full_evals}, spent {r.spent:.2f} units")
print(f"   best-so-far steering F1 after each full evaluation: {[round(x, 2) for x in r.trajectory]}")
print(f"   selected pipeline: transforms={r.best_cfg['transforms']} model={r.best_cfg['model']}")
print(f"   steering F1 {r.best_steer:.3f}   held-out F1 {r.best_heldout:.3f}   (baseline held-out {r.baseline_heldout:.3f})")

results = {}
for budget in (16, 32):
    labkit.section(f"Budget = {budget} units, {len(SEEDS)} seeds")
    for name, (strat, kw) in STRATS.items():
        t = time.time()
        runs = [B.run(strat, s, budget=budget, **kw) for s in SEEDS]
        results[f"{name}@{budget}"] = dict(
            heldout=[x.best_heldout for x in runs], steer=[x.best_steer for x in runs],
            baseline=[x.baseline_heldout for x in runs], full_evals=[x.n_full_evals for x in runs])
        h = results[f"{name}@{budget}"]
        print(f"   {name:18s} held-out F1 {mean_ci(h['heldout'])}  steering {np.mean(h['steer']):.3f}  "
              f"full evals {np.mean(h['full_evals']):4.1f}  RSI-Index {rsi_index(list(zip(h['baseline'], h['heldout']))):.3f}"
              f"   ({time.time()-t:.0f}s)")
    base = results[f"hgm_random@{budget}"]["heldout"]
    for name in ("parent_rate", "budget_rsi", "budget_rsi_online"):
        print(f"   {name:18s} vs hgm_random: {paired_sign_test(results[f'{name}@{budget}']['heldout'], base)}")
labkit.save("10_05_budget_search", results)
