"""Project 12 API: backtest report + live 14-day forecasts from any origin date."""
from __future__ import annotations

import json
import pathlib

import joblib
import pandas as pd
from fastapi import APIRouter, HTTPException

import forecast_pipeline as pipeline

HERE = pathlib.Path(__file__).parent
META = {
    "title": "Electricity Demand Forecasting",
    "tag": "Time series · CRISP-DM",
    "blurb": "Forecast Germany's daily power consumption 1–14 days ahead, with a 51-origin rolling backtest over 2017, holiday-aware features, and calibrated fan charts.",
    "accent": "#b7791f", "accent_soft": "#f7eedb",
}
router = APIRouter()
_state: dict = {}


def state() -> dict:
    if not _state:
        if not (HERE / "artifacts" / "model.joblib").exists():
            pipeline.run()
        _state.update(joblib.load(HERE / "artifacts" / "model.joblib"))
        _state["y"] = pipeline.load()
        _state["report"] = json.loads((HERE / "artifacts" / "report.json").read_text())
    return _state


@router.get("/report")
def report():
    return state()["report"]


@router.get("/forecast")
def forecast(origin: str = "2017-12-17"):
    s = state()
    try:
        o = pd.Timestamp(origin)
    except ValueError:
        raise HTTPException(422, "bad date")
    if not pd.Timestamp("2016-01-01") <= o <= pd.Timestamp("2017-12-31"):
        raise HTTPException(422, "origin must be in 2016-2017 (model was trained on data to 2016; 2017 is out-of-sample)")
    out = pipeline.forecast(s["y"], o, s["model"], s["q"])
    hist = s["y"].loc[o - pd.Timedelta(days=55):o]
    out["history"] = {"dates": hist.index.strftime("%Y-%m-%d").tolist(), "values": hist.round(1).tolist()}
    out["in_sample"] = bool(o < pd.Timestamp("2017-01-01"))
    return out
