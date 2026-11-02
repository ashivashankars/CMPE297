"""Project 06 - Streaming anomaly detection on the Numenta Anomaly Benchmark (NAB).

Business question: alert operators to real machine/system failures early, without crying wolf.

Data: 5 real NAB series whose anomaly windows are known causes (machine failure, AWS
misconfiguration, EC2 latency failure, NYC taxi holidays/storm, ambient temperature failure).

Honesty rules (these are what usually make published anomaly numbers meaningless):
  * Every detector is CAUSAL: the score at time t only uses data up to t.
  * Detectors are fit on the first 15% of each series (NAB's "probation" period) and never refit.
  * Alert thresholds come from the probation-period score distribution, NOT from the labels.
    Labels are only used to score the result.
  * Scoring is event-level (was each failure window caught? how early? how many false alarms
    per day?) as well as point-level PR-AUC.
Run:  python projects/06_anomaly_detection/anomaly_pipeline.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import RobustScaler

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
from shared.report_io import dump  # noqa: E402

RAW = HERE.parents[1] / "data" / "raw"
ART = HERE / "artifacts"
SEED = 42
PROBATION = 0.15
SERIES = {
    "machine_temperature": ("nab_machine_temperature.csv", "realKnownCause/machine_temperature_system_failure.csv",
                            "Industrial machine temperature sensor; known catastrophic failure"),
    "ambient_temperature": ("nab_ambient_temperature.csv", "realKnownCause/ambient_temperature_system_failure.csv",
                            "Office ambient temperature during an HVAC system failure"),
    "cpu_asg_misconfig": ("nab_cpu_asg_misconfig.csv", "realKnownCause/cpu_utilization_asg_misconfiguration.csv",
                          "AWS CPU utilization after an auto-scaling group misconfiguration"),
    "ec2_latency": ("nab_ec2_latency.csv", "realKnownCause/ec2_request_latency_system_failure.csv",
                    "EC2 request latency ahead of a system failure"),
    "nyc_taxi": ("nab_nyc_taxi.csv", "realKnownCause/nyc_taxi.csv",
                 "NYC taxi demand (30-min): marathon, Thanksgiving, Christmas, New Year, blizzard"),
}
METHODS = ["Rolling robust z", "Seasonal residual z", "Isolation Forest", "Local Outlier Factor", "Ensemble (rank mean)"]


def load(name: str) -> tuple[pd.DataFrame, list[tuple[pd.Timestamp, pd.Timestamp]]]:
    csv, key, _ = SERIES[name]
    df = pd.read_csv(RAW / csv, parse_dates=["timestamp"])
    windows = [(pd.Timestamp(a), pd.Timestamp(b)) for a, b in json.loads((RAW / "nab_labels.json").read_text())[key]]
    df["label"] = False
    for a, b in windows:
        df.loc[df["timestamp"].between(a, b), "label"] = True
    return df, windows


def points_per_day(df: pd.DataFrame) -> int:
    step = df["timestamp"].diff().median()
    return max(4, int(pd.Timedelta("1D") / step))


def causal_features(v: pd.Series, ppd: int) -> pd.DataFrame:
    """Window features that only look backwards (rolling windows end at t)."""
    w = max(6, ppd // 4)
    roll = v.rolling(w, min_periods=3)
    f = pd.DataFrame({
        "value": v,
        "diff1": v.diff(),
        "dev_from_mean": v - roll.mean(),
        "roll_std": roll.std(),
        "dev_from_yesterday": v - v.shift(ppd),
        "slope": v.diff(w) / w,
    })
    return f.bfill().fillna(0.0)


def score_series(v: pd.Series, ppd: int) -> dict[str, np.ndarray]:
    """Return an anomaly score per method; higher = more anomalous. All causal."""
    n = len(v)
    n_prob = int(n * PROBATION)
    scores: dict[str, np.ndarray] = {}

    # 1. rolling robust z-score: |x - median| / MAD over the trailing day
    med = v.rolling(ppd, min_periods=10).median()
    mad = (v - med).abs().rolling(ppd, min_periods=10).median() * 1.4826
    # stats are shifted by one step: x_t is compared with statistics from t-1 and earlier
    scores["Rolling robust z"] = ((v - med.shift(1)).abs() / (mad.shift(1) + 1e-9)).fillna(0).to_numpy()

    # 2. seasonal residual: deviation from the median of the same time of day over the last 7 days
    lags = pd.concat([v.shift(ppd * k) for k in range(1, 8)], axis=1)
    seasonal = lags.median(axis=1)
    resid = (v - seasonal)
    rmad = resid.abs().rolling(ppd * 3, min_periods=10).median().shift(1) * 1.4826
    scores["Seasonal residual z"] = (resid.abs() / (rmad + 1e-9)).fillna(0).to_numpy()

    # 3/4. model-based detectors fit on probation only
    X = causal_features(v, ppd)
    scaler = RobustScaler().fit(X.iloc[:n_prob])
    Xs = np.clip(scaler.transform(X), -50, 50)
    iso = IsolationForest(n_estimators=200, random_state=SEED).fit(Xs[:n_prob])
    scores["Isolation Forest"] = -iso.score_samples(Xs)
    lof = LocalOutlierFactor(n_neighbors=35, novelty=True).fit(Xs[:n_prob])
    scores["Local Outlier Factor"] = -lof.score_samples(Xs)

    # 5. ensemble: mean of each detector's percentile rank within its own probation distribution.
    #    Ranks make scores on different scales comparable; a small "excess over the probation max"
    #    term breaks ties among points that beat every probation score.
    ranks, excess = [], []
    for m in METHODS[:-1]:
        ref = np.sort(scores[m][:n_prob])
        ranks.append(np.searchsorted(ref, scores[m], side="right") / len(ref))
        excess.append(np.clip(scores[m] / (ref[-1] + 1e-9) - 1, 0, 10))
    scores["Ensemble (rank mean)"] = np.mean(ranks, axis=0) + 0.01 * np.mean(excess, axis=0)
    return scores


def alerts_from(score: np.ndarray, n_prob: int, quantile: float, refractory: int) -> np.ndarray:
    """Threshold = probation quantile (label-free). Suppress repeats within a refractory period."""
    thr = np.quantile(score[:n_prob], quantile)
    raw = np.where(score > thr)[0]
    raw = raw[raw >= n_prob]  # no alerts during probation, as in NAB
    out, last = [], -10**9
    for i in raw:
        if i - last > refractory:
            out.append(i)
            last = i
    return np.array(out, int)


def evaluate(df: pd.DataFrame, windows, score: np.ndarray, alerts: np.ndarray, n_prob: int) -> dict:
    ts = df["timestamp"]
    lab = df["label"].to_numpy()
    detected, lead = 0, []
    in_window = np.zeros(len(alerts), bool)
    for a, b in windows:
        idx = [i for i in alerts if a <= ts[i] <= b]
        for i in idx:
            in_window[np.where(alerts == i)[0]] = True
        if idx:
            detected += 1
            lead.append((ts[idx[0]] - a) / (b - a))  # 0 = alerted at window start
    days = (ts.iloc[-1] - ts.iloc[n_prob]).total_seconds() / 86400
    post = slice(n_prob, None)
    return {
        "windows": len(windows), "detected": detected,
        "recall_events": detected / len(windows),
        "false_alarms": int((~in_window).sum()), "false_alarms_per_week": float((~in_window).sum() / days * 7),
        "alert_precision": float(in_window.mean()) if len(alerts) else 0.0,
        "mean_detection_position": float(np.mean(lead)) if lead else None,
        "pr_auc": float(average_precision_score(lab[post], score[post])) if lab[post].any() else None,
        "pr_auc_base_rate": float(lab[post].mean()),
    }


def run(quantile: float = 0.999) -> dict:
    t0 = time.time()
    ART.mkdir(exist_ok=True)
    results, payload, curve = [], {}, []
    for name, (_, _, desc) in SERIES.items():
        df, windows = load(name)
        ppd = points_per_day(df)
        n_prob = int(len(df) * PROBATION)
        scores = score_series(df["value"], ppd)
        series_payload = {"description": desc, "points_per_day": ppd, "n": len(df), "n_probation": n_prob,
                          "timestamps": df["timestamp"].dt.strftime("%Y-%m-%d %H:%M").tolist(),
                          "values": df["value"].round(3).tolist(),
                          "windows": [[str(a), str(b)] for a, b in windows], "scores": {}, "alerts": {}}
        for m in METHODS:
            s = scores[m]
            al = alerts_from(s, n_prob, quantile, refractory=ppd // 2)
            results.append({"series": name, "method": m, **evaluate(df, windows, s, al, n_prob)})
            # scores are shipped as probation-percentiles so the UI can re-threshold without the server
            ref = np.sort(s[:n_prob])
            pct = np.searchsorted(ref, s, side="right") / len(ref)
            series_payload["scores"][m] = np.round(np.minimum(pct, 1) + 0.001 * np.clip(s / (ref[-1] + 1e-9) - 1, 0, 50), 5).tolist()
            series_payload["alerts"][m] = al.tolist()
            # operating curve: same label-free thresholding at several sensitivities
            for q in [0.98, 0.99, 0.995, 0.999, 0.9995, 1.0]:
                ev = evaluate(df, windows, s, alerts_from(s, n_prob, q, ppd // 2), n_prob)
                curve.append({"series": name, "method": m, "quantile": q, "detected": ev["detected"],
                              "windows": ev["windows"], "fa_per_week": ev["false_alarms_per_week"]})
        payload[name] = series_payload
    res = pd.DataFrame(results)
    summary = (res.groupby("method", sort=False)
               .agg(windows=("windows", "sum"), detected=("detected", "sum"), false_alarms=("false_alarms", "sum"),
                    fa_per_week=("false_alarms_per_week", "mean"), pr_auc=("pr_auc", "mean"),
                    alert_precision=("alert_precision", "mean"), detection_position=("mean_detection_position", "mean"))
               .reset_index())
    summary["recall_events"] = summary["detected"] / summary["windows"]
    report = {
        "threshold_quantile": quantile, "probation_fraction": PROBATION,
        "per_series": results, "summary": summary.to_dict("records"),
        "operating_curve": (pd.DataFrame(curve).groupby(["method", "quantile"], sort=False)
                            .agg(detected=("detected", "sum"), windows=("windows", "sum"), fa_per_week=("fa_per_week", "mean"))
                            .reset_index().to_dict("records")),
        "series_meta": {k: {"description": v[2]} for k, v in SERIES.items()},
        "runtime_sec": round(time.time() - t0, 1),
    }
    dump(report, ART / "report.json")
    dump(payload, ART / "series.json")
    return report


if __name__ == "__main__":
    rep = run()
    print(pd.DataFrame(rep["summary"]).round(3).to_string(index=False))
    print("runtime", rep["runtime_sec"])
