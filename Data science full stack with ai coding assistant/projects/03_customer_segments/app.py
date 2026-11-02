"""Project 03 API: segmentation report + assign a new customer to a segment."""
from __future__ import annotations

import json
import pathlib

import joblib
import numpy as np
import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel, Field

import segments_pipeline as pipeline

HERE = pathlib.Path(__file__).parent
META = {
    "title": "Customer Segmentation",
    "tag": "Clustering · CRISP-DM",
    "blurb": "Find shopper segments in the Kaggle Mall Customers data, prove the segments are stable and generalize, and turn each into a marketing action.",
    "accent": "#5b6fa8", "accent_soft": "#e7ebf5",
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


class Customer(BaseModel):
    age: int = Field(ge=15, le=90)
    income: float = Field(ge=0, le=200, description="annual income, k$")
    score: float = Field(ge=1, le=100, description="spending score")
    is_male: int = Field(0, ge=0, le=1)


@router.get("/report")
def report():
    return state()["report"]


@router.post("/assign")
def assign(c: Customer):
    s = state()
    row = pd.DataFrame([c.model_dump()])[s["cols"]]
    x = s["scaler"].transform(row)
    raw = int(s["kmeans"].predict(x)[0])
    cluster = s["remap"][raw]
    dists = np.linalg.norm(s["kmeans"].cluster_centers_ - x, axis=1)
    # GMM soft membership, mapped to k-means ids by nearest component mean
    probs = s["gmm"].predict_proba(x)[0]
    comp_to_km = [int(np.argmin(np.linalg.norm(s["kmeans"].cluster_centers_ - m, axis=1))) for m in s["gmm"].means_]
    soft = np.zeros(len(dists))
    for comp, p in enumerate(probs):
        soft[s["remap"][comp_to_km[comp]]] += p
    profile = next(p for p in s["profiles"] if p["cluster"] == cluster)
    return {
        "cluster": cluster, "persona": profile["persona"], "action": profile["action"],
        "distance_to_centroids": {s["remap"][i]: float(d) for i, d in enumerate(dists)},
        "soft_membership": soft.round(4).tolist(),
        "confidence": "clear member" if sorted(dists)[1] - sorted(dists)[0] > 0.5 else "borderline: close to two segments",
        "features_used": s["cols"],
    }
