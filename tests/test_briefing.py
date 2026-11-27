"""Weekly briefing: the numbers, the decision sentences, the Overview alert line and the PDF.

Every expected value is recomputed here from the engines (allocation, routing, simulation,
dispatch), so a briefing that drifts from what the other pages show fails. Weeks used:
2 Jun 2025, 3 weeks ahead (demo week: shortages, no transfers); 1 Jul 2024, 4 weeks ahead
(10 patients moved, 4 still without a bed); 29 Feb 2016 (no High ward, no crews needed).
"""

from __future__ import annotations

import re

import pandas as pd
import pytest

from moshari import allocation as A
from moshari import briefing as B
from moshari import config as C
from moshari import routing as R
from moshari import simulation as S
from moshari.briefing_pdf import briefing_pdf
from moshari.data import load_dataset, ward_label
from moshari.model import ForecastBundle
from moshari.service import ForecastService

DEMO, TRANSFERS, QUIET = ("2025-06-02", 3), ("2024-07-01", 4), ("2016-02-29", 3)


@pytest.fixture(scope="module")
def svc() -> ForecastService:
    return ForecastService(load_dataset(), ForecastBundle.load())


@pytest.fixture(scope="module")
def briefs(svc) -> dict:
    return {w: B.build(svc, pd.Timestamp(w[0]), w[1]) for w in (DEMO, TRANSFERS, QUIET)}


def _engines(svc, issue, h, cities=(), stock=0.70, crews=40, surge=0):
    fc = svc.forecast_all(pd.Timestamp(issue), h, list(cities) or None)
    alloc = A.allocate(fc, svc.wards, stock, crews)
    rr = R.route_overflow(A.allocate(fc, svc.wards), R.with_surge(R.load_bed_capacity(), surge))
    return fc, alloc, rr


def _pdf_text(data: bytes) -> tuple[int, str]:
    """(page count, drawn text) of an uncompressed reportlab PDF."""
    pages = len(re.findall(rb"/Type\s*/Page\b", data))
    strings = re.findall(rb"\(((?:[^()\\]|\\.)*)\)\s*Tj", data)
    text = " ".join(re.sub(rb"\\(.)", rb"\1", s).decode("latin-1") for s in strings)
    return pages, re.sub(r"\s+", " ", text)


# --------------------------------------------------------------------------- small helpers
@pytest.mark.parametrize("n, word, want", [(0, "ward", "0 wards"), (1, "ward", "1 ward"), (2, "crew", "2 crews")])
def test_plural(n, word, want):
    assert B.plural(n, word) == want


def test_alert_text_all_clear():
    assert B.alert_text({"saline_wards": 0, "kits_wards": 0, "crews_short": 0, "out_of_beds_wards": 0}) == \
        "All wards supplied"


def test_alert_text_order_singular_and_skips_zero():
    text = B.alert_text({"saline_wards": 1, "kits_wards": 0, "crews_short": 3, "out_of_beds_wards": 2})
    assert text == "1 ward short on saline · 3 crews short · 2 wards out of beds"


def test_alert_parts_kinds():
    parts = B.alert_parts({"saline_wards": 12, "kits_wards": 2, "crews_short": 0, "out_of_beds_wards": 3})
    assert [k for _, k in parts] == ["supplies", "supplies", "beds"]
    assert parts[0][0] == "12 wards short on saline"


# --------------------------------------------------------------------------- the numbers
def test_supply_alerts_match_allocation_and_routing(svc):
    fc, alloc, rr = _engines(svc, *DEMO)
    alerts = B.supply_alerts(alloc, rr.ward_summary)
    summ = A.summarize(alloc, 40)
    assert alerts["saline_wards"] == summ["resources"]["saline bags"]["wards_short"]
    assert alerts["kits_wards"] == summ["resources"]["test kits"]["wards_short"]
    assert alerts["crews_short"] == summ["crews"]["unmet"]
    assert alerts["out_of_beds_wards"] == int((rr.ward_summary["net_deficit"] > 0).sum())


def test_demo_week_numbers(svc, briefs):
    b = briefs[DEMO]
    fc, alloc, _ = _engines(svc, *DEMO)
    summ = A.summarize(alloc, 40)
    assert b["wards"] == len(fc) == 60
    assert b["high_wards"] == int((fc["tier_idx"] >= 2).sum())
    assert b["crews_needed"] == summ["crews"]["needed"] and b["crews_unmet"] == summ["crews"]["unmet"]
    assert b["saline_short_bags"] == summ["resources"]["saline bags"]["short"] > 0
    assert b["top_wards"] == list(fc[C.WARD_COL].head(5))
    assert b["transfers"] == [] and b["unplaced"] == 0
    assert b["alerts"]["out_of_beds_wards"] == 0


def test_transfer_week_routes_like_the_hospital_page(svc, briefs):
    b = briefs[TRANSFERS]
    _, _, rr = _engines(svc, *TRANSFERS)
    assert b["patients_moved"] == int(rr.transfers["patients"].sum()) > 0
    assert b["unplaced"] == int(rr.ward_summary["net_deficit"].sum()) > 0
    assert len(b["transfers"]) == len(rr.transfers)
    assert all(t["patients"] > 0 and t["from_ward"] != t["to_ward"] for t in b["transfers"])
    assert b["alerts"]["out_of_beds_wards"] == len(b["out_of_beds"]) > 0


def test_cases_prevented_uses_the_assigned_crews(svc, briefs):
    b = briefs[DEMO]
    _, alloc, _ = _engines(svc, *DEMO)
    table = S.build_effect_table(svc, pd.Timestamp(DEMO[0]))
    plan = {w: int(c) for w, c in zip(alloc[C.WARD_COL], alloc["crews_assigned"]) if c > 0}
    want = round(float(S.simulate(table, plan)[1]["cases_prevented"].sum()), 1)
    assert b["cases_prevented"] == pytest.approx(want, abs=0.05)
    assert b["cases_prevented"] > 0


def test_quiet_week_needs_no_crews(briefs):
    b = briefs[QUIET]
    assert b["high_wards"] == 0 and b["crews_needed"] == 0
    assert b["decision"][1] == "No spraying crews are needed this week."
    assert b["notices_ready"] == 0
    assert "short on saline" in B.alert_text(b["alerts"])  # stock is still scarce at 70%


def test_city_filter_and_scarcity_change_everything(svc):
    b = B.build(svc, pd.Timestamp(DEMO[0]), DEMO[1], cities=("Dhaka North",), stock_pct=0.30, crews=10, surge_pct=20)
    fc, alloc, rr = _engines(svc, *DEMO, cities=("Dhaka North",), stock=0.30, crews=10, surge=20)
    assert b["cities"] == ["Dhaka North"] and b["wards"] == len(fc) == 20
    assert b["deficit_wards"] == int(alloc["deficit_flag"].sum())
    assert b["unplaced"] == int(rr.ward_summary["net_deficit"].sum())
    assert [c["city"] for c in b["by_city"]] == ["Dhaka North"]


# --------------------------------------------------------------------------- the decision
def test_decision_sentences_demo_week(briefs):
    b = briefs[DEMO]
    assert b["decision"][0] == f"{b['high_wards']} of 60 wards are High or Critical risk for the week of 23 Jun 2025."
    assert b["decision"][1] == (f"Approve {b['crews_unmet']} more spraying crews: {b['crews_needed']} needed, "
                                f"{b['crews_assigned']} assigned.")
    assert b["decision"][2] == (f"Release {b['saline_short_bags']} more saline bags and {b['kits_short']} more test "
                                f"kits to cover {b['deficit_wards']} short wards.")
    assert b["decision"][3] == "No patient transfers are needed."
    assert b["decision"][0] in _pdf_text(briefing_pdf(b))[1]


def test_decision_with_transfers_and_missing_beds(briefs):
    b = briefs[TRANSFERS]
    assert b["decision"][3] == (f"Move {b['patients_moved']} patients between wards in the same city; beds are "
                                f"still missing for {b['unplaced']} patients.")
    assert b["decision"][3] in _pdf_text(briefing_pdf(b))[1]


def test_full_stock_means_fully_supplied(svc):
    b = B.build(svc, pd.Timestamp(DEMO[0]), DEMO[1], stock_pct=1.0, crews=300)
    assert b["deficit_wards"] == 0 and b["decision"][2] == "Every ward is fully supplied."
    assert b["decision"][1] == f"All {b['crews_needed']} crews needed are assigned."


def test_bad_stock_is_rejected(svc):
    with pytest.raises(ValueError):
        B.build(svc, pd.Timestamp(DEMO[0]), DEMO[1], stock_pct=0)


# --------------------------------------------------------------------------- the PDF
@pytest.mark.parametrize("week", [DEMO, TRANSFERS, QUIET])
def test_pdf_is_one_a4_page_with_the_decision(briefs, week):
    b = briefs[week]
    data = briefing_pdf(b)
    pages, text = _pdf_text(data)
    assert data.startswith(b"%PDF") and pages == 1
    assert re.search(rb"/MediaBox\s*\[\s*0 0 595\.2\d+ 841\.8\d+", data)
    for line in b["decision"]:
        assert line in text
    for heading in ("Weekly briefing", "Risk", "Supplies", "Patient transfers", "Crew plan", "Notices"):
        assert heading in text
    for w in b["top_wards"]:
        assert ward_label(w) in text


def test_pdf_lists_transfers_and_missing_beds(briefs):
    b = briefs[TRANSFERS]
    _, text = _pdf_text(briefing_pdf(b))
    t = b["transfers"][0]
    assert f"{ward_label(t['from_ward'])} to {ward_label(t['to_ward'])}: {t['patients']}" in text
    assert "Still out of beds" in text and ward_label(b["out_of_beds"][0]) in text


def test_pdf_is_deterministic_and_follows_the_data(briefs):
    a, b = briefing_pdf(briefs[DEMO]), briefing_pdf(briefs[DEMO])
    assert a == b
    assert briefing_pdf(briefs[TRANSFERS]) != a
