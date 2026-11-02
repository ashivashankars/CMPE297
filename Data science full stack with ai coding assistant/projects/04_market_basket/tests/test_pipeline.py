import json
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import basket_pipeline as pipeline


@pytest.fixture(scope="module")
def report():
    path = HERE / "artifacts" / "report.json"
    if not path.exists():
        pipeline.run()
    return json.loads(path.read_text())


def test_apriori_and_fpgrowth_agree(report):
    assert all(b["identical"] for b in report["benchmark"])


def test_all_rules_have_lift_above_one_in_training(report):
    assert all(r["lift"] > 1 for r in report["rules"])


def test_validated_rules_hold_out_of_sample(report):
    for r in report["rules"]:
        if r["holds_up"]:
            assert r["test_lift"] > 1 and r["q_value"] < 0.05


def test_champion_beats_random_and_popularity(report):
    board = {b["model"]: b for b in report["evaluation"]["leaderboard"]}
    champ = board["Item co-occurrence (tuned)"]
    assert champ["hit_rate@5"] > board["Most popular items"]["hit_rate@5"] > board["Random items"]["hit_rate@5"]
    assert champ["longtail_hit_rate@10"] > board["Most popular items"]["longtail_hit_rate@10"]


def test_recommender_never_suggests_items_in_cart():
    import joblib
    m = joblib.load(HERE / "artifacts" / "model.joblib")
    cart = {"whole milk", "yogurt", "butter"}
    for rec in (m["co"].recommend(cart, 10), m["recommender"].recommend(cart, 10)):
        assert not cart & {r["item"] for r in rec} and len(rec) == 10


def test_api_mine_and_recommend():
    from fastapi.testclient import TestClient
    sys.path.insert(0, str(HERE.parents[1]))
    from shared.hub import create_app
    c = TestClient(create_app())
    m = c.post("/p/04_market_basket/api/mine", json={"min_support": 0.01, "min_confidence": 0.3, "min_lift": 1.5}).json()
    assert m["n_rules"] > 0 and all(r["lift"] >= 1.5 for r in m["rules"])
    assert c.post("/p/04_market_basket/api/recommend", json={"items": ["not a food"]}).status_code == 422
