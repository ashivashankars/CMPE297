"""
Self-HPO style harness-policy alternation (lab 10.14, after arXiv:2610.22791).

  policy   = the pipeline program being improved
  harness  = the acceptance test-suite the improver uses to judge candidate edits:
             a subset of steering turbines (cheap to run, so more edits can be tried)

  H-step   the CURRENT policy analyses its own failures (per-turbine errors, one full evaluation)
           and proposes the next harness: its hardest turbines + two random guard turbines.
  P-step   the policy is updated under that harness: several candidate edits are judged on the
           suite, the best is kept if it improves the suite score.

Alternating means the harness keeps chasing the policy's *evolving* failure modes.

Baselines with the same budget:
  fixed_harness   one random suite chosen up front, never revised (policy-only optimisation)
  full_eval       no harness: every candidate gets a full steering evaluation
"""
from __future__ import annotations

import random

from turbinegym import TurbineGym, BudgetExceeded, baseline_config, edits
from turbinegym.fleet import N_TURBINES


def run(mode: str, seed: int, budget: float = 25.0, suite_size: int = 8, cands: int = 5,
        log=None) -> dict:
    rng = random.Random(seed)
    gym = TurbineGym(budget=budget)
    cfg = baseline_config()
    base_held = gym.audit_heldout(cfg)["f1"]
    suite = rng.sample(range(N_TURBINES), suite_size)
    rounds = []
    best_full = gym.evaluate(cfg)["f1"]
    try:
        for rnd in range(100):
            # ---------------- H-step
            if mode == "self_hpo":
                err = gym.per_turbine_errors(cfg)
                hard = sorted(err, key=lambda t: -err[t])[: suite_size - 3]
                guard = rng.sample([t for t in range(N_TURBINES) if t not in hard], 3)
                suite = hard + guard
            # ---------------- P-step
            if mode == "full_eval":
                cur = gym.evaluate(cfg)["f1"]
                options = [edits.apply(cfg, edits.random_edit(cfg, rng)) for _ in range(cands)]
                scored = [(gym.evaluate(c)["f1"], c) for c in options]
            else:
                cur = gym.evaluate_suite(cfg, suite)["f1"]
                options = [edits.apply(cfg, edits.random_edit(cfg, rng)) for _ in range(cands)]
                scored = [(gym.evaluate_suite(c, suite)["f1"], c) for c in options]
            s, c = max(scored, key=lambda x: x[0])
            kept = s > cur
            if kept:
                cfg = c
            rounds.append(dict(round=rnd + 1, suite=sorted(suite), suite_before=cur, suite_after=s, kept=kept))
            if log:
                log(f"  round {rnd+1:2d} harness={sorted(suite)} suite F1 {cur:.3f} -> {s:.3f} "
                    f"{'KEEP' if kept else 'keep old'}   transforms={cfg['transforms']}")
    except BudgetExceeded:
        pass
    return dict(mode=mode, steer=gym._eval_cache.get("steer:" + __import__("turbinegym").config_key(cfg),
                                                     {}).get("f1", float("nan")),
                heldout=gym.audit_heldout(cfg)["f1"], baseline_heldout=base_held, rounds=rounds, cfg=cfg)
