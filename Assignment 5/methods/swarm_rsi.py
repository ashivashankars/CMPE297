"""
Method 3 - SwarmRSI: an evolving swarm of scientist agents (after arXiv:2610.20431).

Five agents each hold a HYPOTHESIS (a research direction = a preference over edit families)
and an IMPLEMENTATION (a pipeline program). Every generation:

  1. Feedback-guided mutation  - an agent picks its next edit using its own direction AND the
                                 swarm's shared experience table (edit -> observed gains measured
                                 by *any* agent). Good findings spread; dead ends are avoided.
  2. Complementary recombination - two agents whose gains came from DIFFERENT components are
                                 merged (union of their credited transforms, better agent's model).
  3. Recursive swarm evolution - the swarm revises its own procedure: the share of the budget spent
                                 on recombination vs mutation, and each agent's direction weights,
                                 are updated from which of them actually produced gains.

Baselines under the SAME evaluation budget:
  independent  - five agents, same directions, no shared experience, no recombination
  hill_climber - one greedy agent making random edits
"""
from __future__ import annotations

import copy
import random
from collections import defaultdict
from dataclasses import dataclass, field

from turbinegym import TurbineGym, BudgetExceeded, baseline_config, edits, normalise

FAMILIES = {
    "calibration": lambda e: e["op"].endswith("transform") and e["arg"] in
                   ("firmware_rescale", "turbine_zscore", "oil_residual"),
    "signal":      lambda e: e["op"].endswith("transform") and e["arg"] in
                   ("vib_roll7", "vib_slope14", "oil_slope14", "particle_log", "impute_particles"),
    "model":       lambda e: e["op"] in ("set_model", "C_up", "C_down", "depth_up", "depth_down",
                                         "lr_up", "lr_down"),
    "alerting":    lambda e: e["op"] in ("threshold_up", "threshold_down", "class_weight"),
    "data":        lambda e: e["op"] in ("add_feature", "remove_feature"),
}
FOCUS = 8.0          # how strongly an agent follows its own research direction
ADOPT = False        # competitive selection (homogenises the swarm; off by default, see lab 10.11)
DIRECTIONS = ["calibration", "signal", "model", "alerting", "data"]


def ctx(cfg: dict, e: dict) -> tuple:
    """Experience is CONDITIONAL on context: the same edit can help one implementation and hurt
    another (z-scoring only pays off after the firmware rescale). Key = (edit, parent transforms)."""
    return (edits.describe(e), tuple(cfg["transforms"]), cfg["model"])


def family(e: dict) -> str:
    return next(f for f, test in FAMILIES.items() if test(e))


@dataclass
class Agent:
    name: str
    weights: dict                      # hypothesis: preference over edit families
    cfg: dict
    score: float
    credits: dict = field(default_factory=dict)   # component -> gain it brought this agent

    def components(self):
        return {k for k, v in self.credits.items() if v > 0}


@dataclass
class SwarmLog:
    mode: str
    best_steer: float = 0.0
    best_heldout: float = 0.0
    baseline_heldout: float = 0.0
    best_cfg: dict = None
    events: list = field(default_factory=list)
    recomb_share: list = field(default_factory=list)
    curve: list = field(default_factory=list)


def _pick_edit(agent: Agent, experience, rng, shared: bool):
    legal = edits.legal_edits(agent.cfg)
    scored = []
    for e in legal:
        w = agent.weights[family(e)]
        if shared:
            gains = experience.get(ctx(agent.cfg, e))
            if gains:
                avg = sum(gains) / len(gains)
                w *= 3.0 if avg > 0.01 else (0.3 if avg < -0.01 else 1.0)
        scored.append(w)
    return rng.choices(legal, weights=scored, k=1)[0]


def run(mode: str, seed: int, budget: float = 30.0, n_agents: int = 5, log=None) -> SwarmLog:
    """mode: swarm | independent | hill_climber | swarm_no_recomb | swarm_no_meta"""
    rng = random.Random(seed)
    gym = TurbineGym(budget=budget)
    out = SwarmLog(mode)
    base = baseline_config()
    s0 = gym.evaluate(base)["f1"]
    out.baseline_heldout = gym.audit_heldout(base)["f1"]
    shared = mode.startswith("swarm")
    use_recomb = mode in ("swarm", "swarm_no_meta")
    meta = mode in ("swarm", "swarm_no_recomb")
    k = 1 if mode == "hill_climber" else n_agents

    agents = []
    for i in range(k):
        d = DIRECTIONS[i % len(DIRECTIONS)] if mode != "hill_climber" else None
        w = {f: (FOCUS if f == d else 1.0) for f in FAMILIES}
        agents.append(Agent(d or "greedy", w, copy.deepcopy(base), s0))
    experience = defaultdict(list)
    p_recomb = 0.3 if use_recomb else 0.0
    op_gain = {"mutation": [], "recombination": []}
    best = (s0, base)

    gen = 0
    try:
        while True:
            gen += 1
            for a in agents:
                if use_recomb and rng.random() < p_recomb and len(agents) > 1:
                    # ---------- complementary recombination
                    partner = max((b for b in agents if b is not a),
                                  key=lambda b: len(b.components() - a.components()) + b.score)
                    novel = partner.components() - a.components()
                    if not novel:                      # nothing complementary yet -> mutate instead
                        e = _pick_edit(a, experience, rng, shared)
                        child = edits.apply(a.cfg, e)
                        r = gym.evaluate(child)["f1"]
                        experience[ctx(a.cfg, e)].append(r - a.score)
                        op_gain["mutation"].append(r - a.score)
                        out.events.append((gen, a.name, "mutate " + edits.describe(e), a.score, r))
                        if r > a.score:
                            if e["op"] == "add_transform":
                                a.credits["t:" + e["arg"]] = r - a.score
                            a.cfg, a.score = child, r
                        if a.score > best[0]:
                            best = (a.score, copy.deepcopy(a.cfg))
                        out.curve.append(best[0])
                        continue
                    child = copy.deepcopy(a.cfg if a.score >= partner.score else partner.cfg)
                    for comp in a.components() | partner.components():
                        kind, arg = comp.split(":", 1)
                        if kind == "t" and arg not in child["transforms"]:
                            child["transforms"].append(arg)
                    child = normalise(child)
                    r = gym.evaluate(child)["f1"]
                    gain = r - a.score
                    op_gain["recombination"].append(gain)
                    out.events.append((gen, a.name, f"recombine with {partner.name} (+{sorted(novel)})",
                                       a.score, r))
                    if r > a.score:
                        for comp in novel:
                            a.credits[comp] = partner.credits.get(comp, gain)
                        a.cfg, a.score = child, r
                else:
                    # ---------- feedback-guided mutation
                    e = _pick_edit(a, experience, rng, shared)
                    child = edits.apply(a.cfg, e)
                    r = gym.evaluate(child)["f1"]
                    gain = r - a.score
                    experience_key = edits.describe(e)
                    if shared:
                        experience[ctx(a.cfg, e)].append(gain)
                    op_gain["mutation"].append(gain)
                    out.events.append((gen, a.name, "mutate " + experience_key, a.score, r))
                    if r > a.score:
                        if e["op"] == "add_transform":
                            a.credits["t:" + e["arg"]] = gain
                        a.cfg, a.score = child, r
                        if meta:
                            a.weights[family(e)] *= 1.5      # agent revises its own hypothesis
                    elif meta:
                        a.weights[family(e)] = max(0.2, a.weights[family(e)] * 0.85)
                if a.score > best[0]:
                    best = (a.score, copy.deepcopy(a.cfg))
                out.curve.append(best[0])
            # ---------- recursive swarm evolution: revise the swarm's own procedure
            if meta and use_recomb:
                def rate(xs):
                    return sum(x > 0 for x in xs[-10:]) / len(xs[-10:])
                if op_gain["recombination"] and op_gain["mutation"]:   # only adapt on evidence
                    rm, rr = rate(op_gain["mutation"]), rate(op_gain["recombination"])
                    p_recomb = min(0.7, max(0.1, p_recomb + 0.1 * (1 if rr > rm else -1)))
            # ---------- competitive selection: the weakest agent restarts from the strongest
            #            implementation but keeps its own research direction (hypothesis)
            if shared and ADOPT and gen % 2 == 0:
                lo, hi = min(agents, key=lambda x: x.score), max(agents, key=lambda x: x.score)
                if hi.score - lo.score > 0.05:
                    out.events.append((gen, lo.name, f"adopt {hi.name}'s implementation", lo.score, hi.score))
                    lo.cfg, lo.score, lo.credits = copy.deepcopy(hi.cfg), hi.score, dict(hi.credits)
            out.recomb_share.append(p_recomb)
            if log:
                log(f"  gen {gen:2d}  best steer F1 {best[0]:.3f}  agents "
                    + " ".join(f"{a.name[:5]}={a.score:.2f}" for a in agents)
                    + (f"  p_recomb={p_recomb:.2f}" if use_recomb else ""))
    except BudgetExceeded:
        pass
    out.best_steer, out.best_cfg = best
    out.best_heldout = gym.audit_heldout(out.best_cfg)["f1"]
    return out
