"""S2: allocation guarantees, checked on many randomised weeks plus the real forecast.

`test_allocation_engine.py` checks the engine on one real week. These tests add
the guarantees from TASKS.md as *properties*: they must hold for every stock
level, crew count and demand pattern, so each one runs on a few hundred seeded
random cases (fast: no model needed) and once more on the real model's output.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from moshari import allocation as A
from moshari import config as C

STOCK_LEVELS = (0.3, 0.45, 0.6, 0.75, 0.9, 1.0)
SEEDS = range(40)


# --------------------------------------------------------------------------- synthetic weeks
def fake_week(seed: int, n: int = 24) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A forecast-shaped table and ward profiles, like ForecastService.forecast_all gives."""
    rng = np.random.default_rng(seed)
    wards = [f"W{seed:02d}_Ward_{i:02d}" for i in range(1, n + 1)]
    expected = rng.gamma(1.5, 4.0, n) * rng.choice([0, 1], n, p=[0.15, 0.85])  # some quiet wards
    tier = np.digitize(expected, [3, 7, 12])
    fc = pd.DataFrame({
        C.WARD_COL: wards,
        C.CITY_COL: rng.choice(["Alpha", "Beta", "Gamma"], n),
        "expected_cases": expected,
        "upper_80": expected * rng.uniform(1.1, 1.8, n),
        "tier_idx": tier,
        "p_high": np.clip(expected / 15 + rng.normal(0, 0.05, n), 0, 1),
    })
    profiles = pd.DataFrame({"population_density_sqkm": rng.integers(5_000, 90_000, n)}, index=wards)
    return fc, profiles


def cases():
    for seed in SEEDS:
        for pct in STOCK_LEVELS:
            yield seed, pct


@pytest.fixture(scope="module")
def ratios():
    return A.demand_ratios()


# --------------------------------------------------------------------------- the four S2 rules
@pytest.mark.parametrize("seed,pct", list(cases()))
def test_allocated_never_exceeds_stock_and_uses_all_of_it(seed, pct, ratios):
    fc, wards = fake_week(seed)
    a = A.allocate(fc, wards, stock_pct=pct, total_crews=20, ratios=ratios)
    for need, got, _ in A.RESOURCES:
        stock = int(np.floor(pct * a[need].sum() + 1e-9))
        assert a[got].sum() <= stock, f"{got} over stock"
        assert a[got].sum() == stock, f"{got} left stock unused while wards were short"
        assert ((a[got] >= 0) & (a[got] <= a[need])).all()


@pytest.mark.parametrize("seed", SEEDS)
def test_full_stock_means_no_supply_deficit(seed, ratios):
    fc, wards = fake_week(seed)
    a = A.allocate(fc, wards, stock_pct=1.0, total_crews=0, ratios=ratios)
    assert not a["deficit_flag"].any()
    assert (a["fill_rate"] == 1.0).all()


@pytest.mark.parametrize("seed", SEEDS)
def test_scarce_stock_serves_priority_order(seed, ratios):
    """At 30%, wards are served strictly down the priority list: a run of fully served
    wards, at most one partly served ward, then nothing."""
    fc, wards = fake_week(seed)
    a = A.allocate(fc, wards, stock_pct=0.3, total_crews=0, ratios=ratios)
    assert list(a["priority_rank"]) == list(range(1, len(a) + 1))
    assert a["priority_score"].is_monotonic_decreasing
    for need, got, _ in A.RESOURCES:
        sub = a[a[need] > 0]
        state = np.where(sub[got] == sub[need], 2, np.where(sub[got] > 0, 1, 0))
        assert (np.diff(state) <= 0).all(), f"{got}: a lower-priority ward was served before a higher one"
        assert (state == 1).sum() <= 1


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("crews", [0, 1, 3, 10, 200])
def test_crews_add_up_to_the_total(seed, crews, ratios):
    fc, wards = fake_week(seed)
    a = A.allocate(fc, wards, stock_pct=1.0, total_crews=crews, ratios=ratios)
    need = int(a["crews_needed"].sum())
    assert a["crews_assigned"].sum() == min(crews, need)
    assert (a["crews_assigned"] <= a["crews_needed"]).all()
    assert (a.loc[a["tier_idx"] < A.CREW_MIN_TIER, "crews_assigned"] == 0).all()
    assert (a["crew_shortfall"] == a["crews_needed"] - a["crews_assigned"]).all()


# --------------------------------------------------------------------------- the details behind them
@pytest.mark.parametrize("seed", SEEDS)
def test_every_high_ward_gets_one_crew_before_any_gets_two(seed, ratios):
    fc, wards = fake_week(seed)
    a = A.allocate(fc, wards, stock_pct=1.0, total_crews=5, ratios=ratios)
    eligible = a[a["crews_needed"] > 0]
    if (eligible["crews_assigned"] > 1).any():
        assert (eligible["crews_assigned"] >= 1).all()
    got_one = eligible["crews_assigned"].to_numpy() > 0
    assert (np.diff(got_one.astype(int)) <= 0).all(), "a crew skipped a higher-priority ward"


@pytest.mark.parametrize("seed", SEEDS[:10])
def test_demand_never_understated(seed, ratios):
    fc, wards = fake_week(seed)
    a = A.allocate(fc, wards, ratios=ratios)
    for need, _, _ in A.RESOURCES:
        assert (a[need] >= a["planned_cases"] * ratios.ratios[need] - 1e-9).all()
        assert (a[need] < a["planned_cases"] * ratios.ratios[need] + 1).all()   # rounded up by < 1


@pytest.mark.parametrize("seed", SEEDS[:10])
def test_planning_for_upper_range_never_needs_less(seed, ratios):
    fc, wards = fake_week(seed)
    exp = A.allocate(fc, wards, ratios=ratios).set_index(C.WARD_COL)
    up = A.allocate(fc, wards, plan_for="upper", ratios=ratios).set_index(C.WARD_COL).loc[exp.index]
    for need, _, _ in A.RESOURCES:
        assert (up[need] >= exp[need]).all()


@pytest.mark.parametrize("seed", SEEDS[:10])
def test_result_does_not_depend_on_row_order_and_leaves_input_alone(seed, ratios):
    fc, wards = fake_week(seed)
    before = fc.copy()
    a = A.allocate(fc, wards, stock_pct=0.5, total_crews=7, ratios=ratios)
    b = A.allocate(fc.sample(frac=1, random_state=seed), wards, stock_pct=0.5, total_crews=7, ratios=ratios)
    pd.testing.assert_frame_equal(fc, before)
    cols = [C.WARD_COL, "priority_rank", "crews_assigned", *[g for _, g, _ in A.RESOURCES]]
    pd.testing.assert_frame_equal(a[cols], b[cols])


def test_quiet_week_needs_nothing(ratios):
    fc, wards = fake_week(0)
    fc = fc.assign(expected_cases=0.0, upper_80=0.0, tier_idx=0, p_high=0.0)
    a = A.allocate(fc, wards, stock_pct=0.3, total_crews=10, ratios=ratios)
    assert not a["deficit_flag"].any()
    assert a["crews_assigned"].sum() == 0
    assert (a["deficit_note"] == "Fully supplied").all()


def test_summary_matches_the_table(ratios):
    fc, wards = fake_week(3)
    a = A.allocate(fc, wards, stock_pct=0.5, total_crews=4, ratios=ratios)
    s = A.summarize(a, 4)
    for need, got, label in A.RESOURCES:
        r = s["resources"][label]
        assert r["needed"] == a[need].sum() and r["allocated"] == a[got].sum()
        assert r["short"] == r["needed"] - r["allocated"]
    assert s["deficit_wards"] == a["deficit_flag"].sum()
    assert s["crews"]["assigned"] == a["crews_assigned"].sum() <= 4


@pytest.mark.parametrize("pct", [0.0, -0.1, 1.01])
def test_rejects_stock_outside_0_to_100_percent(pct):
    fc, wards = fake_week(0)
    with pytest.raises(ValueError, match="stock_pct"):
        A.allocate(fc, wards, stock_pct=pct)


# --------------------------------------------------------------------------- the real model
@pytest.fixture(scope="module")
def real_service(raw):
    from moshari.model import ForecastBundle
    from moshari.service import ForecastService

    if not C.MODEL_PATH.exists():
        pytest.skip("model not trained")
    return ForecastService(raw, ForecastBundle.load())


@pytest.mark.parametrize("horizon", [2, 3, 4])
def test_rules_hold_on_the_real_forecast(real_service, horizon):
    svc = real_service
    fc = svc.forecast_all(svc.default_issue_date(), horizon)
    for pct in (0.3, 1.0):
        a = A.allocate(fc, svc.wards, stock_pct=pct, total_crews=40)
        assert len(a) == 60 and a[C.WARD_COL].is_unique
        for need, got, _ in A.RESOURCES:
            assert a[got].sum() == int(np.floor(pct * a[need].sum() + 1e-9))
        assert a["crews_assigned"].sum() == min(40, int(a["crews_needed"].sum()))
        if pct == 1.0:
            assert not a["deficit_flag"].any()


# --------------------------------------------------------------------------- tie-break (the bug S2 found)
def _tied_week(order: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Six wards with identical risk, density and cases, plus one clearly higher-risk ward."""
    ids = [f"DNCC_Ward_{i:02d}" for i in order]
    fc = pd.DataFrame({
        C.WARD_COL: ids,
        C.CITY_COL: "Alpha",
        "expected_cases": [20.0 if i == 9 else 8.0 for i in order],
        "upper_80": [30.0 if i == 9 else 12.0 for i in order],
        "tier_idx": [3 if i == 9 else 2 for i in order],
        "p_high": [0.9 if i == 9 else 0.5 for i in order],
    })
    profiles = pd.DataFrame({"population_density_sqkm": 40_000}, index=ids)
    return fc, profiles


@pytest.mark.parametrize("order", [[1, 2, 3, 4, 5, 6, 9], [6, 5, 4, 3, 2, 1, 9], [9, 4, 1, 6, 3, 5, 2]])
def test_tied_wards_are_ranked_by_ward_id_whatever_the_row_order(order, ratios):
    """Equal score and equal cases: ward id decides, so the plan never depends on row order."""
    fc, wards = _tied_week(order)
    a = A.allocate(fc, wards, stock_pct=0.5, total_crews=3, ratios=ratios)
    tied = a[a[C.WARD_COL] != "DNCC_Ward_09"]
    assert a[C.WARD_COL].iloc[0] == "DNCC_Ward_09"                      # a real priority still wins
    assert list(tied[C.WARD_COL]) == sorted(tied[C.WARD_COL])           # ties go by ward id
    assert list(tied["priority_rank"]) == list(range(2, 8))
    # Scarce crews go to the top ward, then the lowest ward ids among the tied ones.
    got = a.loc[a["crews_assigned"] > 0, C.WARD_COL].tolist()
    assert got == ["DNCC_Ward_09", "DNCC_Ward_01", "DNCC_Ward_02"]
