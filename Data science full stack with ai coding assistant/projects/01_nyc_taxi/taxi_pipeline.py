"""Project 01 - NYC taxi trip duration: an end-to-end CRISP-DM pipeline.

Business question: at booking time, how long will this ride take, and how sure are we?

Data: 6,433 real NYC TLC yellow/green rides from March 2019 (seaborn mirror).
Key design choices (each one is shown in the app):
  * Temporal split, never random: fit Mar 1-14 | tune Mar 15-20 | calibrate Mar 21-24 | test Mar 25-31.
    The test week is touched exactly once, at the end.
  * Only booking-time features. fare / tip / tolls / total are computed *after* the trip,
    so they leak the answer. A "leaky" model is trained on purpose to show the trap.
  * AutoResearch-style hill climbing over hyperparameters, scored on the tune week only.
  * Split-conformal prediction intervals so every estimate ships with a 90% range.
Run:  python projects/01_nyc_taxi/taxi_pipeline.py
"""
from __future__ import annotations

import pathlib
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
from shared.report_io import dump  # noqa: E402

RAW = HERE.parents[1] / "data" / "raw" / "taxis.csv"
ART = HERE / "artifacts"
SEED = 42

CAT = ["pickup_zone", "dropoff_zone", "pickup_borough", "dropoff_borough", "color"]
NUM = ["distance", "log_distance", "hour", "dow", "is_weekend", "same_zone", "passengers", "hour_sin", "hour_cos"]
FEATURES = CAT + NUM
LEAKY = ["fare", "tip", "tolls", "total"]  # only known after drop-off


# --------------------------------------------------------------------------- data
def load() -> pd.DataFrame:
    df = pd.read_csv(RAW, parse_dates=["pickup", "dropoff"])
    df["duration_min"] = (df["dropoff"] - df["pickup"]).dt.total_seconds() / 60
    return df


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Rules are fixed up front (not tuned on test results) and logged."""
    log = {"rows_in": len(df)}
    rules = {
        "zero_or_negative_duration": df["duration_min"] < 1,
        "zero_distance": df["distance"] <= 0,
        "implausible_speed_gt_60mph": df["distance"] / (df["duration_min"] / 60).clip(lower=1e-6) > 60,
        "missing_zone": df["pickup_zone"].isna() | df["dropoff_zone"].isna(),
    }
    drop = np.zeros(len(df), bool)
    for name, mask in rules.items():
        log[name] = int((mask & ~drop).sum())
        drop |= mask.to_numpy()
    out = df.loc[~drop].copy()
    log["rows_out"] = len(out)
    return out, log


def featurize(df: pd.DataFrame) -> pd.DataFrame:
    """Booking-time features only. Pure function of a single row -> no leakage."""
    out = df.copy()
    out["hour"] = out["pickup"].dt.hour
    out["dow"] = out["pickup"].dt.dayofweek
    out["is_weekend"] = (out["dow"] >= 5).astype(int)
    out["hour_sin"] = np.sin(2 * np.pi * out["hour"] / 24)
    out["hour_cos"] = np.cos(2 * np.pi * out["hour"] / 24)
    out["log_distance"] = np.log1p(out["distance"])
    out["same_zone"] = (out["pickup_zone"] == out["dropoff_zone"]).astype(int)
    for c in CAT:
        out[c] = out[c].fillna("Unknown").astype(str)
    return out


def temporal_split(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    d = df["pickup"]
    return {
        "fit": df[d < "2019-03-15"],
        "tune": df[(d >= "2019-03-15") & (d < "2019-03-21")],
        "calibrate": df[(d >= "2019-03-21") & (d < "2019-03-25")],
        "test": df[d >= "2019-03-25"],
    }


# --------------------------------------------------------------------------- models
def gbm(**params) -> Pipeline:
    enc = ColumnTransformer(
        [("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-1), CAT)],
        remainder="passthrough", verbose_feature_names_out=False,
    )
    model = HistGradientBoostingRegressor(
        categorical_features=list(range(len(CAT))), random_state=SEED, **params)
    return Pipeline([("enc", enc), ("model", model)])


def ridge() -> Pipeline:
    enc = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=5), CAT),
        ("num", StandardScaler(), NUM),
    ])
    return Pipeline([("enc", enc), ("model", Ridge(alpha=3.0))])


def metrics(y_true_min: np.ndarray, y_pred_min: np.ndarray) -> dict:
    y_pred_min = np.clip(y_pred_min, 0.5, None)
    return {
        "mae_min": float(mean_absolute_error(y_true_min, y_pred_min)),
        "rmsle": float(np.sqrt(np.mean((np.log1p(y_pred_min) - np.log1p(y_true_min)) ** 2))),
        "r2": float(r2_score(y_true_min, y_pred_min)),
        "median_ae_min": float(np.median(np.abs(y_true_min - y_pred_min))),
    }


def autoresearch(fit: pd.DataFrame, tune: pd.DataFrame, n_trials: int = 30) -> tuple[dict, list]:
    """Greedy hill climbing: perturb the best config, keep it only if tune-week RMSLE improves."""
    rng = np.random.default_rng(SEED)
    space = {
        "learning_rate": [0.03, 0.05, 0.08, 0.12],
        "max_leaf_nodes": [15, 31, 63],
        "min_samples_leaf": [10, 20, 40, 80],
        "l2_regularization": [0.0, 0.1, 1.0, 3.0],
        "max_iter": [200, 400, 700],
    }
    best = {"learning_rate": 0.08, "max_leaf_nodes": 31, "min_samples_leaf": 20, "l2_regularization": 0.0, "max_iter": 200}
    yf, Xf = np.log1p(fit["duration_min"]), fit[FEATURES]

    def score(cfg):
        m = gbm(**cfg).fit(Xf, yf)
        return metrics(tune["duration_min"].to_numpy(), np.expm1(m.predict(tune[FEATURES])))["rmsle"]

    best_score = score(best)
    trials = [{"trial": 0, "params": dict(best), "tune_rmsle": best_score, "accepted": True, "best_so_far": best_score}]
    for t in range(1, n_trials + 1):
        cand = dict(best)
        for k in rng.choice(list(space), size=rng.integers(1, 3), replace=False):
            cand[k] = space[k][rng.integers(len(space[k]))]
        s = score(cand)
        accepted = s < best_score - 1e-5
        if accepted:
            best, best_score = cand, s
        trials.append({"trial": t, "params": cand, "tune_rmsle": s, "accepted": bool(accepted), "best_so_far": best_score})
    return best, trials


def conformal_q(model, cal: pd.DataFrame, alpha: float) -> float:
    """Split conformal on log scale: q = ceil((n+1)(1-a))/n quantile of |residual|."""
    resid = np.abs(np.log1p(cal["duration_min"]) - model.predict(cal[FEATURES]))
    n = len(resid)
    level = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
    return float(np.quantile(resid, level, method="higher"))


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index between train (expected) and test (actual)."""
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    e = np.histogram(expected, edges)[0] / len(expected) + 1e-4
    a = np.histogram(np.clip(actual, edges[0], edges[-1]), edges)[0] / len(actual) + 1e-4
    return float(np.sum((a - e) * np.log(a / e)))


# --------------------------------------------------------------------------- run
def run() -> dict:
    t0 = time.time()
    ART.mkdir(exist_ok=True)
    raw = load()
    df, clean_log = clean(raw)
    df = featurize(df)
    parts = temporal_split(df)
    fit, tune, cal, test = parts["fit"], parts["tune"], parts["calibrate"], parts["test"]
    dev = pd.concat([fit, tune])  # final model trains on fit+tune, never sees cal/test
    y_test = test["duration_min"].to_numpy()

    # --- leaderboard (all models fit on dev, scored once on test)
    board = []
    med = float(dev["duration_min"].median())
    board.append({"model": "Global median (baseline)", **metrics(y_test, np.full(len(test), med))})
    speed = float((dev["distance"] / (dev["duration_min"] / 60)).median())  # mph
    board.append({"model": f"Distance / median speed ({speed:.1f} mph)", **metrics(y_test, test["distance"] / speed * 60)})
    r = ridge().fit(dev[FEATURES], np.log1p(dev["duration_min"]))
    board.append({"model": "Ridge (one-hot zones + time)", **metrics(y_test, np.expm1(r.predict(test[FEATURES])))})
    default = gbm().fit(dev[FEATURES], np.log1p(dev["duration_min"]))
    board.append({"model": "HistGBM default", **metrics(y_test, np.expm1(default.predict(test[FEATURES])))})

    best_params, trials = autoresearch(fit, tune)
    final = gbm(**best_params).fit(dev[FEATURES], np.log1p(dev["duration_min"]))
    pred_test = np.expm1(final.predict(test[FEATURES]))
    board.append({"model": "HistGBM + AutoResearch (champion)", **metrics(y_test, pred_test), "champion": True})

    # --- the leakage trap, trained on purpose
    leak_feats = FEATURES + LEAKY
    leak = Pipeline([("enc", ColumnTransformer([("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), CAT)],
                                               remainder="passthrough")),
                     ("model", HistGradientBoostingRegressor(categorical_features=list(range(len(CAT))), random_state=SEED))])
    leak.fit(dev[leak_feats], np.log1p(dev["duration_min"]))
    leak_metrics = metrics(y_test, np.expm1(leak.predict(test[leak_feats])))

    # --- conformal intervals at several levels, coverage measured on the untouched test week
    intervals = {}
    for alpha in (0.2, 0.1, 0.05):
        q = conformal_q(final, cal, alpha)
        lo, hi = np.expm1(final.predict(test[FEATURES]) - q), np.expm1(final.predict(test[FEATURES]) + q)
        intervals[f"{int((1 - alpha) * 100)}"] = {
            "q_log": q, "coverage": float(np.mean((y_test >= lo) & (y_test <= hi))),
            "median_width_min": float(np.median(hi - lo)),
        }

    # --- explainability: permutation importance on test (model-agnostic)
    pi = permutation_importance(final, test[FEATURES], np.log1p(y_test), n_repeats=5, random_state=SEED,
                                scoring="neg_root_mean_squared_error")
    importance = sorted(({"feature": f, "importance": float(m), "std": float(s)}
                         for f, m, s in zip(FEATURES, pi.importances_mean, pi.importances_std)),
                        key=lambda d: -d["importance"])

    # --- error analysis slices
    test = test.assign(pred=pred_test, abs_err=np.abs(pred_test - y_test))
    slices = {
        "pickup_borough": test.groupby("pickup_borough").agg(n=("abs_err", "size"), mae=("abs_err", "mean")).reset_index(),
        "hour_bucket": test.assign(hour_bucket=pd.cut(test["hour"], [-1, 5, 9, 15, 19, 23],
                                                      labels=["night 0-5", "AM rush 6-9", "midday 10-15", "PM rush 16-19", "evening 20-23"]))
                       .groupby("hour_bucket", observed=True).agg(n=("abs_err", "size"), mae=("abs_err", "mean")).reset_index(),
        "distance_bucket": test.assign(distance_bucket=pd.cut(test["distance"], [0, 1, 2, 4, 8, 50],
                                                              labels=["<1 mi", "1-2 mi", "2-4 mi", "4-8 mi", "8+ mi"]))
                           .groupby("distance_bucket", observed=True).agg(n=("abs_err", "size"), mae=("abs_err", "mean")).reset_index(),
    }
    slices = {k: v.astype({v.columns[0]: str}).to_dict("records") for k, v in slices.items()}

    # --- drift monitor (train vs test)
    drift = [{"feature": f, "psi": psi(dev[f].to_numpy(float), test[f].to_numpy(float))}
             for f in ["distance", "hour", "dow", "passengers", "duration_min"]]

    # --- EDA payload
    sample = df.sample(1500, random_state=SEED)
    heat = df.pivot_table(index="dow", columns="hour", values="duration_min", aggfunc="median").reindex(range(7))
    eda = {
        "n_rows": len(df), "date_range": [str(df["pickup"].min()), str(df["pickup"].max())],
        "duration_hist": np.histogram(df["duration_min"], bins=40, range=(0, 80))[0].tolist(),
        "scatter": {"distance": sample["distance"].round(2).tolist(), "duration": sample["duration_min"].round(2).tolist(),
                    "borough": sample["pickup_borough"].tolist()},
        "heatmap": {"z": heat.round(1).where(heat.notna(), None).values.tolist(), "hours": list(range(24)),
                    "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
        "by_borough": df.groupby("pickup_borough")["duration_min"].describe()[["count", "mean", "50%"]]
                       .reset_index().rename(columns={"50%": "median"}).round(2).to_dict("records"),
        "correlations": raw[["passengers", "distance", "fare", "tip", "tolls", "total", "duration_min"]].corr()["duration_min"].round(3).to_dict(),
        "missing": raw.isna().sum()[raw.isna().sum() > 0].astype(int).to_dict(),
    }

    # --- lookup tables for the booking UI (built from dev data only)
    pair_dist = dev.groupby(["pickup_zone", "dropoff_zone"])["distance"].median()
    zones = dev.groupby("pickup_zone")["pickup_borough"].agg(lambda s: s.mode()[0]).to_dict()
    zones.update({z: b for z, b in dev.groupby("dropoff_zone")["dropoff_borough"].agg(lambda s: s.mode()[0]).items() if z not in zones})

    report = {
        "clean_log": clean_log,
        "split_sizes": {k: len(v) for k, v in parts.items()},
        "leaderboard": board,
        "leak_demo": {"features_added": LEAKY, **leak_metrics},
        "autoresearch": {"best_params": best_params, "trials": trials},
        "intervals": intervals,
        "importance": importance,
        "slices": slices,
        "drift": drift,
        "eda": eda,
        "test_residuals": {"pred": pred_test[:800].round(2).tolist(), "actual": y_test[:800].round(2).tolist()},
        "runtime_sec": round(time.time() - t0, 1),
    }
    joblib.dump({"model": final, "q": {k: v["q_log"] for k, v in intervals.items()}, "zones": zones,
                 "pair_distance": {f"{a}|||{b}": float(v) for (a, b), v in pair_dist.items()},
                 "median_distance": float(dev["distance"].median())}, ART / "model.joblib")
    dump(report, ART / "report.json")
    return report


if __name__ == "__main__":
    rep = run()
    for row in rep["leaderboard"]:
        print(f"{row['model']:42s} MAE {row['mae_min']:6.2f} min  RMSLE {row['rmsle']:.3f}  R2 {row['r2']:.3f}")
    print("leaky model (DON'T SHIP):", {k: round(v, 3) for k, v in rep["leak_demo"].items() if k != "features_added"})
    print("conformal:", rep["intervals"])
    print("runtime", rep["runtime_sec"], "s")
