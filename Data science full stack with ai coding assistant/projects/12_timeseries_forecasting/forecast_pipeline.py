"""Project 12 - Day-ahead to two-week electricity demand forecasting (Germany, OPSD 2006-2017).

Business question: grid operators buy power ahead of time. How much will Germany consume over
the next 1-14 days, and how wide should the safety margin be?

Validation design (the part most forecasting demos get wrong):
  * Rolling-origin backtest: 52 weekly forecast origins across 2017, each forecasting 14 days
    ahead using only data up to the origin. No shuffled K-fold, no peeking.
  * Direct multi-horizon gradient boosting: one global model with "horizon" as a feature.
    Lag features are always taken relative to the forecast ORIGIN, never the target day,
    so a 10-day-ahead forecast can't use yesterday's value.
  * Calendar + public holidays are legitimately known in advance and are allowed.
  * Intervals: per-horizon split-conformal residual quantiles from a 2016 calibration
    backtest (model trained to 2015), then checked on 2017.
  * MASE against weekly seasonal naive, so "good" has a meaning.
Run:  python projects/12_timeseries_forecasting/forecast_pipeline.py
"""
from __future__ import annotations

import pathlib
import sys
import time
import warnings

import holidays
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.seasonal import MSTL
from statsmodels.tsa.stattools import acf, pacf

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
from shared.report_io import dump  # noqa: E402

RAW = HERE.parents[1] / "data" / "raw" / "opsd_germany_daily.csv"
ART = HERE / "artifacts"
H = 14
SEED = 42
DE_HOLIDAYS = holidays.Germany(years=range(2005, 2019))
warnings.filterwarnings("ignore")


def load() -> pd.Series:
    df = pd.read_csv(RAW, parse_dates=["Date"]).set_index("Date")
    return df["Consumption"].asfreq("D")


# ------------------------------------------------------------------ features
def calendar(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Things known about a target day in advance."""
    doy = dates.dayofyear
    is_hol = np.array([d in DE_HOLIDAYS for d in dates.date])
    bridge = np.array([(d + pd.Timedelta(days=1)).date() in DE_HOLIDAYS or (d - pd.Timedelta(days=1)).date() in DE_HOLIDAYS for d in dates])
    return pd.DataFrame({
        "t_dow": dates.dayofweek, "t_month": dates.month,
        "t_doy_sin": np.sin(2 * np.pi * doy / 365.25), "t_doy_cos": np.cos(2 * np.pi * doy / 365.25),
        "t_holiday": is_hol.astype(int), "t_bridge": (bridge & ~is_hol).astype(int),
        "t_xmas": ((dates.month == 12) & (dates.day >= 22) | (dates.month == 1) & (dates.day <= 2)).astype(int),
    }, index=dates)


def build_rows(y: pd.Series, origins: list[pd.Timestamp]) -> pd.DataFrame:
    """One row per (origin, horizon). Every lag is read at a position <= the origin's position.

    Target-day information is limited to the calendar (known in advance). A 10-day-ahead row
    therefore sees the same recent history as a 1-day-ahead row from the same origin.
    """
    v = y.to_numpy(float)
    pos = {d: i for i, d in enumerate(y.index)}
    rows = []
    for o in origins:
        i = pos[o]
        last28 = v[i - 27:i + 1]
        base = {f"lag_{k}": v[i - k] for k in range(7)} | {
            "mean_7": last28[-7:].mean(), "mean_28": last28.mean(), "std_7": last28[-7:].std()}
        targets = pd.date_range(o + pd.Timedelta(days=1), periods=H)
        cal = calendar(targets).to_dict("records")
        for h, (t, c) in enumerate(zip(targets, cal), 1):
            back = (o.dayofweek - t.dayofweek) % 7  # days back to the latest same weekday <= origin
            same = [v[i - back - 7 * w] for w in range(4)]
            j = i + h - 364  # same weekday one year before the target, only if already observed
            rows.append({**base, "same_dow_mean_4w": float(np.mean(same)),
                         "year_ago_same_dow": v[j] if j <= i else np.nan, **c,
                         "horizon": h, "origin": o, "target": t, "y": v[i + h] if i + h < len(v) else np.nan})
    return pd.DataFrame(rows)


NON_FEATURES = ["origin", "target", "y", "resid", "Seasonal naive", "Holt-Winters", "GBM direct"]


def feats(df: pd.DataFrame) -> pd.DataFrame:
    """Model inputs = everything except identifiers, the label and stored predictions."""
    return df.drop(columns=NON_FEATURES, errors="ignore")


def gbm() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(max_iter=600, learning_rate=0.04, max_leaf_nodes=31,
                                         min_samples_leaf=20, l2_regularization=1.0, random_state=SEED)


# ------------------------------------------------------------------ baselines
def seasonal_naive(y: pd.Series, origin: pd.Timestamp) -> np.ndarray:
    last_week = y.loc[:origin].iloc[-7:].to_numpy()
    return np.tile(last_week, 2)[:H]


def holt_winters(y: pd.Series, origin: pd.Timestamp) -> np.ndarray:
    hist = y.loc[:origin].iloc[-3 * 365:]
    m = ExponentialSmoothing(hist, trend="add", damped_trend=True, seasonal="add", seasonal_periods=7,
                             initialization_method="estimated").fit()
    return np.asarray(m.forecast(H))


def metrics(err: np.ndarray, actual: np.ndarray, scale: float) -> dict:
    return {"mae": float(np.mean(np.abs(err))), "mape": float(np.mean(np.abs(err) / actual) * 100),
            "mase": float(np.mean(np.abs(err)) / scale), "bias": float(np.mean(err))}


# ------------------------------------------------------------------ run
def run() -> dict:
    t0 = time.time()
    ART.mkdir(exist_ok=True)
    y = load()
    train_end, cal_end = pd.Timestamp("2015-12-31"), pd.Timestamp("2016-12-31")
    first = pd.Timestamp("2007-01-07")  # need a year of history for lag_364

    # MASE scale: in-sample MAE of weekly seasonal naive on the training period
    tr = y.loc[:train_end]
    scale = float(np.mean(np.abs(tr.diff(7).dropna())))

    # 1) calibration: model trained to 2015, backtested on weekly 2016 origins -> conformal quantiles
    train_origins = list(pd.date_range(first, train_end - pd.Timedelta(days=H), freq="D"))
    D_tr = build_rows(y, train_origins)
    m_cal = gbm().fit(feats(D_tr), D_tr["y"])
    # daily origins: ~5k residuals, and horizon isn't tied to one weekday (as it would be with weekly origins)
    cal_origins = list(pd.date_range("2016-01-01", cal_end - pd.Timedelta(days=H), freq="D"))
    D_cal = build_rows(y, cal_origins)
    D_cal["resid"] = D_cal["y"] - m_cal.predict(feats(D_cal))
    q = {lvl: D_cal.groupby("horizon")["resid"].apply(lambda r: np.quantile(np.abs(r), lvl / 100)).to_dict()
         for lvl in (50, 80, 95)}

    # 2) final model trained on everything up to 2016 (origins whose targets end by 2016-12-31)
    full_origins = list(pd.date_range(first, cal_end - pd.Timedelta(days=H), freq="D"))
    D_full = build_rows(y, full_origins)
    model = gbm().fit(feats(D_full), D_full["y"])

    # 3) rolling-origin backtest on 2017: 51 weekly origins, every model sees only data <= origin
    test_origins = list(pd.date_range("2017-01-01", pd.Timestamp("2017-12-31") - pd.Timedelta(days=H), freq="7D"))
    D_te = build_rows(y, test_origins)
    D_te["GBM direct"] = model.predict(feats(D_te))
    sn, hw = [], []
    for o in test_origins:
        sn.extend(seasonal_naive(y, o))
        hw.extend(holt_winters(y, o))
    D_te["Seasonal naive"] = sn
    D_te["Holt-Winters"] = hw
    MODELS = ["Seasonal naive", "Holt-Winters", "GBM direct"]

    board, by_h = [], []
    for m in MODELS:
        board.append({"model": m, **metrics(D_te[m] - D_te["y"], D_te["y"], scale)})
        for h, g in D_te.groupby("horizon"):
            by_h.append({"model": m, "horizon": int(h), **metrics(g[m] - g["y"], g["y"], scale)})
    # holiday slice: where do models fail?
    hol = D_te[D_te["t_holiday"] == 1]
    holiday_slice = [{"model": m, **metrics(hol[m] - hol["y"], hol["y"], scale)} for m in MODELS]

    # conformal coverage on 2017
    coverage = {}
    for lvl, qh in q.items():
        width = D_te["horizon"].map(qh)
        inside = (D_te["y"] >= D_te["GBM direct"] - width) & (D_te["y"] <= D_te["GBM direct"] + width)
        coverage[str(lvl)] = {"coverage": float(inside.mean()), "mean_halfwidth": float(width.mean())}

    # explainability: permutation-free gain proxy via drop-column on a subsample would be slow;
    # use permutation importance on 2017 rows instead
    from sklearn.inspection import permutation_importance
    pi = permutation_importance(model, feats(D_te), D_te["y"], n_repeats=4, random_state=SEED, scoring="neg_mean_absolute_error")
    importance = sorted(({"feature": f, "importance": float(v)} for f, v in zip(feats(D_te).columns, pi.importances_mean)),
                        key=lambda d: -d["importance"])

    # EDA: decomposition, autocorrelation, calendar effects
    recent = y.loc["2012":"2016"]
    dec = MSTL(recent, periods=(7, 365), stl_kwargs={"seasonal_deg": 0}).fit()
    weekly_profile = y.groupby(y.index.dayofweek).mean()
    eda = {
        "dates": y.index.strftime("%Y-%m-%d").tolist(), "values": y.round(1).tolist(),
        "decomp": {"dates": recent.index.strftime("%Y-%m-%d").tolist(), "trend": dec.trend.round(1).tolist(),
                   "weekly": dec.seasonal["seasonal_7"].round(1).tolist(), "yearly": dec.seasonal["seasonal_365"].round(1).tolist(),
                   "resid": dec.resid.round(1).tolist()},
        "acf": acf(tr, nlags=40).tolist(), "pacf": pacf(tr, nlags=40).tolist(),
        "weekly_profile": weekly_profile.round(1).tolist(),
        "monthly_profile": y.groupby(y.index.month).mean().round(1).tolist(),
        "holiday_vs_normal": {"holiday": float(y[[d in DE_HOLIDAYS for d in y.index.date]].mean()),
                              "weekday": float(y[(y.index.dayofweek < 5) & ~np.array([d in DE_HOLIDAYS for d in y.index.date])].mean()),
                              "sunday": float(y[y.index.dayofweek == 6].mean())},
        "yearly_mean": y.groupby(y.index.year).mean().round(1).to_dict(),
    }

    sample_origins = [str(o.date()) for o in test_origins]
    report = {
        "split": {"train": "2006-01-01 → 2015-12-31", "calibration": "2016", "final_train": "2006 → 2016",
                  "backtest": "2017, 51 weekly origins × 14 days"},
        "mase_scale": scale, "leaderboard": board, "by_horizon": by_h, "holiday_slice": holiday_slice,
        "conformal": {"halfwidth_by_horizon": {k: {int(h): float(v) for h, v in d.items()} for k, d in q.items()},
                      "coverage_2017": coverage},
        "importance": importance[:15], "eda": eda, "test_origins": sample_origins,
        "n_rows": {"train": len(D_tr), "calibration": len(D_cal), "final_train": len(D_full), "backtest": len(D_te)},
        "runtime_sec": round(time.time() - t0, 1),
    }
    joblib.dump({"model": model, "q": q}, ART / "model.joblib")
    dump(report, ART / "report.json")
    return report


def forecast(y: pd.Series, origin: pd.Timestamp, model, q) -> dict:
    """Used by the API: all three models from an arbitrary origin, plus conformal bands."""
    rows = build_rows(y, [origin])
    pred = model.predict(feats(rows))
    out = {"targets": rows["target"].dt.strftime("%Y-%m-%d").tolist(),
           "actual": [None if np.isnan(v) else float(v) for v in rows["y"]],
           "GBM direct": pred.tolist(), "Seasonal naive": seasonal_naive(y, origin).tolist(),
           "Holt-Winters": holt_winters(y, origin).tolist(),
           "holiday": [bool(v) for v in rows["t_holiday"]],
           "bands": {lvl: [float(qh[h]) for h in range(1, H + 1)] for lvl, qh in q.items()}}
    return out


if __name__ == "__main__":
    r = run()
    for b in r["leaderboard"]:
        print(f"{b['model']:16s} MAE {b['mae']:6.1f} GWh  MAPE {b['mape']:.2f}%  MASE {b['mase']:.3f}  bias {b['bias']:+.1f}")
    print("holiday slice:", [(h["model"], round(h["mape"], 1)) for h in r["holiday_slice"]])
    print("coverage:", r["conformal"]["coverage_2017"])
    print("top features:", [i["feature"] for i in r["importance"][:6]], "runtime", r["runtime_sec"])
