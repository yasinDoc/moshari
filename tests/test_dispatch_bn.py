"""Bangla dispatch notices: same facts as English, Bangla text, Unicode SMS within two parts."""

from __future__ import annotations

import io
import itertools
import re
import zipfile

import pandas as pd
import pytest

from moshari import config as C
from moshari import dispatch as D
from moshari import dispatch_bn as B
from moshari.risk import TIERS


def make_row(**over) -> dict:
    """The same sample ward row as tests/test_dispatch.py (kept local: CI can't import across tests)."""
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


LATIN_DIGIT = re.compile(r"[0-9]")


def _without_ids(text: str) -> str:
    """Drop the parts that stay Latin on purpose: ward codes, NS1, the sender and emoji keycaps."""
    return re.sub(r"[A-Z]+-W\d+|W\d+|NS1|DGHS", "", text)


# --------------------------------------------------------------------------- formatting
def test_bangla_digits_and_dates():
    assert B.bn(2025) == "২০২৫" and B.bn("12/40") == "১২/৪০"
    assert B.bn_date(pd.Timestamp("2025-06-23")) == "২৩ জুন"
    assert B.bn_date(pd.Timestamp("2025-08-04"), year=True) == "০৪ আগস্ট ২০২৫"
    assert B.ward_label_bn("DNCC_Ward_07") == "DNCC ওয়ার্ড ০৭"


def test_every_tier_and_city_has_a_translation():
    assert set(B.TIER_BN) == set(TIERS) == set(B.ACTION_BN)
    assert set(B.CITY_BN) == set(C.CITY_CORPORATIONS)
    assert {d[2] for d in D.SUPPLIES} == set(B.SUPPLY_BN)


@pytest.mark.parametrize("text, expected", [
    ("Hello", ("GSM-7", 5, 1)),
    ("x" * 160, ("GSM-7", 160, 1)),
    ("x" * 161, ("GSM-7", 161, 2)),
    ("€" * 80, ("GSM-7", 160, 1)),                 # extension characters cost two septets
    ("অ" * 70, ("Unicode", 70, 1)),
    ("অ" * 71, ("Unicode", 71, 2)),
    ("অ" * 134, ("Unicode", 134, 2)),
    ("অ" * 135, ("Unicode", 135, 3)),
])
def test_sms_parts_counts_like_a_gateway(text, expected):
    assert B.sms_parts(text) == expected


# --------------------------------------------------------------------------- SMS
def test_sms_carries_the_same_facts_in_bangla():
    text = B.sms(make_row())
    assert text.startswith("মশারি DNCC-W12: উচ্চ ঝুঁকি, ~১০ জন রোগী (সপ্তাহ ২৩ জুন)।")
    assert "স্যালাইন ৩২/৪০" in text and "কিট ৯/১২" in text and "শয্যা ৩/৩" in text
    assert "ঘাটতি: স্যালাইন, কিট।" in text
    assert text.endswith("-DGHS")
    assert not LATIN_DIGIT.search(_without_ids(text))
    assert B.sms_parts(text)[0] == "Unicode" and B.sms_parts(text)[2] <= B.BN_SMS_PARTS


@pytest.mark.parametrize("tier, deficit, crews, outs, ins, unplaced", list(itertools.product(
    list(TIERS), [False, True], [None, (1, 1), (0, 4)],
    [[], [("DNCC_Ward_03", 2)], [("DSCC_Ward_10", 1), ("DNCC_Ward_44", 3)]],
    [[], [("DNCC_Ward_05", 1)]], [0, 7])))
def test_sms_never_exceeds_two_parts_and_keeps_the_essentials(tier, deficit, crews, outs, ins, unplaced):
    row = make_row(tier=tier, tier_idx=list(TIERS).index(tier), expected_cases=123.4,
                   saline_bags_needed=1234, saline_bags_allocated=600 if deficit else 1234,
                   diagnostic_kits_needed=999, diagnostic_kits_allocated=999,
                   ward_id="DSCC_Ward_75", transfers_out=outs, transfers_in=ins, net_deficit=unplaced)
    if crews is None:
        row.pop("crews_assigned"), row.pop("crews_needed")
    else:
        row["crews_assigned"], row["crews_needed"] = crews
    text = B.sms(row)
    enc, n, parts = B.sms_parts(text)
    assert n <= B.BN_SMS_LIMIT and parts <= B.BN_SMS_PARTS
    assert "DSCC-W75" in text and B.TIER_BN[tier] in text
    assert "স্যালাইন" in text                       # supplies are never cut
    if D.deficit_items(row):
        assert "ঘাটতি" in text                      # nor is a deficit


def test_sms_keeps_patient_transfers_on_a_busy_ward():
    row = make_row(transfers_out=[("DNCC_Ward_03", 2)], net_deficit=1, crews_needed=4, crews_assigned=1)
    text = B.sms(row)
    assert "W03" in text and B.sms_parts(text)[2] <= 2        # where to send them survives
    calm = B.sms(make_row(transfers_out=[("DNCC_Ward_03", 2)]))
    assert "২ রোগী W03-এ পাঠান" in calm


# --------------------------------------------------------------------------- WhatsApp and brief
def test_whatsapp_in_bangla():
    msg = B.whatsapp(make_row(transfers_out=[("DNCC_Ward_03", 2)], net_deficit=1))
    assert msg.startswith("🟠 *মশারি নির্দেশনা: DNCC ওয়ার্ড ১২*")
    assert "ঢাকা উত্তর সিটি কর্পোরেশন · সপ্তাহ শুরু ২৩ জুন ২০২৫" in msg
    assert "*প্রাদুর্ভাবের সম্ভাবনা:* ৪২%" in msg
    assert "• স্যালাইন ব্যাগ: ৩২ / ৪০  ⚠️ ৮টি কম" in msg
    assert "২ জন রোগীকে DNCC ওয়ার্ড ০৩-এ পাঠান" in msg
    assert "*এখনই করণীয়:*" in msg and msg.endswith("— মশারি / DGHS")
    assert not LATIN_DIGIT.search(_without_ids(msg))


def test_no_ration_advice_when_nothing_arrived():
    acts = B.actions_bn(make_row(saline_bags_allocated=0))
    assert any("৪০টি স্যালাইন ব্যাগ চেয়ে নিন।" in a for a in acts)
    assert not any("প্রাপ্ত ০টি" in a for a in acts)


def test_brief_is_bangla_escaped_and_one_page_per_ward():
    rows = [make_row(), make_row(ward_id="CCC_Ward_02", tier="Critical", tier_idx=3)]
    doc = B.briefs_html(rows)
    assert doc.startswith('<!doctype html><html lang="bn">')
    assert doc.count('<section class="page"') == 2
    assert "কমিশনার ব্রিফ" in doc and "সংকটজনক ঝুঁকি" in doc and "চট্টগ্রাম সিটি কর্পোরেশন" in doc
    assert "প্রিন্ট / PDF হিসেবে সংরক্ষণ" in doc
    evil = B.brief_html(make_row(ward_id="<script>alert(1)</script>"))
    assert "<script>alert" not in evil


def test_export_zip_in_bangla():
    rows = [make_row(), make_row(ward_id="DSCC_Ward_04")]
    z = zipfile.ZipFile(io.BytesIO(D.export_zip(rows, lang="bn")))
    assert sorted(z.namelist()) == sorted(
        [f"{k}/{w}.{ext}" for w in ("DNCC_Ward_12", "DSCC_Ward_04")
         for k, ext in (("sms", "txt"), ("whatsapp", "txt"), ("briefs", "html"))] + ["briefs/all_briefs.html"])
    assert z.read("sms/DNCC_Ward_12.txt").decode("utf-8").startswith("মশারি DNCC-W12")


def test_english_output_is_unchanged_and_languages_are_checked():
    row = make_row()
    assert D.templates("en").sms(row) == D.sms(row)
    assert D.export_zip([row]) == D.export_zip([row], lang="en")
    with pytest.raises(ValueError):
        D.templates("fr")


# --------------------------------------------------------------------------- real weeks
@pytest.mark.skipif(not C.MODEL_PATH.exists(), reason="model not trained")
@pytest.mark.parametrize("issue, stock", [("2025-06-09", 0.4), ("2023-08-07", 0.5), ("2025-11-17", 1.0)])
def test_every_ward_fits_on_real_weeks(raw, issue, stock):
    from moshari import allocation as A
    from moshari import routing as R
    from moshari.model import ForecastBundle
    from moshari.service import ForecastService

    svc = ForecastService(raw, ForecastBundle.load())
    alloc = A.allocate(svc.forecast_all(pd.Timestamp(issue), 3), svc.wards, stock, 40)
    table = D.dispatch_table(alloc, R.route_overflow(alloc, R.load_bed_capacity()))
    for r in table.to_dict("records"):
        text = B.sms(r)
        assert B.sms_parts(text)[2] <= B.BN_SMS_PARTS, text
        if D.deficit_items(r):
            assert "ঘাটতি" in text
        for dest, _ in r["transfers_out"]:
            assert D.short_ward(dest, dest.split("_")[0]) in text or "স্থানান্তর" in text
