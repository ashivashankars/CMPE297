"""Edit operators: the moves an improver can make on a pipeline config."""
from __future__ import annotations

import copy
import random

from .pipeline import BASE_FEATURES, TRANSFORM_NAMES, MODELS, normalise


def describe(edit: dict) -> str:
    return edit["op"] + ("(" + str(edit.get("arg")) + ")" if "arg" in edit else "")


def apply(cfg: dict, edit: dict) -> dict:
    c = copy.deepcopy(cfg)
    op, arg = edit["op"], edit.get("arg")
    if op == "add_transform" and arg not in c["transforms"]:
        c["transforms"].append(arg)
    elif op == "remove_transform" and arg in c["transforms"]:
        c["transforms"].remove(arg)
    elif op == "add_feature" and arg not in c["features"]:
        c["features"].append(arg)
    elif op == "remove_feature" and arg in c["features"] and len(c["features"]) > 1:
        c["features"].remove(arg)
    elif op == "set_model":
        c["model"] = arg
    elif op == "class_weight":
        c["class_weight"] = arg
    elif op == "threshold_up":          # raise the alarm bar -> fewer alarms
        c["alarm_rate"] /= 1.3
    elif op == "threshold_down":        # lower the alarm bar -> more alarms
        c["alarm_rate"] *= 1.3
    elif op == "C_up":
        c["params"]["C"] *= 4
    elif op == "C_down":
        c["params"]["C"] /= 4
    elif op == "depth_up":
        c["params"]["max_depth"] += 1
    elif op == "depth_down":
        c["params"]["max_depth"] -= 1
    elif op == "lr_up":
        c["params"]["lr"] *= 2
    elif op == "lr_down":
        c["params"]["lr"] /= 2
    return normalise(c)


def legal_edits(cfg: dict) -> list[dict]:
    """All edits that change something about cfg."""
    out = []
    for t in TRANSFORM_NAMES:
        out.append({"op": "remove_transform" if t in cfg["transforms"] else "add_transform", "arg": t})
    for f in BASE_FEATURES:
        out.append({"op": "remove_feature" if f in cfg["features"] else "add_feature", "arg": f})
    for m in MODELS:
        if m != cfg["model"]:
            out.append({"op": "set_model", "arg": m})
    out.append({"op": "class_weight", "arg": None if cfg["class_weight"] else "balanced"})
    out += [{"op": o} for o in ["threshold_up", "threshold_down"]]
    if cfg["model"] == "logreg":
        out += [{"op": "C_up"}, {"op": "C_down"}]
    else:
        out += [{"op": "depth_up"}, {"op": "depth_down"}]
    if cfg["model"] == "hgb":
        out += [{"op": "lr_up"}, {"op": "lr_down"}]
    return [e for e in out if apply(cfg, e) != normalise(cfg)]


def random_edit(cfg: dict, rng: random.Random) -> dict:
    return rng.choice(legal_edits(cfg))
