"""The Overview supply strip and the Weekly briefing page, opened in the real app with AppTest.

Checks that the pages show what :mod:`moshari.briefing` computes, at the default scenario
(70% stock, 40 crews, no surge), and that the briefing's controls drive its PDF.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd
import pytest

from moshari import allocation as A
from moshari import briefing as B
from moshari.briefing_pdf import briefing_pdf
from test_offline import no_network  # noqa: F401  (fixture: blocks every non-local socket, as with Wi-Fi off)

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(scope="module")
def stores(monkeypatch_module):
    """Keep every AppTest run's media store, so download-button bytes can be read back."""
    import streamlit.testing.v1.app_test as T

    kept: list = []

    class Kept(T.MemoryMediaFileStorage):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            kept.append(self)

    monkeypatch_module.setattr(T, "MemoryMediaFileStorage", Kept)
    return kept


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="module")
def svc():
    from moshari.data import load_dataset
    from moshari.model import ForecastBundle
    from moshari.service import ForecastService
    return ForecastService(load_dataset(), ForecastBundle.load())


def _open(page: str, issue: str, h: int):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=300)
    at.query_params["issue"] = issue
    at.query_params["h"] = str(h)
    at.switch_page(page)
    at.run()
    assert not at.exception, at.exception
    return at


def _text(at) -> str:
    raw = " ".join(e.value for e in at.get("html"))
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def _pdf_bytes(at, stores) -> bytes:
    btn = [b for b in at.get("download_button") if "PDF" in b.proto.label]
    assert len(btn) == 1
    fid = btn[0].proto.url.rsplit("/", 1)[-1].split(".")[0]
    f = next(s._files_by_id[fid] for s in reversed(stores) if fid in s._files_by_id)
    assert f.mimetype == "application/pdf"
    return bytes(f.content)


@pytest.mark.parametrize("issue, h", [("2025-06-02", 3), ("2024-07-01", 4)])
def test_overview_strip_shows_the_shortages(svc, issue, h):
    at = _open("ui/views/ward_net.py", issue, h)
    fc = svc.forecast_all(pd.Timestamp(issue), h, None)
    alloc = A.allocate(fc, svc.wards, B.OVERVIEW_STOCK, B.OVERVIEW_CREWS)
    want = B.alert_text(B.supply_alerts(alloc, B.beds_routing(svc, fc, B.OVERVIEW_SURGE).ward_summary))
    text = _text(at)
    assert want in text and "short on saline" in want
    assert "At 70% stock and 40 crews." in text
    assert "Expected high risk" in text  # the rest of the page is still there


def test_overview_strip_links_to_the_pages():
    at = _open("ui/views/ward_net.py", "2024-07-01", 4)
    links = [p.proto.page for p in at.get("page_link")]
    assert any("briefing" in p for p in links)


def test_briefing_page_shows_the_decision_and_serves_its_pdf(svc, stores):
    at = _open("ui/views/briefing.py", "2025-06-02", 3)
    b = B.build(svc, pd.Timestamp("2025-06-02"), 3)
    text = _text(at)
    for line in b["decision"]:
        assert line in text
    assert _pdf_bytes(at, stores) == briefing_pdf(b)


def test_briefing_controls_change_the_pdf(svc, stores):
    at = _open("ui/views/briefing.py", "2025-06-02", 3)
    at.slider(key="brief_stock").set_value(30)
    at.number_input(key="brief_crews").set_value(10)
    at.slider(key="brief_surge").set_value(20)
    at.run()
    assert not at.exception
    b = B.build(svc, pd.Timestamp("2025-06-02"), 3, stock_pct=0.30, crews=10, surge_pct=20)
    assert _pdf_bytes(at, stores) == briefing_pdf(b)
    assert b["decision"][2] in _text(at)


def test_briefing_page_quiet_week(stores):
    at = _open("ui/views/briefing.py", "2016-02-29", 3)
    assert "No spraying crews are needed this week." in _text(at)
    assert _pdf_bytes(at, stores).startswith(b"%PDF")


def test_briefing_and_overview_work_with_the_internet_cut_off(no_network, stores):  # noqa: F811
    at = _open("ui/views/briefing.py", "2024-07-01", 4)
    assert _pdf_bytes(at, stores).startswith(b"%PDF")
    assert "Move 10 patients" in _text(at)
    assert "out of beds" in _text(_open("ui/views/ward_net.py", "2024-07-01", 4))
