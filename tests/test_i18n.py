"""English / Bangla language switch: the catalog, the formatting helpers and the real app.

English must stay exactly what the code wrote before; Bangla must come from the catalog
(``src/moshari/locales/bn.json``) with Bangla digits, month names and ward labels.
"""

from __future__ import annotations

import json
import re
import string
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from moshari import briefing as B
from moshari import i18n

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
APP = str(ROOT / "app.py")
BENGALI = re.compile(r"[ঀ-৿]")


def _fields(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}


# --------------------------------------------------------------------------- the catalog
def test_catalog_is_a_bangla_mapping_with_matching_placeholders():
    cat = json.loads(i18n.CATALOG_PATH.read_text(encoding="utf-8"))
    assert len(cat) > 300
    for en, bn in cat.items():
        assert BENGALI.search(bn), en
        assert _fields(en) == _fields(bn), en


def test_page_titles_and_tiers_are_translated():
    for title, want in (("Overview", "সারসংক্ষেপ"), ("Ward map", "ওয়ার্ড মানচিত্র"),
                        ("Hospital beds", "হাসপাতাল শয্যা"), ("Weekly briefing", "সাপ্তাহিক ব্রিফিং")):
        assert i18n.t(title, "bn") == want
    assert [i18n.tier(n, "bn") for n in ("Low", "Medium", "High", "Critical")] == ["নিম্ন", "মাঝারি", "উচ্চ", "সংকটজনক"]


# --------------------------------------------------------------------------- t() and friends
def test_english_is_the_text_itself():
    assert i18n.t("{n} wards", "en", n=12) == "12 wards"
    assert i18n.t("Overview") == "Overview"
    assert i18n.t("{a:,} of {n:,} needed", "en", a=1234, n=5000) == "1,234 of 5,000 needed"


def test_bangla_uses_the_catalog_and_bangla_digits():
    assert i18n.t("{n} wards", "bn", n=12) == "১২টি ওয়ার্ড"
    assert i18n.t("{a:,} of {n:,} needed", "bn", a=1234, n=5000) == "৫,০০০টি প্রয়োজনের মধ্যে ১,২৩৪টি"
    assert i18n.t("{lo:.1f} to {hi:.1f}", "bn", lo=4.94, hi=12.06) == "৪.৯ থেকে ১২.১"


def test_text_arguments_keep_their_own_digits_and_unknown_language_is_english():
    # a ward code passed as text is not a number, so it is not rewritten
    assert "DNCC-W12" in i18n.t("Signed as {sender}.", "bn", sender="DNCC-W12")
    assert i18n.t("{n} wards", "fr", n=3) == "3 wards"
    assert i18n.norm("xx") == "en"


def test_missing_text_falls_back_to_english_and_is_recorded():
    i18n.MISSING.discard("A sentence nobody translated")
    assert i18n.t("A sentence nobody translated", "bn") == "A sentence nobody translated"
    assert "A sentence nobody translated" in i18n.MISSING


def test_digits_dates_and_wards():
    assert i18n.digits("2025-06-23 1.03") == "২০২৫-০৬-২৩ ১.০৩"
    assert i18n.week("2025-06-23", "bn") == "২৩ জুন ২০২৫"
    assert i18n.week("2025-06-23") == "23 Jun 2025"
    assert i18n.short("2023-08-07", "bn") == "০৭ আগস্ট"
    assert i18n.ward("DNCC_Ward_12", "bn") == "DNCC ওয়ার্ড ১২"
    assert i18n.ward("DNCC_Ward_12") == "DNCC Ward 12"
    assert i18n.date_fmt("2025-01-05", "%d %b", "bn") == "০৫ জানুয়ারি"


def test_tr_translates_finished_values():
    assert i18n.tr("Dhaka North", "bn") == "ঢাকা উত্তর"
    assert i18n.tr("12 / 30", "bn") == "১২ / ৩০"
    assert i18n.tr("ward_id", "bn") == "ward_id"           # dataset column names stay as typed
    assert i18n.tr("Dhaka North", "en") == "Dhaka North"


# --------------------------------------------------------------------------- core modules
def test_briefing_sentences_follow_the_language():
    alerts = {"saline_wards": 3, "kits_wards": 0, "crews_short": 2, "out_of_beds_wards": 1}
    assert B.alert_text(alerts) == "3 wards short on saline · 2 crews short · 1 ward out of beds"
    assert B.alert_text(alerts, "bn") == "৩টি ওয়ার্ডে স্যালাইনের ঘাটতি · ২টি দলের ঘাটতি · ১টি ওয়ার্ডে শয্যা নেই"
    assert B.alert_text({}, "bn") == "সব ওয়ার্ডে সরবরাহ পর্যাপ্ত"
    args = (pd.Timestamp("2025-06-23"), 60, 14, 20, 12, 8, 30, 10, 6, 5, 2)
    en, bn = B._decision(*args), B._decision_bn(*args)
    assert en[0] == "14 of 60 wards are High or Critical risk for the week of 23 Jun 2025."
    assert len(bn) == len(en) == 4
    assert bn[0] == "২৩ জুন ২০২৫ সপ্তাহে ৬০টি ওয়ার্ডের মধ্যে ১৪টি উচ্চ বা সংকটজনক ঝুঁকিতে।"
    assert all(BENGALI.search(s) and not re.search(r"[0-9]", s) for s in bn)


def test_deficit_note_bn_matches_the_english_rule():
    row = {"saline_bags_needed": 10, "saline_bags_allocated": 7, "diagnostic_kits_needed": 4,
           "diagnostic_kits_allocated": 4, "hospital_beds_required": 2, "hospital_beds_allocated": 1,
           "crews_needed": 3, "crews_assigned": 1}
    assert i18n.deficit_note_bn(row) == "ঘাটতি: ৩টি স্যালাইন ব্যাগ, ১টি শয্যা; আরও ২টি দল দরকার"
    full = {**row, "saline_bags_allocated": 10, "hospital_beds_allocated": 2, "crews_assigned": 3}
    assert i18n.deficit_note_bn(full) == "পুরো সরবরাহ পাওয়া গেছে"


# --------------------------------------------------------------------------- dashboard helpers
@pytest.fixture()
def ui_bn(monkeypatch):
    from ui import i18n as ui_i18n

    monkeypatch.setattr(ui_i18n, "lang", lambda: "bn")
    return ui_i18n


def test_ui_t_follows_the_session_language(ui_bn):
    assert ui_bn.t("Overview") == "সারসংক্ষেপ"
    assert ui_bn.t("{n} weeks", n=3) == "৩ সপ্তাহ"
    assert ui_bn.t("Overview", "en") == "Overview"


def test_tables_become_bangla_text_with_the_same_shape(ui_bn):
    df = pd.DataFrame({"Ward": ["DNCC Ward 07"], "Cases": [12.34], "Supplied": [0.8], "Risk": ["High"]})
    out, cfg = ui_bn.frame(df, formats={"Cases": ".1f", "Supplied": ".0%"})
    assert out.shape == df.shape
    assert list(out.columns) == ["ওয়ার্ড", "রোগী", "সরবরাহ", "ঝুঁকি"]
    assert out.iloc[0].tolist() == ["DNCC ওয়ার্ড ০৭", "১২.৩", "৮০%", "উচ্চ"]
    assert all(out[c].map(type).eq(str).all() for c in out.columns)


def test_figures_get_bangla_ticks_and_hover(ui_bn):
    fig = go.Figure(go.Bar(x=[1, 2, 3], y=["Dhaka North", "Gazipur", "Chattogram"], orientation="h",
                           hovertemplate="%{y}: %{x} high<extra></extra>"))
    ui_bn.localize_figure(fig)
    assert list(fig.data[0].y) == ["ঢাকা উত্তর", "গাজীপুর", "চট্টগ্রাম"]
    assert fig.data[0].hovertext[0] == "ঢাকা উত্তর: ১টি উচ্চ"
    assert fig.layout.xaxis.tickmode == "array"
    assert all(not re.search(r"[0-9]", s) for s in fig.layout.xaxis.ticktext)


# --------------------------------------------------------------------------- the real app
def _heads(at) -> str:
    # Older Streamlit test trees have no ``.html`` list, so read the raw element protos.
    return " ".join(h.proto.body for h in at.main.get("html"))


def test_app_switches_to_bangla_and_back():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=240)
    at.run()
    assert not at.exception
    assert at.session_state["lang"] == "en"
    assert any(c.label == "ভাষা / Language" for c in at.sidebar.button_group)
    assert "Dengue outlook for the week of" in _heads(at)
    at.session_state["lang"] = "bn"
    at.run()
    assert not at.exception
    assert "সারসংক্ষেপ" in _heads(at) and "Dengue outlook" not in _heads(at)
    assert at.sidebar.select_slider[0].label == "পূর্বাভাস প্রকাশের সপ্তাহ"
    at.session_state["lang"] = "en"
    at.run()
    assert "Dengue outlook for the week of" in _heads(at)
    assert at.sidebar.select_slider[0].label == "Forecast issued"


def test_link_with_lang_bn_opens_in_bangla():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=240)
    at.query_params["lang"] = "bn"
    at.run()
    assert not at.exception
    assert at.session_state["lang"] == "bn"
    assert "সারসংক্ষেপ" in _heads(at)
