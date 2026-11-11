"""
Pipeline-as-code.

The object every improver edits is a *program*: a small Python module that turns raw
sensor rows into features and builds a classifier. A pipeline is described by a config
dict, rendered to real Python source, and the evaluator exec()s that source.

Because the source is real code, an "edit" is a real code diff, and Budget RSI can read
features off the unified diff *before* the edit is run.
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re

BASE_FEATURES = ["vibration", "oil_temp", "ambient_temp", "wind_speed",
                 "power", "rotor_rpm", "particles"]

# ---------------------------------------------------------------------------
# Transform catalogue. Each entry = (python source of the function, derived columns).
# Order inside a pipeline matters (e.g. rescale before z-scoring).
# ---------------------------------------------------------------------------
TRANSFORMS: dict[str, tuple[str, list[str]]] = {
    "impute_particles": ('''
def t_impute_particles(df):
    """Sensor dropout: forward-fill per turbine, then fall back to the median."""
    df["particles"] = df.groupby("turbine_id")["particles"].ffill()
    df["particles"] = df["particles"].fillna(df["particles"].median())
    return df
''', []),
    "firmware_rescale": ('''
def t_firmware_rescale(df):
    """Undo the firmware-v2 unit change, factor estimated on TRAIN rows only."""
    tr = df[df.day < TRAIN_END]
    both = tr.groupby("turbine_id").firmware.nunique()
    ids = both[both == 2].index
    ratios = []
    for tid in ids:
        t = tr[tr.turbine_id == tid]
        ratios.append(t[t.firmware == 2].vibration.median() / t[t.firmware == 1].vibration.median())
    factor = float(np.median(ratios)) if ratios else 1.0
    df.loc[df.firmware == 2, "vibration"] = df.loc[df.firmware == 2, "vibration"] / factor
    return df
''', []),
    "turbine_zscore": ('''
def t_turbine_zscore(df):
    """Remove per-sensor calibration: z-score against each turbine's first 60 days."""
    base = df[df.day < 60].groupby("turbine_id")
    for col in ["vibration", "oil_temp"]:
        mu = df.turbine_id.map(base[col].median())
        sd = df.turbine_id.map(base[col].std()).replace(0, 1)
        df[col + "_z"] = (df[col] - mu) / sd
    return df
''', ["vibration_z", "oil_temp_z"]),
    "oil_residual": ('''
def t_oil_residual(df):
    """Remove seasonal + load confounding from oil temperature (fit on TRAIN rows)."""
    tr = df[df.day < TRAIN_END]
    X = np.c_[np.ones(len(tr)), tr.ambient_temp, tr.power]
    coef, *_ = np.linalg.lstsq(X, tr.oil_temp, rcond=None)
    df["oil_resid"] = df.oil_temp - np.c_[np.ones(len(df)), df.ambient_temp, df.power] @ coef
    return df
''', ["oil_resid"]),
    "vib_roll7": ('''
def t_vib_roll7(df):
    """7-day rolling mean of vibration (per turbine, past only)."""
    df["vib_roll7"] = df.groupby("turbine_id")["vibration"].transform(
        lambda s: s.rolling(7, min_periods=1).mean())
    return df
''', ["vib_roll7"]),
    "vib_slope14": ('''
def t_vib_slope14(df):
    """Wear trend: 14-day change in smoothed vibration, relative to its level."""
    g = df.groupby("turbine_id")["vibration"]
    sm = g.transform(lambda s: s.rolling(5, min_periods=1).mean())
    prev = sm.groupby(df.turbine_id).shift(14)
    df["vib_slope14"] = ((sm - prev) / prev).fillna(0.0)
    return df
''', ["vib_slope14"]),
    "oil_slope14": ('''
def t_oil_slope14(df):
    """Wear trend in oil temperature residual-free proxy: 14-day change of oil - ambient."""
    gap = (df.oil_temp - df.ambient_temp)
    sm = gap.groupby(df.turbine_id).transform(lambda s: s.rolling(5, min_periods=1).mean())
    df["oil_slope14"] = (sm - sm.groupby(df.turbine_id).shift(14)).fillna(0.0)
    return df
''', ["oil_slope14"]),
    "particle_log": ('''
def t_particle_log(df):
    """Particle counts are heavy-tailed: log1p them."""
    df["particles_log"] = np.log1p(df["particles"])
    return df
''', ["particles_log"]),
}
TRANSFORM_NAMES = list(TRANSFORMS)
# canonical order used when inserting a transform (keeps rescale before z-score etc.)
CANONICAL_ORDER = ["impute_particles", "firmware_rescale", "turbine_zscore", "oil_residual",
                   "vib_roll7", "vib_slope14", "oil_slope14", "particle_log"]

MODELS = {
    "logreg": ("from sklearn.linear_model import LogisticRegression\n"
               "from sklearn.preprocessing import StandardScaler\n"
               "from sklearn.pipeline import make_pipeline",
               "make_pipeline(StandardScaler(), LogisticRegression(C={C}, class_weight={cw}, max_iter=1000))"),
    "tree": ("from sklearn.tree import DecisionTreeClassifier",
             "DecisionTreeClassifier(max_depth={max_depth}, min_samples_leaf=20, class_weight={cw}, random_state=0)"),
    "hgb": ("from sklearn.ensemble import HistGradientBoostingClassifier",
            "HistGradientBoostingClassifier(max_depth={max_depth}, learning_rate={lr}, max_iter=80, "
            "class_weight={cw}, random_state=0)"),
}
DEFAULT_PARAMS = {"C": 1.0, "max_depth": 3, "lr": 0.1}


def baseline_config() -> dict:
    """The seed program every improver starts from."""
    return {
        "transforms": [],
        "features": ["vibration", "oil_temp", "ambient_temp", "wind_speed", "power", "rotor_rpm"],
        "model": "logreg",
        "params": dict(DEFAULT_PARAMS),
        "class_weight": None,
        "alarm_rate": 0.08,
    }


def normalise(cfg: dict) -> dict:
    cfg = copy.deepcopy(cfg)
    cfg["transforms"] = [t for t in CANONICAL_ORDER if t in set(cfg["transforms"])]
    cfg["features"] = [f for f in BASE_FEATURES if f in set(cfg["features"])]
    cfg["alarm_rate"] = round(min(0.30, max(0.01, cfg["alarm_rate"])), 4)
    p = cfg["params"]
    p["C"] = round(min(100.0, max(0.001, p["C"])), 4)
    p["max_depth"] = int(min(8, max(1, p["max_depth"])))
    p["lr"] = round(min(0.5, max(0.01, p["lr"])), 4)
    return cfg


def derived_features(cfg: dict) -> list[str]:
    out = []
    for t in cfg["transforms"]:
        out += TRANSFORMS[t][1]
    return out


def config_key(cfg: dict) -> str:
    return hashlib.sha1(json.dumps(normalise(cfg), sort_keys=True).encode()).hexdigest()[:10]


def render(cfg: dict) -> str:
    """Render a config to a self-contained Python module (the program under improvement)."""
    cfg = normalise(cfg)
    imp, ctor = MODELS[cfg["model"]]
    cw = "'balanced'" if cfg["class_weight"] == "balanced" else "None"
    p = cfg["params"]
    feats = cfg["features"] + derived_features(cfg)
    lines = [
        "# AUTO-GENERATED turbine early-warning pipeline",
        "import numpy as np",
        "import pandas as pd",
        imp,
        "",
        f"TRAIN_END = 210",
        f"FEATURES = {feats!r}",
        f"ALARM_RATE = {cfg['alarm_rate']}   # alarm bar = score quantile that flags this share of TRAIN rows",
    ]
    for t in cfg["transforms"]:
        lines.append(TRANSFORMS[t][0].rstrip())
    lines += ["", "", "def build_features(df):", "    df = df.sort_values(['turbine_id', 'day']).copy()"]
    for t in cfg["transforms"]:
        lines.append(f"    df = t_{t}(df)")
    lines += ["    X = df[FEATURES].fillna(0.0)", "    return df, X", "", "",
              "def make_model():",
              "    return " + ctor.format(C=p["C"], max_depth=p["max_depth"], lr=p["lr"], cw=cw), ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Diff features for Budget RSI: computed from the unified diff text ONLY.
# ---------------------------------------------------------------------------
DIFF_FEATURE_NAMES = ["lines_net", "funcs_net", "groupby_ops_delta", "window_ops_delta",
                      "features_delta", "alarm_rate_delta", "ensemble_delta", "balanced_delta"]


def unified_diff(parent_src: str, child_src: str) -> list[str]:
    return list(difflib.unified_diff(parent_src.splitlines(), child_src.splitlines(), lineterm="", n=0))


def _value(lines: list[str], name: str):
    for l in lines:
        if l.startswith(name + " = "):
            return l.split(" = ", 1)[1]
    return None


def diff_features(parent_src: str, child_src: str) -> list[float]:
    """Eight coordinates read off the unified diff text. Nothing is executed."""
    d = unified_diff(parent_src, child_src)
    add = [l[1:] for l in d if l.startswith("+") and not l.startswith("+++")]
    rem = [l[1:] for l in d if l.startswith("-") and not l.startswith("---")]
    count = lambda ls, pat: sum(len(re.findall(pat, l)) for l in ls)
    delta = lambda pat: float(count(add, pat) - count(rem, pat))

    fa, fr = _value(add, "FEATURES"), _value(rem, "FEATURES")
    feat_delta = float(len(eval(fa)) - len(eval(fr))) if fa and fr else 0.0
    ta, tr = _value(add, "ALARM_RATE"), _value(rem, "ALARM_RATE")
    thr_delta = float(ta.split("#")[0]) - float(tr.split("#")[0]) if ta and tr else 0.0
    return [
        float(len(add) - len(rem)),            # lines_net: how much code the edit adds
        delta(r"^def "),                       # funcs_net: transforms added minus removed
        delta(r"groupby"),                     # per-turbine operations (calibration-aware code)
        delta(r"rolling|shift"),               # time-window operations (trend-aware code)
        feat_delta,                            # change in model input width
        thr_delta,                             # signed change of the alarm rate
        delta(r"Boosting|Forest"),             # move to / away from an ensemble model
        delta(r"'balanced'"),                  # class re-weighting switched on / off
    ]
