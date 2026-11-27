from __future__ import annotations

import pandas as pd
import pytest

from moshari.routing import (
    beds_to_clear,
    plain_summary,
    with_surge,
    beds_from_forecast,
    estimate_bed_capacity,
    load_bed_capacity,
    route_overflow,
)


def _table(rows):
    return pd.DataFrame(rows, columns=["ward_id", "city", "hospital_beds_required"])


@pytest.fixture()
def two_cities():
    alloc = _table([
        ("AAA_Ward_01", "Alpha", 9),   # 6 over
        ("AAA_Ward_02", "Alpha", 1),   # 2 spare
        ("AAA_Ward_05", "Alpha", 0),   # 3 spare
        ("BBB_Ward_01", "Beta", 0),    # 10 spare, but in another city
        ("BBB_Ward_02", "Beta", 2),
    ])
    cap = {"AAA_Ward_01": 3, "AAA_Ward_02": 3, "AAA_Ward_05": 3, "BBB_Ward_01": 10, "BBB_Ward_02": 2}
    return alloc, cap


def test_transfers_never_cross_cities(two_cities):
    alloc, cap = two_cities
    transfers, wards, _ = route_overflow(alloc, cap)
    city_of = dict(zip(alloc.ward_id, alloc.city))
    assert not transfers.empty
    for t in transfers.itertuples():
        assert city_of[t.from_ward] == city_of[t.to_ward] == t.city
    # Beta's spare beds stay unused even though Alpha still has 1 unplaced patient.
    assert wards.set_index("ward_id").loc["BBB_Ward_01", "received"] == 0
    assert wards.set_index("ward_id").loc["AAA_Ward_01", "net_deficit"] == 1


def test_patients_are_conserved(two_cities):
    alloc, cap = two_cities
    transfers, wards, _ = route_overflow(alloc, cap)
    assert wards["sent"].sum() == wards["received"].sum() == transfers["patients"].sum()
    placed = (wards["beds_in_use"] + wards["net_deficit"]).sum()
    assert placed == wards["beds_required"].sum()


def test_least_loaded_ward_fills_first_then_nearest():
    alloc = _table([
        ("AAA_Ward_01", "Alpha", 6),
        ("AAA_Ward_02", "Alpha", 2),   # 50% used
        ("AAA_Ward_03", "Alpha", 0),   # 0% used, near
        ("AAA_Ward_09", "Alpha", 0),   # 0% used, far
    ])
    cap = {"AAA_Ward_01": 2, "AAA_Ward_02": 4, "AAA_Ward_03": 1, "AAA_Ward_09": 1}
    transfers, *_ = route_overflow(alloc, cap)
    assert list(transfers.to_ward) == ["AAA_Ward_03", "AAA_Ward_09", "AAA_Ward_02"]
    assert list(transfers.patients) == [1, 1, 2]


def test_largest_overflow_is_placed_first_when_beds_run_short():
    """Two wards compete for 2 spare beds: the one 3 beds over goes first and gets both."""
    alloc = _table([
        ("AAA_Ward_01", "Alpha", 2),   # 1 over capacity
        ("AAA_Ward_02", "Alpha", 4),   # 3 over capacity
        ("AAA_Ward_03", "Alpha", 1),   # 2 spare beds
    ])
    cap = {"AAA_Ward_01": 1, "AAA_Ward_02": 1, "AAA_Ward_03": 3}
    transfers, wards, _ = route_overflow(alloc, cap)
    assert transfers[["from_ward", "to_ward", "patients"]].values.tolist() == [["AAA_Ward_02", "AAA_Ward_03", 2]]
    short = wards.set_index("ward_id")["net_deficit"]
    assert short.to_dict() == {"AAA_Ward_01": 1, "AAA_Ward_02": 1, "AAA_Ward_03": 0}


def test_no_ward_over_capacity_while_city_has_headroom(raw):
    cap = estimate_bed_capacity(_onsite_like(raw))
    peak = raw.loc[raw.groupby("ward_id")["dengue_cases"].idxmax(), ["ward_id", "city", "dengue_cases"]]
    alloc = beds_from_forecast(peak.rename(columns={"dengue_cases": "expected_cases"}))
    _, wards, cities = route_overflow(alloc, cap)
    for city, grp in wards.groupby("city"):
        spare = (grp["bed_capacity"] - grp["beds_in_use"]).sum()
        if grp["net_deficit"].sum() > 0:
            assert spare == 0, f"{city} left patients unplaced with {spare} spare beds"
    assert (wards["beds_in_use"] <= wards["bed_capacity"]).all()
    assert set(cities.columns) >= {"city", "total_capacity", "total_required", "utilization", "headroom"}


def test_output_columns_match_interface(two_cities):
    alloc, cap = two_cities
    transfers, wards, cities = route_overflow(alloc, cap)
    assert list(transfers.columns) == ["from_ward", "to_ward", "city", "patients"]
    assert list(wards.columns[:7]) == ["ward_id", "city", "beds_required", "bed_capacity",
                                       "net_deficit", "received", "sent"]
    assert list(cities.columns[:5]) == ["city", "total_capacity", "total_required", "utilization", "headroom"]


def test_no_overflow_means_no_transfers():
    alloc = _table([("AAA_Ward_01", "Alpha", 1), ("AAA_Ward_02", "Alpha", 2)])
    transfers, wards, _ = route_overflow(alloc, {"AAA_Ward_01": 3, "AAA_Ward_02": 3})
    assert transfers.empty and wards["net_deficit"].sum() == 0


def test_missing_capacity_is_an_error():
    alloc = _table([("AAA_Ward_01", "Alpha", 1)])
    with pytest.raises(ValueError, match="No bed capacity"):
        route_overflow(alloc, {})


def test_capacity_from_onsite_data_is_in_the_documented_range():
    cap = load_bed_capacity()
    assert len(cap) == 60
    assert cap.min() >= 1 and cap.max() <= 5


def _onsite_like(raw: pd.DataFrame) -> pd.DataFrame:
    """The bundled Phase 1 data plus a bed column at the onsite ratio, for tests that need history."""
    return raw.assign(hospital_beds_required=(raw["dengue_cases"] * 0.3).round())


def test_surge_beds_round_down_and_reduce_deficit(two_cities):
    alloc, cap = two_cities
    surged = with_surge(pd.Series(cap), 50)
    assert surged["AAA_Ward_01"] == 4 and surged["BBB_Ward_02"] == 3   # 3 * 1.5 -> 4, 2 * 1.5 -> 3
    _, base, base_city = route_overflow(alloc, cap)
    _, more, more_city = route_overflow(alloc, surged)
    assert more["net_deficit"].sum() <= base["net_deficit"].sum()
    assert beds_to_clear(base_city) == 1 and beds_to_clear(more_city) == 0
    with pytest.raises(ValueError):
        with_surge(pd.Series(cap), -10)


def test_plain_summary_names_short_city_first(two_cities):
    alloc, cap = two_cities
    *_, cities = route_overflow(alloc, cap)
    lines = plain_summary(cities)
    assert lines[0].startswith("Alpha is 1 bed short")
    assert "Beta needs no transfers" in lines[1]


def test_routing_60_wards_is_fast(raw):
    """Guards against an accidental O(n^3) loop or a hang, not a benchmark.

    One routing of the 60 wards takes about 1 ms. The bound is a generous 1 s per run so a
    slow or busy CI machine never fails it by chance, while a real blow-up still does.
    """
    import time
    cap = estimate_bed_capacity(_onsite_like(raw))
    peak = raw.loc[raw.groupby("ward_id")["dengue_cases"].idxmax(), ["ward_id", "city", "dengue_cases"]]
    alloc = beds_from_forecast(peak.rename(columns={"dengue_cases": "expected_cases"}))
    start = time.perf_counter()
    for _ in range(20):
        route_overflow(alloc, cap)
    assert (time.perf_counter() - start) / 20 < 1.0, "routing 60 wards took over 1 s per run"


# --------------------------------------------------------------------------- S2: properties on random cities
def _random_city_week(seed: int):
    """3 cities, 4–15 wards each, capacity 1–5, demand from quiet to 3× capacity."""
    import numpy as np

    rng = np.random.default_rng(seed)
    rows, cap = [], {}
    for c, code in (("Alpha", "AAA"), ("Beta", "BBB"), ("Gamma", "CCC")):
        n = int(rng.integers(4, 16))
        load = rng.uniform(0.2, 1.6)
        for i in rng.permutation(np.arange(1, n + 1)):
            w = f"{code}_Ward_{i:02d}"
            cap[w] = int(rng.integers(1, 6))
            rows.append((w, c, int(rng.poisson(cap[w] * load))))
    return _table(rows), cap


SEEDS = range(150)


@pytest.mark.parametrize("seed", SEEDS)
def test_routing_invariants_hold_on_random_cities(seed):
    alloc, cap = _random_city_week(seed)
    before = alloc.copy()
    transfers, wards, cities = route_overflow(alloc, cap)
    pd.testing.assert_frame_equal(alloc, before)                       # input untouched
    city_of = dict(zip(alloc.ward_id, alloc.city))
    w = wards.set_index("ward_id")

    # 1. never across cities, never a ward to itself, always a positive whole number
    assert all(city_of[t.from_ward] == city_of[t.to_ward] == t.city for t in transfers.itertuples())
    assert (transfers.from_ward != transfers.to_ward).all() and (transfers.patients > 0).all()
    # 2. patients conserved
    assert w.sent.sum() == w.received.sum() == transfers.patients.sum()
    assert ((w.beds_in_use + w.net_deficit) == (w.beds_required - w.sent + w.received)).all()
    # 3. no ward ends over capacity; a ward never both sends and receives
    assert (w.beds_in_use <= w.bed_capacity).all()
    assert not ((w.sent > 0) & (w.received > 0)).any()
    # 4. optimal on patients placed: each city places min(overflow, spare beds)
    for city, g in w.groupby("city"):
        overflow = (g.beds_required - g.bed_capacity).clip(lower=0).sum()
        spare = (g.bed_capacity - g.beds_required).clip(lower=0).sum()
        assert g.sent.sum() == min(overflow, spare), city
        assert g.net_deficit.sum() == overflow - min(overflow, spare), city
    # 5. city summary agrees with the ward table
    cs = cities.set_index("city")
    assert (cs.total_capacity == w.groupby("city").bed_capacity.sum()).all()
    assert (cs.total_required == w.groupby("city").beds_required.sum()).all()
    assert (cs.headroom == cs.total_capacity - cs.total_required).all()
    assert (cs.unplaced == w.groupby("city").net_deficit.sum()).all()


@pytest.mark.parametrize("seed", range(30))
def test_routing_is_deterministic_whatever_the_row_order(seed):
    alloc, cap = _random_city_week(seed)
    a = route_overflow(alloc, cap)
    b = route_overflow(alloc.sample(frac=1, random_state=seed), cap)
    for x, y in zip(a, b):
        pd.testing.assert_frame_equal(x.reset_index(drop=True), y.reset_index(drop=True))


def test_capacity_accepts_series_dict_or_frame(two_cities):
    alloc, cap = two_cities
    as_frame = pd.DataFrame({"ward_id": list(cap), "bed_capacity": list(cap.values())})
    results = [route_overflow(alloc, c).ward_summary for c in (cap, pd.Series(cap), as_frame)]
    for r in results[1:]:
        pd.testing.assert_frame_equal(results[0], r)


def test_fractional_demand_is_rounded_up_and_blanks_count_as_zero():
    alloc = pd.DataFrame({"ward_id": ["AAA_Ward_01", "AAA_Ward_02", "AAA_Ward_03"], "city": "Alpha",
                          "hospital_beds_required": [2.1, None, "n/a"]})
    _, wards, _ = route_overflow(alloc, {"AAA_Ward_01": 2, "AAA_Ward_02": 2, "AAA_Ward_03": 2})
    assert list(wards.beds_required) == [3, 0, 0]
    assert wards.set_index("ward_id").loc["AAA_Ward_01", "sent"] == 1


def test_zero_capacity_ward_only_sends_and_unnumbered_wards_still_route():
    alloc = _table([("AAA_Ward_01", "Alpha", 2), ("AAA_North", "Alpha", 0), ("AAA_Ward_02", "Alpha", 0)])
    transfers, wards, cities = route_overflow(alloc, {"AAA_Ward_01": 0, "AAA_North": 1, "AAA_Ward_02": 1})
    assert transfers.patients.sum() == 2
    assert wards.set_index("ward_id").loc["AAA_Ward_01", "net_deficit"] == 0
    # the numbered neighbour is "nearer" than the unnumbered ward, so it is filled first
    assert transfers.iloc[0].to_ward == "AAA_Ward_02"


def test_duplicate_wards_and_missing_columns_are_rejected():
    dup = _table([("AAA_Ward_01", "Alpha", 1), ("AAA_Ward_01", "Alpha", 2)])
    with pytest.raises(ValueError, match="more than one row"):
        route_overflow(dup, {"AAA_Ward_01": 3})
    with pytest.raises(ValueError, match="missing column"):
        route_overflow(dup.drop(columns="city"), {"AAA_Ward_01": 3})


def test_empty_table_gives_empty_results():
    transfers, wards, cities = route_overflow(_table([]), {})
    assert transfers.empty and wards.empty and cities.empty


def test_capacity_estimate_uses_only_years_up_to_2023():
    hist = pd.DataFrame({"date": pd.to_datetime(["2023-12-25"] * 10 + ["2024-01-01"]),
                         "ward_id": "AAA_Ward_01", "hospital_beds_required": [2] * 10 + [50]})
    assert estimate_bed_capacity(hist)["AAA_Ward_01"] == 2      # the 2024 spike is ignored
    with pytest.raises(ValueError, match="No rows"):
        estimate_bed_capacity(hist.assign(date=pd.Timestamp("2025-01-06")))


# --------------------------------------------------------------------------- S2: allocation -> routing contract
@pytest.fixture(scope="module")
def july_2024_forecast(raw):
    from moshari import config as C
    from moshari.model import ForecastBundle
    from moshari.service import ForecastService

    if not C.MODEL_PATH.exists():
        pytest.skip("model not trained")
    svc = ForecastService(raw, ForecastBundle.load())
    return svc.forecast_all(pd.Timestamp("2024-07-01"), 4), svc.wards


@pytest.mark.parametrize("pct", [0.3, 1.0])
def test_real_allocation_feeds_routing(july_2024_forecast, pct):
    from moshari.allocation import allocate

    fc, ward_profiles = july_2024_forecast
    alloc = allocate(fc, ward_profiles, stock_pct=pct)
    transfers, wards, cities = route_overflow(alloc, load_bed_capacity())
    assert len(wards) == 60 and set(cities.city) == set(alloc.city)
    # bed demand is routed as *required*, so stock scarcity does not change the plan
    assert wards.beds_required.sum() == alloc.hospital_beds_required.sum()
    assert transfers.patients.sum() > 0        # this week has real overflow to move
