import json
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import forecast_pipeline as pipeline  # noqa: E402


@pytest.fixture(scope="module")
def report():
    path = HERE / "artifacts" / "report.json"
    if not path.exists():
        pipeline.run()
    return json.loads(path.read_text())


def test_rows_never_use_data_after_origin():
    """Corrupting everything after the origin must not change any feature."""
    y = pipeline.load()
    o = pd.Timestamp("2015-06-07")
    a = pipeline.feats(pipeline.build_rows(y, [o]))
    y2 = y.copy()
    y2.loc[o + pd.Timedelta(days=1):] = -1e6
    b = pipeline.feats(pipeline.build_rows(y2, [o]))
    pd.testing.assert_frame_equal(a, b)


def test_gbm_beats_seasonal_naive(report):
    board = {b["model"]: b for b in report["leaderboard"]}
    assert board["GBM direct"]["mase"] < 1 < board["Seasonal naive"]["mase"] + 0.2
    assert board["GBM direct"]["mae"] < board["Holt-Winters"]["mae"] < board["Seasonal naive"]["mae"]


def test_bands_are_nested_at_every_horizon(report):
    hw = report["conformal"]["halfwidth_by_horizon"]
    for h in range(1, 15):
        assert 0 < hw["50"][str(h)] < hw["80"][str(h)] < hw["95"][str(h)]


def test_coverage_reasonable(report):
    for lvl, c in report["conformal"]["coverage_2017"].items():
        assert abs(c["coverage"] - int(lvl) / 100) < 0.06


def test_forecast_api():
    from fastapi.testclient import TestClient
    sys.path.insert(0, str(HERE.parents[1]))
    from shared.hub import create_app
    c = TestClient(create_app())
    r = c.get("/p/12_timeseries_forecasting/api/forecast?origin=2017-12-17")
    assert r.status_code == 200 and len(r.json()["GBM direct"]) == 14
    assert c.get("/p/12_timeseries_forecasting/api/forecast?origin=2014-01-01").status_code == 422
