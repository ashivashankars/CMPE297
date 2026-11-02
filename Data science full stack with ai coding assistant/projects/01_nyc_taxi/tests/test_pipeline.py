"""Guardrail tests: leakage, split integrity, calibration, and API contract."""
import json
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import taxi_pipeline as pipeline


@pytest.fixture(scope="module")
def report():
    path = HERE / "artifacts" / "report.json"
    if not path.exists():
        pipeline.run()
    return json.loads(path.read_text())


def test_no_post_trip_fields_in_features():
    assert not set(pipeline.LEAKY) & set(pipeline.FEATURES)
    assert "dropoff" not in pipeline.FEATURES and "duration_min" not in pipeline.FEATURES


def test_split_is_strictly_chronological():
    df = pipeline.featurize(pipeline.clean(pipeline.load())[0])
    parts = pipeline.temporal_split(df)
    order = ["fit", "tune", "calibrate", "test"]
    for a, b in zip(order, order[1:]):
        assert parts[a]["pickup"].max() < parts[b]["pickup"].min()
    assert sum(len(p) for p in parts.values()) == len(df)


def test_champion_beats_baselines(report):
    board = {m["model"]: m for m in report["leaderboard"]}
    champ = next(m for m in report["leaderboard"] if m.get("champion"))
    assert champ["mae_min"] < min(m["mae_min"] for k, m in board.items() if "median" in k.lower() or "speed" in k)


def test_conformal_coverage_close_to_target(report):
    for level, d in report["intervals"].items():
        assert abs(d["coverage"] - int(level) / 100) < 0.05, (level, d)


def test_leak_demo_is_suspiciously_good(report):
    champ = next(m for m in report["leaderboard"] if m.get("champion"))
    assert report["leak_demo"]["mae_min"] < champ["mae_min"]


def test_predict_endpoint():
    from fastapi.testclient import TestClient
    sys.path.insert(0, str(HERE.parents[1]))
    from shared.hub import create_app
    client = TestClient(create_app())
    r = client.post("/p/01_nyc_taxi/api/predict", json={"pickup_zone": "Midtown Center", "dropoff_zone": "JFK Airport", "hour": 17, "dow": 4})
    assert r.status_code == 200
    body = r.json()
    lo, hi = body["interval"]["90"]
    assert lo < body["minutes"] < hi and len(body["by_hour"]["minutes"]) == 24
    assert client.post("/p/01_nyc_taxi/api/predict", json={"pickup_zone": "Atlantis", "dropoff_zone": "JFK Airport", "hour": 1, "dow": 1}).status_code == 422
