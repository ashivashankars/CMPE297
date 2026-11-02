import json
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import segments_pipeline as pipeline


@pytest.fixture(scope="module")
def report():
    path = HERE / "artifacts" / "report.json"
    if not path.exists():
        pipeline.run()
    return json.loads(path.read_text())


def test_chosen_segmentation_is_stable_and_separated(report):
    assert report["chosen"]["silhouette"] > 0.45
    assert report["chosen"]["stability"] > 0.85


def test_segments_generalize_to_holdout(report):
    h = report["holdout"]
    assert h["holdout_silhouette"] > h["train_silhouette"] - 0.1
    assert h["holdout_ari_vs_full_fit"] > 0.8


def test_algorithms_agree(report):
    assert min(a["ari"] for a in report["algo_agreement"]) > 0.8


def test_every_customer_assigned_and_profiles_cover_all(report):
    assert len(report["points"]) == report["n_customers"] == 200
    assert sum(p["size"] for p in report["profiles"]) == 200


def test_assign_endpoint():
    from fastapi.testclient import TestClient
    sys.path.insert(0, str(HERE.parents[1]))
    from shared.hub import create_app
    c = TestClient(create_app())
    r = c.post("/p/03_customer_segments/api/assign", json={"age": 30, "income": 95, "score": 88})
    assert r.status_code == 200
    body = r.json()
    assert "High-income" in body["persona"] and abs(sum(body["soft_membership"]) - 1) < 1e-3
