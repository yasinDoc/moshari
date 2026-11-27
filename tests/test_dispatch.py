"""Dispatch notices: SMS length, content, escaping, routing merge and exports."""

from __future__ import annotations

import io
import itertools
import zipfile

import pandas as pd
import pytest

from moshari import dispatch as D


def make_row(**over) -> dict:
    row = {
        "ward_id": "DNCC_Ward_12", "city": "Dhaka", "date": pd.Timestamp("2025-06-02"),
        "target_date": pd.Timestamp("2025-06-23"), "expected_cases": 10.2, "lower_80": 6.0, "upper_80": 15.0,
        "tier": "High", "tier_idx": 2, "p_crit": 0.42,
        "saline_bags_needed": 40, "saline_bags_allocated": 32,
        "diagnostic_kits_needed": 12, "diagnostic_kits_allocated": 9,
        "hospital_beds_required": 3, "hospital_beds_allocated": 3,
        "crews_needed": 2, "crews_assigned": 2, "priority_rank": 4,
        "transfers_out": [], "transfers_in": [], "bed_capacity": 3, "net_deficit": 0,
    }
    row.update(over)
    return row


# --------------------------------------------------------------------------- SMS
def test_sms_matches_brief_example():
    text = D.sms(make_row())
    assert text.startswith("MOSHARI DNCC-W12: HIGH risk, ~10 cases wk of 23 Jun.")
    assert "Saline 32/40, kits 9/12, beds 3/3." in text
    assert "DEFICIT saline, kits." in text
    assert "Crews: 2." in text
    assert text.endswith("-DGHS")
    assert D.gsm_length(text) <= 160


@pytest.mark.parametrize("tier,cases,outs,ins,unplaced,crews", list(itertools.product(
    ["Low", "Critical"], [0.2, 9.6, 1234.0],
    [[], [("DNCC_Ward_03", 4), ("DNCC_Ward_07", 2), ("DNCC_Ward_41", 11)]],
    [[], [("DNCC_Ward_01", 3)]], [0, 25], [(0, 0), (1, 9)],
)))
def test_sms_always_fits_one_segment(tier, cases, outs, ins, unplaced, crews):
    got, need = crews
    row = make_row(tier=tier, expected_cases=cases, transfers_out=outs, transfers_in=ins, net_deficit=unplaced,
                   crews_assigned=got, crews_needed=need, saline_bags_needed=99999, saline_bags_allocated=1,
                   diagnostic_kits_needed=88888, diagnostic_kits_allocated=0)
    text = D.sms(row)
    assert D.gsm_length(text) <= D.SMS_LIMIT, text
    assert text.isascii()
    # Essentials survive every shortening step.
    assert "DNCC-W12" in text and tier.upper() in text
    assert "saline" in text.lower() or "S1/" in text


def test_sms_shortens_long_details_before_dropping_essentials():
    outs = [(f"DNCC_Ward_{i:02d}", 1) for i in range(1, 30)]
    text = D.sms(make_row(transfers_out=outs, net_deficit=3))
    assert D.gsm_length(text) <= 160
    assert "DEFICIT" in text or "SHORT" in text


def test_sms_fully_supplied_and_missing_optional_fields():
    row = {"ward_id": "CCC_Ward_01", "tier": "Low", "expected_cases": 0.1}
    text = D.sms(row)
    assert text.startswith("MOSHARI CCC-W01: LOW risk, <1 case")
    assert D.gsm_length(text) <= 160


def test_gsm_length_counts_extension_and_unicode():
    assert D.gsm_length("abc") == 3
    assert D.gsm_length("~") == 2            # GSM extension table
    assert D.gsm_length("মশা") > 3          # forces UCS-2


# --------------------------------------------------------------------------- WhatsApp
def test_whatsapp_has_supplies_crews_deficit_and_actions():
    msg = D.whatsapp(make_row(crews_assigned=1, transfers_out=[("DNCC_Ward_03", 2)]))
    assert msg.splitlines()[0] == "🟠 *MOSHARI dispatch: DNCC Ward 12*"
    assert "• Saline bags: 32 / 40  ⚠️ short 8" in msg
    assert "• Hospital beds: 3 / 3  ✅" in msg
    assert "*Spraying crews:* 1 assigned (needs 2)" in msg
    assert "Send 2 patients to DNCC Ward 03" in msg
    assert "*DEFICIT:* Short 8 saline bags, 3 test kits; 1 more crew needed" in msg
    assert "*Do now:*" in msg and "Targeted vector control" in msg


def test_whatsapp_fully_supplied_has_no_deficit_line():
    msg = D.whatsapp(make_row(saline_bags_allocated=40, diagnostic_kits_allocated=12))
    assert "DEFICIT" not in msg


# --------------------------------------------------------------------------- brief
def test_brief_is_a_printable_page_with_supply_table():
    page = D.brief_html(make_row(transfers_in=[("DNCC_Ward_05", 1)]))
    assert page.startswith("<!doctype html>")
    assert "window.print()" in page and "@media print" in page
    assert page.count('<section class="page"') == 1
    assert "<td class=n>40</td><td class=n>32</td>" in page
    assert "Receive <b>1 patient</b> from DNCC Ward 05" in page
    assert "http://" not in page and "https://" not in page  # nothing to fetch: works offline


def test_brief_escapes_untrusted_values():
    page = D.brief_html(make_row(ward_id="DNCC_<script>alert(1)</script>", city="<b>x</b>"))
    assert "<script>alert(1)" not in page
    assert "&lt;script&gt;" in page


def test_briefs_html_one_page_per_ward():
    rows = [make_row(ward_id=f"DSCC_Ward_{i:02d}") for i in range(1, 6)]
    assert D.briefs_html(rows).count('<section class="page"') == 5


# --------------------------------------------------------------------------- table, selection, exports
@pytest.fixture()
def fc() -> pd.DataFrame:
    return pd.DataFrame({
        "ward_id": ["DNCC_Ward_01", "DNCC_Ward_02", "CCC_Ward_01"],
        "city": ["Dhaka", "Dhaka", "Chattogram"],
        "date": pd.Timestamp("2025-06-02"), "target_date": pd.Timestamp("2025-06-23"),
        "expected_cases": [20.0, 1.0, 9.0], "lower_80": [10.0, 0.0, 5.0], "upper_80": [30.0, 2.0, 14.0],
        "tier": ["Critical", "Low", "High"], "tier_idx": [3, 0, 2], "p_crit": [0.8, 0.0, 0.2],
    })


def test_standin_allocation_has_interface_columns_and_no_deficit(fc):
    alloc = D.standin_allocation(fc)
    for need, got, _, _ in D.SUPPLIES:
        assert (alloc[need] == alloc[got]).all()
    assert alloc.loc[alloc["ward_id"] == "DNCC_Ward_01", "saline_bags_needed"].item() == 48  # ceil(20 * 2.39)
    assert alloc["priority_rank"].tolist() == [1, 2, 3]
    assert alloc.iloc[0]["ward_id"] == "DNCC_Ward_01"
    assert (alloc.loc[alloc["tier_idx"] < 2, "crews_assigned"] == 0).all()
    assert not alloc["deficit_flag"].any()


def test_dispatch_table_merges_routing(fc):
    alloc = D.standin_allocation(fc)
    transfers = pd.DataFrame({"from_ward": ["DNCC_Ward_01"], "to_ward": ["DNCC_Ward_02"], "city": ["Dhaka"],
                              "patients": [3]})
    wards = pd.DataFrame({"ward_id": alloc["ward_id"], "bed_capacity": [2, 5, 3], "net_deficit": [1, 0, 0]})
    table = D.dispatch_table(alloc, (transfers, wards, None))
    by = table.set_index("ward_id")
    assert by.at["DNCC_Ward_01", "transfers_out"] == [("DNCC_Ward_02", 3)]
    assert by.at["DNCC_Ward_02", "transfers_in"] == [("DNCC_Ward_01", 3)]
    assert by.at["CCC_Ward_01", "transfers_out"] == []
    assert by.at["DNCC_Ward_01", "net_deficit"] == 1
    assert "Send 3 pts to W02." in D.sms(by.loc["DNCC_Ward_01"].to_dict() | {"ward_id": "DNCC_Ward_01"})


def test_dispatch_table_without_routing(fc):
    table = D.dispatch_table(D.standin_allocation(fc))
    assert all(v == [] for v in table["transfers_out"])


def test_select_rows_modes(fc):
    table = D.dispatch_table(D.standin_allocation(fc))
    assert set(D.select_rows(table, "high")["ward_id"]) == {"DNCC_Ward_01", "CCC_Ward_01"}
    assert D.select_rows(table, "deficit").empty
    assert D.select_rows(table, "pick", ["CCC_Ward_01"])["ward_id"].tolist() == ["CCC_Ward_01"]
    assert len(D.select_rows(table, "all")) == 3


def test_export_zip_layout(fc):
    rows = D.dispatch_table(D.standin_allocation(fc)).to_dict("records")
    with zipfile.ZipFile(io.BytesIO(D.export_zip(rows))) as z:
        names = set(z.namelist())
        assert {"sms/CCC_Ward_01.txt", "whatsapp/CCC_Ward_01.txt", "briefs/CCC_Ward_01.html",
                "briefs/all_briefs.html"} <= names
        assert len(z.read("sms/CCC_Ward_01.txt").decode().strip()) <= 160


def test_real_forecast_end_to_end(raw):
    """Every ward on a real forecast week gets three notices, all SMS within one segment."""
    from moshari.model import ForecastBundle
    from moshari.service import ForecastService

    svc = ForecastService(raw, ForecastBundle.load())
    fc = svc.forecast_all(svc.default_issue_date(), 3)
    rows = D.dispatch_table(D.standin_allocation(fc)).to_dict("records")
    assert len(rows) == len(fc)
    assert max(D.gsm_length(D.sms(r)) for r in rows) <= 160
    assert all(D.whatsapp(r) and D.brief_html(r) for r in rows)
