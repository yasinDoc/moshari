"""Core rules of the constrained resource allocation engine (module 1)."""

from __future__ import annotations

import pandas as pd
import pytest

from moshari import allocation as A
from moshari import config as C
from moshari.model import ForecastBundle
from moshari.service import ForecastService

pytestmark = pytest.mark.skipif(not C.MODEL_PATH.exists(), reason="model not trained")


@pytest.fixture(scope="module")
def svc(raw):
    return ForecastService(raw, ForecastBundle.load())


@pytest.fixture(scope="module")
def fc(svc):
    return svc.forecast_all(svc.default_issue_date(), 3)


def test_ratios_are_fitted_from_onsite_data():
    r = A.demand_ratios()
    assert r.source == "fitted from onsite data"
    assert 2.3 < r.ratios["saline_bags_needed"] < 2.5
    assert 1.1 < r.ratios["diagnostic_kits_needed"] < 1.25
    assert 0.25 < r.ratios["hospital_beds_required"] < 0.35
    assert min(r.r2.values()) > 0.95


def test_full_stock_has_no_supply_deficits(svc, fc):
    a = A.allocate(fc, svc.wards, stock_pct=1.0, total_crews=200)
    assert not a["deficit_flag"].any()
    for need, got, _ in A.RESOURCES:
        assert (a[got] == a[need]).all()


@pytest.mark.parametrize("pct", [0.3, 0.55, 0.8])
def test_allocation_never_exceeds_stock_or_demand(svc, fc, pct):
    a = A.allocate(fc, svc.wards, stock_pct=pct, total_crews=40)
    for need, got, _ in A.RESOURCES:
        assert a[got].sum() <= pct * a[need].sum() + 1e-9
        assert (a[got] <= a[need]).all() and (a[got] >= 0).all()


def test_scarcity_serves_highest_priority_first(svc, fc):
    a = A.allocate(fc, svc.wards, stock_pct=0.3, total_crews=40)
    served = a["saline_bags_allocated"] >= a["saline_bags_needed"]
    # once a ward goes short, no lower-priority ward is fully served (except zero-demand wards)
    first_short = served.idxmin() if (~served).any() else len(a)
    later = a.iloc[first_short + 1:]
    assert not ((later["saline_bags_allocated"] > 0) & (later["saline_bags_needed"] > 0)).any()
    assert a["priority_score"].is_monotonic_decreasing


def test_priority_rewards_risk_and_density():
    base = pd.DataFrame({"tier_idx": [2, 2, 1], "p_high": [0.8, 0.8, 0.8],
                         "population_density_sqkm": [70000, 20000, 70000]})
    s = A.priority_scores(base)
    assert s[0] > s[1]          # same risk, denser ward ranks higher
    assert s[0] > s[2]          # same density, higher tier ranks higher


def test_crews_add_up_and_go_to_high_risk_wards(svc, fc):
    a = A.allocate(fc, svc.wards, stock_pct=1.0, total_crews=25)
    assert a["crews_assigned"].sum() <= 25
    assert (a.loc[a["tier_idx"] < A.CREW_MIN_TIER, "crews_assigned"] == 0).all()
    assert (a["crews_assigned"] <= a["crews_needed"]).all()


def test_deficit_notes_state_exact_shortfall(svc, fc):
    a = A.allocate(fc, svc.wards, stock_pct=0.4, total_crews=40)
    short = a[a["deficit_flag"]].iloc[0]
    gap = int(short["saline_bags_needed"] - short["saline_bags_allocated"])
    assert f"{gap} saline bag" in short["deficit_note"]


def test_rejects_invalid_stock():
    with pytest.raises(ValueError):
        A.allocate(pd.DataFrame(), pd.DataFrame(), stock_pct=1.5)
