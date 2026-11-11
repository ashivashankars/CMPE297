"""
Lab 10.17 - Analyse metrics beyond the headline score.

For the three headline methods and their baselines:
  * steering -> held-out gap   (did selection overfit the steering split?)
  * reliability                 (share of runs that reach F1 >= 0.70 on held-out; worst run)
  * spread                      (std across seeds - an improver you cannot predict is hard to deploy)
  * cost-normalised gain        (held-out F1 points gained per cost unit)
  * thrash                      (SO-RSI only: repeated failed patches)
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
import labkit

labkit.header("10.17", "Metrics analysis")
budgets = {"10_05_budget_search": None, "10_08_so_rsi": 20, "10_11_swarm": None}
rows = []
for src, keys in [("10_05_budget_search", ["hgm_random@32", "parent_rate@32", "budget_rsi@32", "budget_rsi_online@32"]),
                  ("10_08_so_rsi", ["naive", "so_rsi"]),
                  ("10_11_swarm", ["hill_climber@30", "independent@30", "swarm@30"])]:
    res = labkit.load(src)
    for k in keys:
        h, b = np.array(res[k]["heldout"]), np.array(res[k]["baseline"])
        st = np.array(res[k]["steer"]) if "steer" in res[k] else None
        budget = float(k.split("@")[1]) if "@" in k else 20.0
        rows.append(dict(method=k, heldout=h.mean(), gap=(st.mean() - h.mean()) if st is not None else float("nan"),
                         reliable=float((h >= 0.70).mean()), worst=h.min(), std=h.std(ddof=1),
                         gain_per_unit=(h - b).mean() / budget * 100,
                         thrash=float(np.mean(res[k]["repeated"])) if "repeated" in res[k] else float("nan")))
print(f"   {'method':22s} {'held-out':>8s} {'steer-held':>10s} {'P(F1>=.7)':>9s} {'worst':>6s} {'std':>6s} "
      f"{'pts/unit':>8s} {'thrash':>6s}")
for r in rows:
    print(f"   {r['method']:22s} {r['heldout']:8.3f} {r['gap']:+10.3f} {r['reliable']:9.0%} {r['worst']:6.3f} "
          f"{r['std']:6.3f} {r['gain_per_unit']:8.2f} {r['thrash']:6.1f}")
print("""
   steer-held > 0  : the improver's best steering score over-states what you get on new data
                     (selection-induced optimism - more candidates compared = larger gap).
   pts/unit        : held-out F1 points (x100) gained per cost unit - the budget view of RSI.
   P(F1>=.7), worst: reliability - two methods with equal means can differ a lot here.""")
labkit.save("10_17_metrics", rows)
