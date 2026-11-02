"""Project 01 API: serves the training report and live trip-duration estimates."""
from __future__ import annotations

import json
import pathlib

import joblib
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import taxi_pipeline as pipeline

HERE = pathlib.Path(__file__).parent
META = {
    "title": "NYC Taxi Trip Duration",
    "tag": "Regression · CRISP-DM",
    "blurb": "Predict ride time at booking from 6,433 real NYC TLC trips, with honest temporal validation, a leakage trap, and conformal 90% ranges.",
    "accent": "#c0703a", "accent_soft": "#f6e9df",
}
router = APIRouter()
_state: dict = {}


def state() -> dict:
    if not _state:
        if not (HERE / "artifacts" / "model.joblib").exists():
            pipeline.run()
        _state.update(joblib.load(HERE / "artifacts" / "model.joblib"))
        _state["report"] = json.loads((HERE / "artifacts" / "report.json").read_text())
    return _state


class Trip(BaseModel):
    pickup_zone: str
    dropoff_zone: str
    hour: int = Field(ge=0, le=23)
    dow: int = Field(ge=0, le=6)
    passengers: int = Field(1, ge=0, le=6)
    color: str = "yellow"
    distance: float | None = Field(None, gt=0, le=60)


def _frame(t: Trip, distance: float, hours=None) -> pd.DataFrame:
    s = state()
    hours = [t.hour] if hours is None else hours
    rows = pd.DataFrame({
        "pickup": [pd.Timestamp("2019-03-04") + pd.Timedelta(days=t.dow, hours=h) for h in hours],
        "pickup_zone": t.pickup_zone, "dropoff_zone": t.dropoff_zone,
        "pickup_borough": s["zones"].get(t.pickup_zone, "Unknown"),
        "dropoff_borough": s["zones"].get(t.dropoff_zone, "Unknown"),
        "color": t.color, "passengers": t.passengers, "distance": distance,
    })
    return pipeline.featurize(rows)[pipeline.FEATURES]


@router.get("/report")
def report():
    return state()["report"]


@router.get("/options")
def options():
    s = state()
    return {"zones": sorted(s["zones"].items()), "median_distance": s["median_distance"]}


@router.post("/predict")
def predict(t: Trip):
    s = state()
    if t.pickup_zone not in s["zones"] or t.dropoff_zone not in s["zones"]:
        raise HTTPException(422, "unknown zone")
    key = f"{t.pickup_zone}|||{t.dropoff_zone}"
    distance_source = "you entered it"
    distance = t.distance
    if distance is None:
        distance = s["pair_distance"].get(key)
        distance_source = "median of past trips on this route" if distance else "city-wide median (route never seen)"
        distance = distance or s["median_distance"]
    log_pred = float(s["model"].predict(_frame(t, distance))[0])
    curve = np.expm1(s["model"].predict(_frame(t, distance, hours=list(range(24)))))
    q90 = s["q"]["90"]
    return {
        "minutes": float(np.expm1(log_pred)),
        "interval": {lvl: [float(np.expm1(log_pred - q)), float(np.expm1(log_pred + q))] for lvl, q in s["q"].items()},
        "distance": distance, "distance_source": distance_source,
        "pickup_borough": s["zones"][t.pickup_zone], "dropoff_borough": s["zones"][t.dropoff_zone],
        "by_hour": {"minutes": curve.round(2).tolist(),
                    "lo": np.expm1(np.log1p(curve) - q90).round(2).tolist(),
                    "hi": np.expm1(np.log1p(curve) + q90).round(2).tolist()},
    }
