"""S2: the Hospital beds page shows exactly what the routing engine computes.

The unit and property tests prove `allocate()` and `route_overflow()` are right. This test
proves the page wires them together correctly: it opens the real Streamlit app in AppTest
(no browser, no server), on the demo week (issued 1 July 2024, 4 weeks ahead), and checks the
page's headline numbers and red list against the engine called directly. Then it moves the
surge slider and checks the page reacts.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd
import pytest

from moshari import config as C

APP = str(Path(__file__).resolve().parents[1] / "app.py")
ISSUE, HORIZON = "2024-07-01", 4

pytestmark = pytest.mark.skipif(not C.MODEL_PATH.exists(), reason="model not trained")


def _open_page():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=180)
    at.query_params["issue"] = ISSUE
    at.query_params["h"] = str(HORIZON)
    at.switch_page("ui/views/hospital.py")
    at.run()
    assert not at.exception, at.exception
    return at


def _page_html(at) -> str:
    return "\n".join(e.value for e in at.get("html"))


def _stat(page: str, label: str) -> str:
    m = re.search(rf'<span class="k">{re.escape(label)}</span>.*?<div class="v">(.*?)</div>', page, re.S)
    assert m, f"stat tile {label!r} not on the page"
    return re.sub(r"<[^>]+>", "", m.group(1)).replace(",", "").strip()


def _red_list(page: str) -> tuple[int, list[str]]:
    """The 'Still short after routing' card: its ward count and the ward names it lists."""
    m = re.search(r"<h3>Still short after routing</h3>.*?<span class=aside>(\d+) wards?</span>", page, re.S)
    assert m, "red list card not on the page"
    rest = page[m.end():]
    end = rest.find('<div class="m-gap">')
    block = rest if end < 0 else rest[:end]
    names = [html.unescape(n) for n in re.findall(r'<div class="w" style="color:[^"]+">(.*?)</div>', block)]
    return int(m.group(1)), names


@pytest.fixture(scope="module")
def page():
    return _open_page()


@pytest.fixture(scope="module")
def expected(page):
    """The same week computed straight from the engine, with the page's own alert policy."""
    from moshari.allocation import allocate
    from moshari.model import ForecastBundle
    from moshari.routing import load_bed_capacity, route_overflow
    from moshari.service import ForecastService
    from moshari.data import load_dataset

    svc = ForecastService(load_dataset(), ForecastBundle.load())
    fc = svc.forecast_all(pd.Timestamp(ISSUE), HORIZON, None, page.session_state["alert_policy"])
    return route_overflow(allocate(fc, svc.wards), load_bed_capacity())


def test_page_headline_matches_the_engine(page, expected):
    transfers, wards, _ = expected
    text = _page_html(page)
    assert int(_stat(text, "Beds available")) == int(wards["bed_capacity"].sum())
    assert int(_stat(text, "Beds needed")) == int(wards["beds_required"].sum())
    assert int(_stat(text, "Patients moved")) == int(transfers["patients"].sum())
    assert int(_stat(text, "Still short").split()[0]) == int((wards["net_deficit"] > 0).sum())


def test_red_list_shows_every_short_ward_and_only_those(page, expected):
    from moshari.data import ward_label

    _, wards, _ = expected
    short = wards[wards["net_deficit"] > 0]
    assert len(short) > 0, "the demo week should have short wards; pick another week if the data changed"
    count, names = _red_list(_page_html(page))
    assert count == len(short)
    assert sorted(names) == sorted(ward_label(w) for w in short["ward_id"])


def test_surge_slider_closes_the_gap():
    at = _open_page()
    before, _ = _red_list(_page_html(at))
    assert before > 0
    at.slider(key="hosp_surge").set_value(30).run()
    assert not at.exception, at.exception
    text = _page_html(at)
    assert "including +30% surge" in text
    after, names = _red_list(text)
    assert after == 0 and names == []
    assert int(_stat(text, "Still short").split()[0]) == 0
