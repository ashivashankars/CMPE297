"""
Method 1 - Budget RSI: score code edits before they run (after arXiv:2610.29121).

Mechanism, adapted to TurbineGym:
  * The improver runs a Huxley-Goedel-Machine-style tree search over pipeline programs.
  * Each step, K (parent, child) proposals are drawn: parents by Thompson sampling on
    steering scores, children by a random code edit of that parent.
  * Only ONE proposal per step gets a full (expensive) evaluation. Which one?
       random        -> standard HGM: expand whatever the sampled parent proposed
       parent_rate   -> ablation: the proposal whose parent scored best
       budget_rsi    -> linear readout  w . [parent_rate, 8 diff features]  read off
                        the unified code diff BEFORE running anything
  * The readout is fit on edits labelled with the cheap fit-split service.
  * Optional online refit: every full evaluation becomes a new training row, so the
    scorer (part of the improver) keeps revising itself during the run.
  * Everyone returns the earliest evaluated node with the maximal steering score;
    held-out is audited once at the end.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np

from turbinegym import TurbineGym, BudgetExceeded, baseline_config, render, diff_features, edits


# ----------------------------------------------------------------------------- readout
class LinearReadout:
    """score = w . [1, parent_rate, d1..d8]  (ridge-regularised least squares)."""

    def __init__(self, n_diff: int = 8, ridge: float = 1e-2):
        self.n_diff, self.ridge = n_diff, ridge
        self.X: list[list[float]] = []
        self.y: list[float] = []
        self.w = None

    def row(self, parent_rate: float, dfeat: list[float]) -> list[float]:
        return [1.0, parent_rate] + list(dfeat[: self.n_diff])

    def add(self, parent_rate, dfeat, target):
        self.X.append(self.row(parent_rate, dfeat))
        self.y.append(target)

    def fit(self):
        X, y = np.asarray(self.X), np.asarray(self.y)
        A = X.T @ X + self.ridge * np.eye(X.shape[1])
        self.w = np.linalg.solve(A, X.T @ y)
        return self.w

    def score(self, parent_rate, dfeat) -> float:
        return float(np.dot(self.w, self.row(parent_rate, dfeat)))


def child_of(cfg: dict, rng: random.Random, max_edits: int = 2) -> tuple[dict, list[dict]]:
    c, applied = cfg, []
    for _ in range(rng.randint(1, max_edits)):
        e = edits.random_edit(c, rng)
        c = edits.apply(c, e)
        applied.append(e)
    return c, applied


def label_edits(gym: TurbineGym, n_edits: int, rng: random.Random, readout: LinearReadout,
                log=None):
    """Build the scorer's training set with the CHEAP fit-split service."""
    pool = [baseline_config()]
    rates = {render(pool[0]): gym.evaluate_fit(pool[0])["f1"]}
    for i in range(n_edits):
        parent = rng.choice(pool)
        child, applied = child_of(parent, rng)
        ps, cs = render(parent), render(child)
        if cs not in rates:
            rates[cs] = gym.evaluate_fit(child)["f1"]
        readout.add(rates[ps], diff_features(ps, cs), rates[cs])
        pool.append(child)
        if log and i < 5:
            log(f"   labelled edit {i+1}: {' + '.join(map(edits.describe, applied)):45s} "
                f"parent={rates[ps]:.3f} child={rates[cs]:.3f}")
    return readout


# ----------------------------------------------------------------------------- search
@dataclass
class Node:
    cfg: dict
    steer: float
    order: int
    parent: int | None = None
    edit: str = ""


@dataclass
class RunResult:
    strategy: str
    best_steer: float
    best_heldout: float
    baseline_heldout: float
    baseline_steer: float
    n_full_evals: int
    spent: float
    best_cfg: dict
    trajectory: list = field(default_factory=list)   # best steering score after each full eval


def thompson_parent(nodes: list[Node], rng: random.Random, n_pos: int = 83) -> Node:
    draws = [rng.betavariate(1 + n.steer * n_pos, 1 + (1 - n.steer) * n_pos) for n in nodes]
    return nodes[int(np.argmax(draws))]


def run(strategy: str, seed: int, budget: float = 40.0, k: int = 8, n_label: int = 48,
        online_refit: bool = False, n_diff: int = 8, readout: "LinearReadout | None" = None,
        log=None) -> RunResult:
    """One search run. If a pre-fit `readout` is passed it is copied (amortised scorer);
    otherwise Budget RSI pays for its own labels out of this run's budget."""
    rng = random.Random(seed)
    gym = TurbineGym(budget=budget)
    if readout is not None:
        import copy
        readout = copy.deepcopy(readout)
    elif strategy.startswith("budget_rsi"):
        readout = LinearReadout(n_diff=n_diff)
        label_edits(gym, n_label, rng, readout, log=log)
        readout.fit()

    base = baseline_config()
    nodes = [Node(base, gym.evaluate(base)["f1"], 0)]
    traj = [nodes[0].steer]
    for _step in range(400):                      # hard guard; budget normally stops us first
        props = []
        for _ in range(k if strategy != "random" else 1):
            p = thompson_parent(nodes, rng)
            c, applied = child_of(p.cfg, rng)
            props.append((p, c, applied))
        if strategy == "random":
            p, c, applied = props[0]
        elif strategy == "parent_rate":
            p, c, applied = max(props, key=lambda t: t[0].steer)
        else:
            p, c, applied = max(props, key=lambda t: readout.score(
                t[0].steer, diff_features(render(t[0].cfg), render(t[1]))))
        try:
            s = gym.evaluate(c)["f1"]
        except BudgetExceeded:
            break
        nodes.append(Node(c, s, len(nodes), nodes.index(p), " + ".join(map(edits.describe, applied))))
        traj.append(max(traj[-1], s))
        if readout is not None and online_refit:
            readout.add(p.steer, diff_features(render(p.cfg), render(c)), s)
            readout.fit()

    best_val = max(n.steer for n in nodes)
    best = next(n for n in nodes if n.steer == best_val)          # earliest maximal node
    return RunResult(strategy, best.steer, gym.audit_heldout(best.cfg)["f1"],
                     gym.audit_heldout(base)["f1"], nodes[0].steer,
                     sum(1 for s_, _, _ in gym.ledger if s_ == "evaluate"), gym.spent, best.cfg, traj)
