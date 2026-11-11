"""
Method 2 - SO-RSI: second-order diagnostic inquiry (after arXiv:2610.05701).

Two improvers share the SAME first-order proposal policy and the SAME budget:

  NaiveRSI (first-order)   looks at the symptom on the steering split (too many false alarms /
                           too many missed failures / both) and patches a surface knob.
                           Greedy accept if the steering F1 improves.

  SORSI (second-order)     runs the identical policy, but passively monitors its own trace for
                           three structural anomalies:
                             recurrence  - the same patch keeps being tried and keeps failing
                             opposing    - a patch undoes a recent patch (threshold up/down ...)
                             mismatch    - the outcome contradicts the patch's stated prediction
                           An anomaly triggers lightweight diagnostic PROBES on raw sensor data.
                           Probe findings go to a persistent INQUIRY MEMORY as hypotheses, each with
                           a proposed structural edit. Hypotheses are tested, then marked
                           supported / refuted. The improver also revises ITSELF: after an
                           opposing anomaly it stops spending evaluations on threshold patches
                           until the representation changes.

Nothing about the success rate is hard-coded: any difference comes from what the probes find.
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field

import numpy as np
from sklearn.metrics import roc_auc_score

from turbinegym import TurbineGym, BudgetExceeded, baseline_config, edits

INVERSE = {"threshold_up": "threshold_down", "threshold_down": "threshold_up",
           "C_up": "C_down", "C_down": "C_up", "depth_up": "depth_down", "depth_down": "depth_up",
           "add_transform": "remove_transform", "remove_transform": "add_transform",
           "add_feature": "remove_feature", "remove_feature": "add_feature"}


# ============================================================================ first-order policy
def symptom(r: dict) -> str:
    if r["precision"] < r["recall"] - 0.10:
        return "false_alarms"
    if r["recall"] < r["precision"] - 0.10:
        return "missed_failures"
    return "weak_signal"


PATCHES = {   # symptom -> list of (edit, predicted effect)
    "false_alarms":    [({"op": "threshold_up"}, "precision_up"), ({"op": "C_down"}, "precision_up"),
                        ({"op": "class_weight", "arg": None}, "precision_up")],
    "missed_failures": [({"op": "threshold_down"}, "recall_up"),
                        ({"op": "class_weight", "arg": "balanced"}, "recall_up")],
    "weak_signal":     [({"op": "set_model", "arg": "hgb"}, "f1_up"), ({"op": "C_up"}, "f1_up"),
                        ({"op": "depth_up"}, "f1_up")],
}


def first_order_proposal(cfg: dict, r: dict, rng: random.Random, explore: float = 0.25):
    """The shared surface-level policy. Returns (edit, prediction, symptom)."""
    s = symptom(r)
    if rng.random() < explore:
        return edits.random_edit(cfg, rng), "f1_up", s
    options = [(e, p) for e, p in PATCHES[s] if edits.apply(cfg, e) != cfg]
    if not options:
        return edits.random_edit(cfg, rng), "f1_up", s
    e, p = rng.choice(options)
    return e, p, s


# ============================================================================ trace + anomalies
@dataclass
class Step:
    i: int
    edit: dict
    prediction: str
    symptom: str
    before: dict
    after: dict
    accepted: bool
    source: str = "policy"        # policy | inquiry

    @property
    def name(self):
        return edits.describe(self.edit)


def detect_anomalies(trace: list[Step], step: Step) -> list[str]:
    found = []
    failed_same = [s for s in trace[:-1] if s.name == step.name and not s.accepted]
    if not step.accepted and len(failed_same) >= 1:
        found.append("recurrence")
    recent = trace[-4:-1]
    if any(s.edit["op"] == INVERSE.get(step.edit["op"]) and s.edit.get("arg") == step.edit.get("arg")
           for s in recent):
        found.append("opposing")
    b, a = step.before, step.after
    violated = {
        "precision_up": a["precision"] <= b["precision"],
        "recall_up": a["recall"] <= b["recall"],
        "f1_up": a["f1"] < b["f1"] - 0.02,
    }[step.prediction]
    if violated:
        found.append("mismatch")
    return found


# ============================================================================ diagnostic probes
def probe_firmware_drift(view):
    """Does vibration jump when a turbine's firmware changes? (uses unlabeled train+steer rows)"""
    ratios = []
    for tid, t in view.groupby("turbine_id"):
        if t.firmware.nunique() == 2:
            pre = t[t.firmware == 1].vibration.tail(20).median()
            post = t[t.firmware == 2].vibration.head(20).median()
            ratios.append(post / pre)
    r = float(np.median(ratios)) if ratios else 1.0
    return {"evidence": f"median vibration jump at firmware v2 = x{r:.2f} over {len(ratios)} turbines",
            "supported": r > 1.4, "hypothesis": "firmware v2 changed vibration units",
            "edit": {"op": "add_transform", "arg": "firmware_rescale"}}


def probe_sensor_calibration(view):
    """Is between-turbine spread of healthy vibration much larger than within-turbine spread?"""
    h = view[(view.firmware == 1) & (view.day < 60)]
    between = h.groupby("turbine_id").vibration.median().std()
    within = h.groupby("turbine_id").vibration.std().mean()
    ratio = float(between / within)
    return {"evidence": f"between/within turbine vibration spread = {ratio:.1f}",
            "supported": ratio > 2.0, "hypothesis": "each sensor has its own calibration offset",
            "edit": {"op": "add_transform", "arg": "turbine_zscore"}}


def probe_seasonal_confounding(view):
    c = float(np.corrcoef(view.oil_temp, view.ambient_temp)[0, 1])
    return {"evidence": f"corr(oil_temp, ambient_temp) = {c:.2f}",
            "supported": c > 0.6, "hypothesis": "oil temperature is dominated by weather, not wear",
            "edit": {"op": "add_transform", "arg": "oil_residual"}}


def probe_trend_vs_level(view):
    """On TRAIN labels: does a 14-day vibration trend separate failures better than the raw level?"""
    tr = view[view.split == "train"].sort_values(["turbine_id", "day"]).copy()
    sm = tr.groupby("turbine_id").vibration.transform(lambda s: s.rolling(5, min_periods=1).mean())
    prev = sm.groupby(tr.turbine_id).shift(14)
    slope = ((sm - prev) / prev).fillna(0)
    a_level = roc_auc_score(tr.label, tr.vibration)
    a_trend = roc_auc_score(tr.label, slope)
    return {"evidence": f"AUC raw vibration level = {a_level:.2f}, AUC 14-day trend = {a_trend:.2f}",
            "supported": a_trend > a_level + 0.05, "hypothesis": "wear shows up as a trend, not a level",
            "edit": {"op": "add_transform", "arg": "vib_slope14"}}


def probe_dropout(view):
    rate = float(view.particles.isna().mean())
    return {"evidence": f"particle-sensor dropout = {rate:.0%}",
            "supported": rate > 0.05, "hypothesis": "particle counter is offline often; signal unused",
            "edit": {"op": "add_transform", "arg": "impute_particles"},
            "followup": {"op": "add_feature", "arg": "particles"}}


PROBES_FOR = {   # which mechanism investigations each anomaly type triggers
    "opposing":   [probe_firmware_drift, probe_sensor_calibration],
    "mismatch":   [probe_firmware_drift, probe_seasonal_confounding],
    "recurrence": [probe_trend_vs_level, probe_dropout, probe_seasonal_confounding],
}


# ============================================================================ improvers
@dataclass
class RunLog:
    name: str
    trace: list = field(default_factory=list)
    inquiry_memory: list = field(default_factory=list)
    anomalies: list = field(default_factory=list)
    final_cfg: dict = None
    steer: float = 0.0
    heldout: float = 0.0
    baseline_steer: float = 0.0
    baseline_heldout: float = 0.0
    spent: float = 0.0

    def thrash(self) -> dict:
        names = [s.name for s in self.trace]
        opp = sum(1 for i in range(1, len(self.trace))
                  if self.trace[i].edit["op"] == INVERSE.get(self.trace[i - 1].edit["op"]))
        repeats = sum(1 for i, s in enumerate(self.trace) if not s.accepted
                      and any(t.name == s.name and not t.accepted for t in self.trace[:i]))
        return {"opposing_pairs": opp, "repeated_failed_patches": repeats,
                "accepted": sum(s.accepted for s in self.trace), "attempts": len(names)}


def run(mode: str, seed: int, budget: float = 20.0, fleet_seed: int = 7,
        memory: list | None = None, firmware_factor: float = 2.2, log=None) -> RunLog:
    """mode = 'naive' or 'so_rsi'. `memory` = inquiry memory inherited from an earlier campaign."""
    rng = random.Random(seed)
    gym = TurbineGym(seed=fleet_seed, budget=budget, firmware_factor=firmware_factor)
    out = RunLog(mode)
    cfg = baseline_config()
    cur = gym.evaluate(cfg)
    out.baseline_steer = cur["f1"]
    banned: set[str] = set()                     # second-order revision of the policy itself
    stale: set[str] = set()                      # patches that recurred-and-failed on this incumbent
    queue: list[tuple[dict, dict]] = []          # structural edits waiting to be tested
    view = None
    probed: set[str] = set()

    def run_probe(fn):
        nonlocal view
        if fn.__name__ in probed:
            return None
        if view is None:
            view = gym.sensor_view()
        gym._charge("probe", fn.__name__)
        probed.add(fn.__name__)
        f = fn(view)
        f["probe"] = fn.__name__
        f["status"] = "unresolved" if f["supported"] else "refuted-by-probe"
        out.inquiry_memory.append(f)
        if f["supported"]:
            queue.append((f["edit"], f))
        if log:
            log(f"      probe {fn.__name__:28s} {f['evidence']:58s} -> "
                f"{'HYPOTHESIS: ' + f['hypothesis'] if f['supported'] else 'no evidence'}")
        return f

    # inherited inquiry memory: re-verify each supported hypothesis with its probe, then test it
    if mode == "so_rsi" and memory:
        for m in memory:
            if m["status"] == "supported":
                fn = globals()[m["probe"]]
                try:
                    run_probe(fn)
                except BudgetExceeded:
                    break

    for i in range(200):
        source = "policy"
        if mode == "so_rsi" and queue:
            e, finding = queue.pop(0)
            pred, sym, source = "f1_up", symptom(cur), "inquiry"
        else:
            e, pred, sym = first_order_proposal(cfg, cur, rng)
            if mode == "so_rsi" and (e["op"] in banned or edits.describe(e) in stale):
                for _ in range(50):                               # spend the slot elsewhere
                    e, pred = edits.random_edit(cfg, rng), "f1_up"
                    if e["op"] not in banned and edits.describe(e) not in stale:
                        break
        cand = edits.apply(cfg, e)
        if cand == cfg:
            continue
        try:
            r = gym.evaluate(cand)
        except BudgetExceeded:
            break
        acc = r["f1"] > cur["f1"]
        step = Step(i, e, pred, sym, cur, r, acc, source)
        out.trace.append(step)
        if log:
            log(f"  [{len(out.trace):2d}] {source:7s} {sym:15s} {step.name:34s} "
                f"F1 {cur['f1']:.3f} -> {r['f1']:.3f} {'ACCEPT' if acc else 'reject'}")
        if source == "inquiry":
            finding["status"] = "supported" if acc else "refuted-by-test"
            if acc and "followup" in finding:
                queue.insert(0, (finding["followup"], dict(finding, status="unresolved")))
            if acc and e["arg"] in ("firmware_rescale", "turbine_zscore"):
                banned.discard("threshold_up"); banned.discard("threshold_down")
        if acc:
            cfg, cur = cand, r
            stale.clear()                          # new incumbent: old failures may not apply

        if mode == "so_rsi":
            an = detect_anomalies(out.trace, step)
            for a in an:
                out.anomalies.append((len(out.trace), a, step.name))
                if log:
                    log(f"      ANOMALY {a} on {step.name}")
                if a == "opposing" and step.edit["op"].startswith("threshold"):
                    banned.update({"threshold_up", "threshold_down"})
                if a == "recurrence":
                    stale.add(step.name)
                for fn in PROBES_FOR[a]:
                    try:
                        run_probe(fn)
                    except BudgetExceeded:
                        break

    out.final_cfg, out.steer = cfg, cur["f1"]
    out.heldout = gym.audit_heldout(cfg)["f1"]
    out.baseline_heldout = gym.audit_heldout(baseline_config())["f1"]
    out.spent = gym.spent
    return out
