from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from moshari import config as C
from moshari.model import ForecastBundle, conformal_offset
from moshari.risk import assign_tier
from moshari.service import ForecastService, Scenario

pytestmark = pytest.mark.skipif(not C.MODEL_PATH.exists(), reason="model not trained")


@pytest.fixture(scope="module")
def svc(raw):
    return ForecastService(raw, ForecastBundle.load())


def test_bundle_has_all_horizons(svc):
    assert svc.bundle.horizons == list(C.HORIZONS)


def test_forecast_all_covers_every_ward_with_ordered_interval(svc):
    fc = svc.forecast_all(svc.default_issue_date(), 3)
    assert len(fc) == 60
    assert (fc["lower_80"] <= fc["expected_cases"]).all()
    assert (fc["expected_cases"] <= fc["upper_80"]).all()
    assert set(fc["tier"]) <= set(C.TIER_NAMES)


def test_explanations_add_up_to_the_prediction(svc):
    d = svc.default_issue_date()
    row = svc.ward_row("DNCC_Ward_01", d)
    contrib = svc.bundle.explain(row, 3).iloc[0]
    pred = svc.bundle.predict(row, 3)["expected_cases"].iloc[0]
    assert np.isclose(np.exp(contrib.sum()), pred, rtol=1e-4)


def test_more_rain_raises_risk(svc):
    d = svc.default_issue_date()
    base = svc.ward_outlook("DSCC_Ward_05", d)["expected_cases"].sum()
    wet = svc.ward_outlook("DSCC_Ward_05", d, Scenario(rain_factor=2.5))["expected_cases"].sum()
    assert wet > base


def test_tiers_are_monotonic():
    t = assign_tier([0, 1.9, 2, 6.9, 7, 13, 50], [2.0, 7.0, 13.0])
    assert list(t) == [0, 0, 1, 1, 2, 3, 3]


def test_conformal_offset_hits_target_coverage():
    rng = np.random.default_rng(0)
    y = rng.normal(size=5000)
    off = conformal_offset(y, np.full_like(y, -0.5), np.full_like(y, 0.5), coverage=0.8)
    cover = ((y >= -0.5 - off) & (y <= 0.5 + off)).mean()
    assert 0.79 <= cover <= 0.82
