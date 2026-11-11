"""
RSIFlow-style adaptive workflow (lab 10.13, after arXiv:2610.21791).

The improvement WORKFLOW is a graph of stages:  data -> calibration -> signal -> model -> alerting.
Each cycle spends one evaluation inside one stage.

  fixed_workflow   visits stages round-robin (a static self-improvement workflow)
  rsiflow          an evolving META-AGENT profiles the bottleneck - which stage currently yields
                   the most improvement per evaluation (UCB over recent gains) - and routes the next
                   cycle there. Its routing table is itself updated from execution feedback, and a
                   stage that keeps failing is put on cooldown until the incumbent changes.
"""
from __future__ import annotations

import math
import random

from turbinegym import TurbineGym, BudgetExceeded, baseline_config, edits
from methods.swarm_rsi import family

STAGES = ["data", "calibration", "signal", "model", "alerting"]


def run(mode: str, seed: int, budget: float = 25.0, log=None) -> dict:
    rng = random.Random(seed)
    gym = TurbineGym(budget=budget)
    cfg = baseline_config()
    cur = gym.evaluate(cfg)["f1"]
    base_held = gym.audit_heldout(cfg)["f1"]
    stats = {s: [] for s in STAGES}          # gains observed per stage
    cooldown = set()
    route = []
    t = 0
    try:
        while True:
            t += 1
            if mode == "fixed_workflow":
                stage = STAGES[(t - 1) % len(STAGES)]
            else:
                open_ = [s for s in STAGES if s not in cooldown] or STAGES

                def ucb(s):
                    g = stats[s][-4:]
                    if not g:
                        return float("inf")
                    return sum(max(0, x) for x in g) / len(g) + 0.05 * math.sqrt(math.log(t) / len(stats[s]))
                stage = max(open_, key=lambda s: (ucb(s), rng.random()))
            legal = [e for e in edits.legal_edits(cfg) if family(e) == stage]
            if not legal:
                stats[stage].append(0.0)
                cooldown.add(stage)
                continue
            e = rng.choice(legal)
            cand = edits.apply(cfg, e)
            r = gym.evaluate(cand)["f1"]
            gain = r - cur
            stats[stage].append(gain)
            route.append(stage)
            if r > cur:
                cfg, cur = cand, r
                cooldown.clear()             # bottlenecks move when the system changes
            elif mode == "rsiflow" and len(stats[stage]) >= 3 and max(stats[stage][-3:]) <= 0:
                cooldown.add(stage)
            if log:
                log(f"  cycle {t:2d} stage={stage:11s} {edits.describe(e):32s} gain {gain:+.3f} "
                    f"F1={cur:.3f} {'cooldown=' + ','.join(sorted(cooldown)) if cooldown else ''}")
    except BudgetExceeded:
        pass
    return dict(mode=mode, steer=cur, heldout=gym.audit_heldout(cfg)["f1"], baseline_heldout=base_held,
                route=route, cfg=cfg)
