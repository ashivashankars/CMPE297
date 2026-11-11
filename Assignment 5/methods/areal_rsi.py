"""
AReaL-RSI style leader-follower coordination (lab 10.10, after arXiv:2610.18083).

  Leader       picks a research ORIENTATION for each campaign (calibration / signal / model / alerting)
               from the conditional memory: it prefers orientations with unresolved problems.
  Researchers  (2) run edits inside the orientation on the shared incumbent pipeline.
  Conditional memory  stores findings marked RESOLVED (a supported improvement, safe to build on)
               or UNRESOLVED (tried, did not help *in this context* - worth revisiting after the
               context changes). Researchers only receive findings relevant to their orientation.
  Evidence-based review  after each campaign the leader revises orientation priorities.

Compared with: same agents, same budget, but no memory sharing (each researcher works alone
and the leader rotates orientations blindly).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from turbinegym import TurbineGym, BudgetExceeded, baseline_config, edits
from methods.swarm_rsi import family

ORIENTATIONS = ["calibration", "signal", "model", "alerting"]


@dataclass
class ConditionalMemory:
    items: list = field(default_factory=list)   # dicts: orientation, edit, context, gain, status

    def store(self, orientation, edit_name, context, gain):
        self.items.append(dict(orientation=orientation, edit=edit_name, context=context, gain=gain,
                               status="resolved" if gain > 0.005 else "unresolved"))

    def retrieve(self, orientation, context):
        """Resolved findings for this orientation + unresolved ones whose context has changed."""
        tried_here = {m["edit"] for m in self.items if m["context"] == context}
        return [m for m in self.items if m["orientation"] == orientation and m["edit"] not in tried_here]

    def open_problems(self, orientation, context):
        return sum(1 for m in self.items if m["orientation"] == orientation
                   and m["status"] == "unresolved" and m["context"] != context)


def run(mode: str, seed: int, budget: float = 30.0, campaigns: int = 6, log=None) -> dict:
    """mode = 'areal' (leader + conditional memory) or 'no_sharing'."""
    rng = random.Random(seed)
    gym = TurbineGym(budget=budget)
    mem = ConditionalMemory()
    cfg = baseline_config()
    cur = gym.evaluate(cfg)["f1"]
    base_held = gym.audit_heldout(cfg)["f1"]
    priority = {o: 1.0 for o in ORIENTATIONS}
    history = []
    per_campaign = max(1, int((budget - 1) // campaigns))
    private = [set(), set()]                      # no_sharing: each researcher's own tried set
    try:
        for c in range(campaigns):
            context = tuple(cfg["transforms"]) + (cfg["model"],)
            if mode == "areal":   # leader: orientations that still have untried edits in this context,
                                  # ranked by priority x (1 + open problems worth revisiting)
                tried = {m["edit"] for m in mem.items if m["context"] == context}
                live = [o for o in ORIENTATIONS if any(
                    family(e) == o and edits.describe(e) not in tried for e in edits.legal_edits(cfg))]
                orient = max(live or ORIENTATIONS,
                             key=lambda o: priority[o] * (1 + mem.open_problems(o, context)) + rng.random() * 0.01)
            else:
                orient = ORIENTATIONS[c % len(ORIENTATIONS)]
            gains = []
            for j in range(per_campaign):
                rid = j % 2
                legal = [e for e in edits.legal_edits(cfg) if family(e) == orient] or edits.legal_edits(cfg)
                if mode == "areal":
                    known_here = {m["edit"] for m in mem.items if m["context"] == context}
                    fresh = [e for e in legal if edits.describe(e) not in known_here] or legal
                else:
                    fresh = [e for e in legal if edits.describe(e) not in private[rid]] or legal
                e = rng.choice(fresh)
                cand = edits.apply(cfg, e)
                r = gym.evaluate(cand)["f1"]
                gain = r - cur
                gains.append(gain)
                if mode == "areal":
                    mem.store(orient, edits.describe(e), context, gain)
                else:
                    private[rid].add(edits.describe(e))
                if r > cur:
                    cfg, cur = cand, r
                    context = tuple(cfg["transforms"]) + (cfg["model"],)
            # evidence-based review: orientations that paid off get more future campaigns
            if mode == "areal":
                priority[orient] = 0.5 * priority[orient] + (2.0 if max(gains) > 0.005 else 0.2)
            history.append((c + 1, orient, round(max(gains), 3), round(cur, 3)))
            if log:
                log(f"  campaign {c+1}: leader chose {orient:11s} best gain {max(gains):+.3f} "
                    f"-> incumbent F1 {cur:.3f}  memory={len(mem.items)} findings "
                    f"({sum(m['status']=='resolved' for m in mem.items)} resolved)")
    except BudgetExceeded:
        pass
    return dict(mode=mode, steer=cur, heldout=gym.audit_heldout(cfg)["f1"], baseline_heldout=base_held,
                history=history, memory=mem.items, cfg=cfg)
