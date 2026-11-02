"""Project 04 API: rule report, live re-mining with custom thresholds, and cart recommendations."""
from __future__ import annotations

import json
import pathlib
import time

import joblib
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import basket_pipeline as pipeline

HERE = pathlib.Path(__file__).parent
META = {
    "title": "Market Basket Mining",
    "tag": "Association rules · CRISP-DM",
    "blurb": "Mine 9,835 real grocery baskets with Apriori and FP-Growth, test every rule on held-out baskets, and benchmark rule-based recommendations against honest baselines.",
    "accent": "#3f8f8a", "accent_soft": "#e2f0ee",
}
router = APIRouter()
_state: dict = {}


def state() -> dict:
    if not _state:
        if not (HERE / "artifacts" / "model.joblib").exists():
            pipeline.run()
        s = joblib.load(HERE / "artifacts" / "model.joblib")
        s["oh_df"] = pd.DataFrame(s.pop("oh_train"), columns=s["columns"])
        s["report"] = json.loads((HERE / "artifacts" / "report.json").read_text())
        _state.update(s)
    return _state


class Cart(BaseModel):
    items: list[str] = Field(default_factory=list, max_length=30)


class MineParams(BaseModel):
    min_support: float = Field(0.01, ge=0.002, le=0.2)
    min_confidence: float = Field(0.2, ge=0.01, le=1.0)
    min_lift: float = Field(1.0, ge=0.0, le=20)
    algorithm: str = "fpgrowth"


@router.get("/report")
def report():
    return state()["report"]


@router.get("/items")
def items():
    s = state()
    return {"items": s["items"], "popular": s["popularity"][:24]}


@router.post("/recommend")
def recommend(c: Cart):
    s = state()
    unknown = [i for i in c.items if i not in s["items"]]
    if unknown:
        raise HTTPException(422, f"unknown items: {unknown}")
    cart = set(c.items)
    return {"co_occurrence": s["co"].recommend(cart, 8), "rules": s["recommender"].recommend(cart, 8)}


@router.post("/mine")
def mine(p: MineParams):
    s = state()
    algo = {"fpgrowth": pipeline.fpgrowth, "apriori": pipeline.apriori}.get(p.algorithm)
    if algo is None:
        raise HTTPException(422, "algorithm must be fpgrowth or apriori")
    t = time.perf_counter()
    rules = pipeline.mine(s["oh_df"], p.min_support, p.min_confidence, algo)
    elapsed = time.perf_counter() - t
    if len(rules):
        rules = rules[rules["lift"] >= p.min_lift].sort_values("lift", ascending=False)
    top = [{"antecedents": sorted(r.antecedents), "consequents": sorted(r.consequents), "support": float(r.support),
            "confidence": float(r.confidence), "lift": float(r.lift)} for r in rules.head(40).itertuples()] if len(rules) else []
    return {"n_rules": int(len(rules)), "seconds": elapsed, "rules": top}
