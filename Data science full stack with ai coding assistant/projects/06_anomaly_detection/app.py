"""Project 06 API: benchmark report, per-series scores, and an anomaly-injection sandbox."""
from __future__ import annotations

import json
import pathlib

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import anomaly_pipeline as pipeline

HERE = pathlib.Path(__file__).parent
META = {
    "title": "Anomaly Detection",
    "tag": "Unsupervised · Streaming · CRISP-DM",
    "blurb": "Catch real machine and cloud failures in 5 Numenta Anomaly Benchmark series with causal detectors, label-free thresholds, and event-level scoring.",
    "accent": "#a64d5d", "accent_soft": "#f5e6e9",
}
router = APIRouter()
_state: dict = {}


def state() -> dict:
    if not _state:
        if not (HERE / "artifacts" / "series.json").exists():
            pipeline.run()
        _state["report"] = json.loads((HERE / "artifacts" / "report.json").read_text())
        _state["series"] = json.loads((HERE / "artifacts" / "series.json").read_text())
    return _state


class Injection(BaseModel):
    series: str
    kind: str = Field("spike", pattern="^(spike|level_shift|drift|flatline)$")
    position: float = Field(0.6, ge=0.2, le=0.95, description="fraction of the series where it starts")
    magnitude: float = Field(4.0, ge=0.5, le=15, description="size in probation standard deviations")
    quantile: float = Field(0.999, ge=0.9, le=1.0)


@router.get("/report")
def report():
    return state()["report"]


@router.get("/series/{name}")
def series(name: str):
    s = state()["series"]
    if name not in s:
        raise HTTPException(404, "unknown series")
    return s[name]


@router.post("/inject")
def inject(inj: Injection):
    if inj.series not in pipeline.SERIES:
        raise HTTPException(404, "unknown series")
    df, _ = pipeline.load(inj.series)
    v = df["value"].astype(float).copy()
    ppd = pipeline.points_per_day(df)
    n_prob = int(len(v) * pipeline.PROBATION)
    sd = float(v.iloc[:n_prob].std())
    start = int(len(v) * inj.position)
    length = {"spike": 2, "level_shift": ppd, "drift": ppd * 2, "flatline": ppd // 2}[inj.kind]
    end = min(len(v), start + length)
    if inj.kind == "spike":
        v.iloc[start:end] += inj.magnitude * sd
    elif inj.kind == "level_shift":
        v.iloc[start:end] += inj.magnitude * sd
    elif inj.kind == "drift":
        v.iloc[start:end] += np.linspace(0, inj.magnitude * sd, end - start)
    else:  # sensor stuck at its last value
        v.iloc[start:end] = v.iloc[start]
    scores = pipeline.score_series(v, ppd)
    out = {}
    for m in pipeline.METHODS:
        al = pipeline.alerts_from(scores[m], n_prob, inj.quantile, ppd // 2)
        hit = [int(i) for i in al if start <= i <= end + ppd // 2]
        out[m] = {"caught": bool(hit), "delay_points": (hit[0] - start) if hit else None, "alerts": al.tolist()}
    return {"values": v.round(3).tolist(), "start": start, "end": end, "methods": out,
            "points_per_day": ppd}
