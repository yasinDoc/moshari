"""Vector-control simulator (module 3): model-driven, monotone, ROI-ranked."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from moshari import config as C
from moshari import simulation as S
from moshari.model import SIM_KIND, ForecastBundle
from moshari.service import ForecastService

pytestmark = pytest.mark.skipif(not C.MODEL_PATH.exists(), reason="model not trained")
PEAK = pd.Timestamp("2025-06-02")
DRY = pd.Timestamp("2025-11-17")


@pytest.fixture(scope="module")
def svc(raw):
    return ForecastService(raw, ForecastBundle.load())


@pytest.fixture(scope="module")
def table(svc):
    return S.build_effect_table(svc, PEAK)


def test_crew_effect_has_diminishing_returns_and_a_cap():
    e = S.crew_effect(np.arange(0, 12), per_crew=0.2, cap=0.75)
    assert e[0] == 0 and np.all(np.diff(e) >= 0)
    assert np.all(np.diff(e[:6]) > np.diff(e)[1:6].min() - 1e-12)  # gains shrink
    assert e.max() <= 0.75


def test_simulation_models_exist_for_every_horizon(svc):
    assert all((h, SIM_KIND) in svc.bundle.boosters for h in svc.bundle.horizons)


def test_more_crews_never_increase_cases(table):
    assert (np.diff(table.cases, axis=1) <= 1e-9).all()


def test_zero_crews_reproduce_the_main_forecast(svc, table):
    fc = svc.forecast_all(PEAK, 3).set_index(C.WARD_COL)["expected_cases"]
    j = table.horizons.index(3)
    base = pd.Series(table.cases[:, 0, j], index=table.wards[C.WARD_COL])
    assert np.allclose(base.loc[fc.index], fc, rtol=1e-6)


def test_crews_prevent_cases_in_peak_season(table):
    plan = S.recommend(table, 30)
    _, by_h = S.simulate(table, plan)
    assert sum(plan.values()) == 30
    assert by_h["cases_prevented"].sum() > 50
    assert (by_h["beds_freed"] >= 0).all() and (by_h["saline_saved"] >= 0).all()


def test_crews_are_held_back_in_dry_season(svc):
    plan = S.recommend(S.build_effect_table(svc, DRY), 30)
    assert sum(plan.values()) == 0


def test_greedy_plan_beats_one_crew_per_worst_ward(table):
    greedy = S.recommend(table, 30)
    naive = {w: 1 for w in table.wards.sort_values("baseline_h3", ascending=False)[C.WARD_COL].head(30)}
    _, g = S.simulate(table, greedy)
    _, n = S.simulate(table, naive)
    assert g["cases_prevented"].sum() >= n["cases_prevented"].sum()


def test_plan_respects_limits(table):
    plan = S.recommend(table, 100, max_per_ward=3)
    assert max(plan.values()) <= 3 and sum(plan.values()) <= 100


def test_roi_is_cases_prevented_per_crew(table):
    plan = S.recommend(table, 20)
    w, _ = S.simulate(table, plan)
    used = w[w["crews"] > 0]
    assert np.allclose(used["roi"], used["cases_prevented"] / used["crews"])
