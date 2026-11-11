"""
Lab 10.16 - Compare environments: TurbineGym as an RSIGym-style Everything-as-a-Service environment.

1. The service surface and its cost ledger (what an improver is allowed to call).
2. RSIGym's three improvement tracks, reproduced on TurbineGym with the same greedy improver and
   the same 20-unit budget:
     data track     - may only edit how sensor data is cleaned / calibrated / featurised
     harness track  - may only edit the model, its capacity and the alerting policy
     joint track    - may edit both
"""
import pathlib, random, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import labkit
from turbinegym import TurbineGym, BudgetExceeded, baseline_config, edits
from turbinegym.metrics import mean_ci, rsi_index
from methods.swarm_rsi import family

labkit.header("10.16", "Environments: TurbineGym services and RSIGym-style tracks")
labkit.section("1. Service surface")
g = TurbineGym(budget=5)
g.evaluate(baseline_config()); g.evaluate_fit(baseline_config()); g.sensor_view()
g.evaluate_suite(baseline_config(), [0, 1, 2]); g.audit_heldout(baseline_config())
for line in [("evaluate(cfg)", "train on TRAIN, score STEERING", "1.0"),
             ("evaluate_fit(cfg)", "cheap noisy label (10 turbines -> 8 turbines)", "0.25"),
             ("evaluate_suite(cfg, ids)", "score a subset of steering turbines (a harness)", "0.1 + 0.9*share"),
             ("sensor_view()", "read-only raw sensors for probes (steering labels hidden)", "0.05"),
             ("audit_heldout(cfg)", "final report only - never used for selection", "0 (logged)")]:
    print(f"   {line[0]:26s} {line[1]:58s} cost {line[2]}")
print(f"   ledger after one call of each: {g.spend_summary()}   spent {g.spent:.3f} of budget {g.budget}")
try:
    for _ in range(10):                       # keep spending until the environment says no
        g.evaluate(baseline_config())
except BudgetExceeded as e:
    print(f"   budget enforcement works: {e}")

TRACKS = {"data": {"calibration", "signal", "data"}, "harness": {"model", "alerting"},
          "joint": {"calibration", "signal", "data", "model", "alerting"}}


def greedy(track, seed, budget=20):
    rng, gym = random.Random(seed), TurbineGym(budget=budget)
    cfg = baseline_config(); cur = gym.evaluate(cfg)["f1"]
    try:
        while True:
            legal = [e for e in edits.legal_edits(cfg) if family(e) in TRACKS[track]]
            c = edits.apply(cfg, rng.choice(legal)); r = gym.evaluate(c)["f1"]
            if r > cur:
                cfg, cur = c, r
    except BudgetExceeded:
        pass
    return gym.audit_heldout(baseline_config())["f1"], gym.audit_heldout(cfg)["f1"]

labkit.section("2. RSIGym tracks on TurbineGym (greedy improver, 20 units, 16 seeds)")
out = {}
for track in TRACKS:
    pairs = [greedy(track, s) for s in range(16)]
    out[track] = dict(baseline=[p[0] for p in pairs], heldout=[p[1] for p in pairs])
    print(f"   {track:8s} track  held-out F1 {mean_ci(out[track]['heldout'])}   RSI-Index {rsi_index(pairs):.3f}")
labkit.section("3. TurbineGym vs RSIGym vs the course demos")
rows = [("", "RSIGym (paper)", "TurbineGym (this repo)", "course laptop demos"),
        ("tasks", "5 benchmarks (SWE-bench V...)", "1 task, 24 turbines x 360 days", "synthetic numbers"),
        ("what is edited", "data, harness, both", "data (transforms), harness (model/alerts), both", "nothing real"),
        ("evaluation", "services + budget", "services + cost ledger + held-out audit", "a formula"),
        ("metric", "RSI-Index", "F1, RSI-Index, thrash, gap", "success counts"),
        ("budget", "$500 per benchmark", "16-60 cost units", "none")]
for r in rows:
    print(f"   {r[0]:15s} | {r[1]:30s} | {r[2]:48s} | {r[3]}")
labkit.save("10_16_tracks", out)
