"""Sidebar shortcuts: Early season, Peak and Latest jump the forecast to useful weeks."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from moshari import config as C
from moshari.model import ForecastBundle
from moshari.service import ForecastService

APP = str(Path(__file__).resolve().parents[1] / "app.py")
pytestmark = pytest.mark.skipif(not C.MODEL_PATH.exists(), reason="model not trained")


@pytest.fixture(scope="module")
def svc(raw):
    return ForecastService(raw, ForecastBundle.load())


def test_peak_is_the_heaviest_forecast_of_the_latest_season(svc):
    peak = svc.peak_issue_date(3)
    dates = pd.DatetimeIndex(svc.issue_dates)
    assert peak in set(dates) and peak.year == dates.max().year
    load = {d: svc.forecast_all(d, 3)["expected_cases"].sum() for d in dates[dates.year == dates.max().year]}
    assert load[peak] == pytest.approx(max(load.values()))


def test_peak_week_has_pressure_on_every_module(svc):
    from moshari import allocation as A

    fc = svc.forecast_all(svc.peak_issue_date(3), 3)
    alloc = A.allocate(fc, svc.wards, 0.7, 40)
    assert (fc["tier_idx"] >= 2).sum() > (svc.forecast_all(svc.default_issue_date(), 3)["tier_idx"] >= 2).sum()
    assert alloc["deficit_flag"].any()


def test_latest_is_the_newest_week(svc):
    assert svc.latest_issue_date() == max(svc.issue_dates)


def test_buttons_move_the_forecast_week():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    assert not at.exception
    early = at.session_state["issue_date"]
    at.button(key="jump_Peak").click().run()
    peak = pd.Timestamp(at.session_state["issue_date"])
    assert not at.exception and peak != pd.Timestamp(early)
    at.button(key="jump_Latest").click().run()
    assert pd.Timestamp(at.session_state["issue_date"]) > peak
    at.button(key="jump_Early").click().run()
    assert pd.Timestamp(at.session_state["issue_date"]) == pd.Timestamp(early)
