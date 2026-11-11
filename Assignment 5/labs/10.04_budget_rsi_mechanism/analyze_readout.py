"""
Lab 10.04 - Analyse the scoring mechanism.

1. Fit the linear readout on 96 edits labelled with the CHEAP fit-split service.
2. Print the learned coefficients, ranked by |weight|.
3. Test the mechanism directly: on 60 fresh proposal sets of K=8 edits, which edit would each
   selector expand, and how good is it really (every proposal is fully evaluated here, for the audit)?
4. Ablations: number of diff coordinates (8 / 4 / 0) and number of labelled edits (24 / 48 / 96).
"""
import pathlib, random, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
from scipy.stats import spearmanr
import labkit
from turbinegym import TurbineGym, baseline_config, render, diff_features, DIFF_FEATURE_NAMES
from methods.budget_rsi import LinearReadout, label_edits, child_of

labkit.header("10.04", "Analyse the Budget RSI scoring mechanism")

labkit.section("1. Fit the readout on 96 cheaply-labelled edits")
gym = TurbineGym()
ro = label_edits(gym, 96, random.Random(0), LinearReadout(), log=print)
w = ro.fit()
print(f"   labelling cost: {gym.spent:.2f} units ({len(ro.y)} edits x fit-split evaluations)")

labkit.section("2. Feature importance (coefficients of score = w . [1, parent_rate, d1..d8])")
names = ["intercept", "parent_rate"] + DIFF_FEATURE_NAMES
for n, c in sorted(zip(names, w), key=lambda x: -abs(x[1])):
    print(f"   {n:18s} {c:+.3f}")

labkit.section("3. Does the readout pick better edits? (60 proposal sets, K=8)")
audit = TurbineGym()                     # audit gym: we fully evaluate every proposal to grade selectors
rng = random.Random(5)
pool = [baseline_config()]
for _ in range(30):
    c, _ = child_of(rng.choice(pool), rng); pool.append(c)
sets = []
for _ in range(60):
    props = []
    for _ in range(8):
        p = rng.choice(pool); c, _ = child_of(p, rng)
        props.append(dict(parent=audit.evaluate(p)["f1"], child=audit.evaluate(c)["f1"],
                          d=diff_features(render(p), render(c))))
    sets.append(props)


def evaluate_selector(readout):
    picked, preds, acts = [], [], []
    for props in sets:
        s = [readout.score(x["parent"], x["d"]) for x in props]
        picked.append(props[int(np.argmax(s))]["child"])
        preds += s; acts += [x["child"] for x in props]
    return np.mean(picked), spearmanr(preds, acts).statistic

rand = np.mean([np.mean([x["child"] for x in p]) for p in sets])
parent = np.mean([max(p, key=lambda x: x["parent"])["child"] for p in sets])
oracle = np.mean([max(x["child"] for x in p) for p in sets])
mean_pick, rho = evaluate_selector(ro)
print(f"   random proposal (standard HGM expansion)  F1 {rand:.3f}")
print(f"   parent-rate ablation                       F1 {parent:.3f}")
print(f"   Budget RSI readout                         F1 {mean_pick:.3f}   Spearman(pred, actual) = {rho:.2f}")
print(f"   best-of-8 (would need 8 full evaluations)  F1 {oracle:.3f}")
captured = (mean_pick - rand) / (oracle - rand)
print(f"   => with ONE evaluation per step the readout captures {captured:.0%} of the benefit of evaluating all 8")

labkit.section("4. Ablations")
rows = []
for n_diff in (8, 4, 0):
    r = LinearReadout(n_diff=n_diff); r.X = [x[:2 + n_diff] for x in ro.X]; r.y = list(ro.y); r.fit()
    m, rho_ = evaluate_selector(r)
    rows.append(("diff coords", n_diff, m, rho_))
for n in (24, 48, 96):
    r = LinearReadout(); r.X, r.y = ro.X[:n], ro.y[:n]; r.fit()
    m, rho_ = evaluate_selector(r)
    rows.append(("labelled edits", n, m, rho_))
for kind, n, m, rho_ in rows:
    print(f"   {kind:15s} = {n:3d}   picked F1 {m:.3f}   Spearman {rho_:.2f}")

labkit.save("10_04_readout", dict(coefficients=dict(zip(names, map(float, w))), random=rand,
            parent_rate=parent, readout=mean_pick, best_of_k=oracle, spearman=rho, captured=captured,
            ablations=[dict(kind=k, n=n, picked=m, spearman=r) for k, n, m, r in rows]))
