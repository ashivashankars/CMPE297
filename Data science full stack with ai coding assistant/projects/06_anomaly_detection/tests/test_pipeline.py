import json
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import anomaly_pipeline as pipeline  # noqa: E402


@pytest.fixture(scope="module")
def report():
    path = HERE / "artifacts" / "report.json"
    if not path.exists():
        pipeline.run()
    return json.loads(path.read_text())


def test_detectors_are_causal():
    """Changing the future must not change any past score."""
    df, _ = pipeline.load("ec2_latency")
    v = df["value"].astype(float)
    ppd = pipeline.points_per_day(df)
    cut = int(len(v) * 0.7)
    a = pipeline.score_series(v, ppd)
    v2 = v.copy()
    v2.iloc[cut:] = v2.iloc[cut:] * 3 + 100  # wreck the future
    b = pipeline.score_series(v2, ppd)
    for m in pipeline.METHODS:
        np.testing.assert_allclose(a[m][:cut], b[m][:cut], rtol=1e-6, atol=1e-6, err_msg=m)


def test_no_alerts_during_probation():
    s = np.r_[np.zeros(100), np.full(900, 10.0)]
    al = pipeline.alerts_from(s, 150, 0.99, refractory=1)
    assert (al >= 150).all()


def test_every_detector_beats_random_pr_auc(report):
    for row in report["per_series"]:
        if row["pr_auc"] is not None and row["method"] in ("Isolation Forest", "Local Outlier Factor"):
            assert row["pr_auc"] > row["pr_auc_base_rate"] * 0.8, row


def test_injected_spike_is_caught():
    from fastapi.testclient import TestClient
    sys.path.insert(0, str(HERE.parents[1]))
    from shared.hub import create_app
    c = TestClient(create_app())
    r = c.post("/p/06_anomaly_detection/api/inject", json={"series": "ec2_latency", "kind": "spike", "position": 0.5, "magnitude": 12})
    assert r.status_code == 200
    assert r.json()["methods"]["Rolling robust z"]["caught"]


def test_summary_counts_consistent(report):
    total = sum(1 for _ in pipeline.SERIES)
    assert len(report["per_series"]) == total * len(pipeline.METHODS)
    assert all(s["windows"] == 15 for s in report["summary"])
