from __future__ import annotations

import pandas as pd
import pytest

from moshari.routing import (
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
