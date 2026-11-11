"""
Lab 10.01 - Distinguish claim from evidence.

Before trusting any RSI headline, we test the course's OWN laptop demos:
  (a) Budget RSI demo  - is the "Budget RSI beats random" result produced by the scorer,
                         or by how the synthetic data was generated?  Run it over 30 seeds.
  (b) SO-RSI demo      - remove the diagnostics entirely. Does the "+20 points" survive?
                         If yes, the demo's improvement is not evidence for the mechanism.
"""
import contextlib, importlib.util, io, pathlib, random, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
import labkit

labkit.header("10.01", "Distinguish claim from evidence (audit the course demos)")
papers = labkit.course_repo()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- (a) Budget RSI demo
labkit.section("(a) Budget RSI demo, 30 seeds instead of 1")
B = load(papers / "01_budget_rsi" / "demo.py", "budget_demo")
wins_vs_parent, gains, corr = 0, [], []
for seed in range(30):
    random.seed(seed); np.random.seed(seed)
    edits = B.generate_synthetic_edits(128)
    with contextlib.redirect_stdout(io.StringIO()):
        best_b, best_p, _ = B.compare_selection_strategies(edits, B.EditScorer())
    rnd = np.mean([e.held_out_solve_count for e in edits[96:]])
    gains.append((best_b.held_out_solve_count - rnd) / rnd * 100)
    wins_vs_parent += best_b.held_out_solve_count > best_p.held_out_solve_count
    corr.append(np.corrcoef([e.steering_solve_count for e in edits],
                            [e.held_out_solve_count for e in edits])[0, 1])
print(f"Budget RSI gain over random, % : mean {np.mean(gains):+.1f}, min {np.min(gains):+.1f}, max {np.max(gains):+.1f}")
print(f"Budget RSI beats parent-rate ablation in {wins_vs_parent}/30 seeds")
print(f"corr(steering count, held-out count) built into the generator: {np.mean(corr):.2f}")
print("Note: held_out_solve_count = 6 * steering_solve_count + noise in generate_synthetic_edits(),")
print("      and the steering count is itself a linear function of the 8 features. A linear scorer")
print("      is guaranteed to look good here - the demo shows the mechanism RUNS, not that it WORKS.")
print("Note: the cost numbers (12,800 evals, ~88% saving) are printed constants, not measurements.")

# ---------------------------------------------------------------- (b) SO-RSI demo
labkit.section("(b) SO-RSI demo with the diagnostics switched OFF")
S = load(papers / "02_second_order_rsi" / "demo.py", "sorsi_demo")


def success_rate(cls, n=3000, ablate=False):
    random.seed(0)
    agent = cls()
    if ablate and hasattr(agent, "detector"):
        agent.detector.monitor_trace = lambda trace: []     # no anomalies -> no probes ever run
    with contextlib.redirect_stdout(io.StringIO()):
        for _ in range(n):
            agent.attempt_fix("convergence issue")
    return agent.successes / agent.attempts, getattr(agent, "diagnostic_count", 0)

naive, _ = success_rate(S.NaiveRSI)
full, diag = success_rate(S.SORSI)
ablated, diag0 = success_rate(S.SORSI, ablate=True)
print(f"NaiveRSI success rate             : {naive:.1%}")
print(f"SORSI success rate                : {full:.1%}   (diagnostics run: {diag})")
print(f"SORSI with diagnostics REMOVED    : {ablated:.1%}   (diagnostics run: {diag0})")
print("=> the gap survives with zero diagnostics: SORSI.attempt_fix() draws success with")
print("   p=0.5 and NaiveRSI with p=0.3. The probes' recommendations are printed but never used.")

labkit.save("10_01_demo_audit", {
    "budget_demo_gain_mean_pct": float(np.mean(gains)), "budget_demo_beats_parent": wins_vs_parent,
    "budget_demo_steer_heldout_corr": float(np.mean(corr)),
    "sorsi_demo_naive": naive, "sorsi_demo_full": full, "sorsi_demo_no_diagnostics": ablated})
print("\nTakeaway: both demos illustrate the mechanism's *shape*. Neither is evidence that the mechanism")
print("causes improvement. Labs 10.05, 10.08 and 10.11 therefore measure each method on real model runs,")
print("with ablations, matched budgets, many seeds and a held-out split.")
