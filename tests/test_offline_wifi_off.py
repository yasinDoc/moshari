"""S3: the app with Wi-Fi off, the way it will really happen on the day.

`test_offline.py` checks the MOSHARI_OFFLINE kill switch. This file checks the other case:
the laptop simply has no internet and nobody set the switch. Every non-loopback connection
and DNS lookup is refused (as with Wi-Fi off), proxy settings are removed, and each attempt
is recorded, so a test can say exactly which page tried to go online.

Guarantees:
- all 9 pages render with no error, and only Live outlook ever tries the internet;
- Live outlook with no saved weather shows a friendly warning instead of crashing;
- Live outlook with an old saved copy still works and says "Offline copy";
- with the switch on, Live outlook makes no network attempt at all.
"""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import pandas as pd
import pytest

from moshari import config as C
from moshari import live

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not C.MODEL_PATH.exists(), reason="model not trained")

PAGES = {
    "ui/views/ward_net.py": "Overview",
    "ui/views/resources.py": "Resources",
    "ui/views/hospital.py": "Hospital beds",
    "ui/views/simulator.py": "Simulator",
    "ui/views/dispatch.py": "Dispatch",
    "ui/views/live.py": "Live outlook",
    "ui/views/ward_forecast.py": "Ward forecast",
    "ui/views/model_check.py": "Model accuracy",
    "ui/views/data_source.py": "Data",
}
LIVE = "ui/views/live.py"
LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}
PROXY_VARS = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy")


def _host(address) -> str:
    return str(address[0]) if isinstance(address, tuple) and address else str(address)


@pytest.fixture()
def wifi_off(monkeypatch, tmp_path):
    """No internet, no proxy, switch NOT set, and an empty weather cache. Yields the list of
    hosts the code tried to reach."""
    attempts: list[str] = []
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
    real_create, real_getaddrinfo = socket.create_connection, socket.getaddrinfo

    def refuse(host: str) -> None:
        if host not in LOOPBACK:
            attempts.append(host)
            raise OSError(101, f"Network is unreachable ({host})")

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            refuse(_host(address))
        return real_connect(self, address)

    def connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            refuse(_host(address))
        return real_connect_ex(self, address)

    def create_connection(address, *args, **kwargs):
        refuse(_host(address))
        return real_create(address, *args, **kwargs)

    def getaddrinfo(host, *args, **kwargs):
        refuse(str(host or ""))
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    for var in PROXY_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("MOSHARI_OFFLINE", raising=False)
    monkeypatch.setattr(live, "CACHE_DIR", tmp_path / "open_meteo")

    import streamlit as st

    st.cache_data.clear()       # forget weather and forecasts cached by earlier tests
    yield attempts
    st.cache_data.clear()


def _canned_weather(url, timeout):
    """An Open-Meteo-shaped answer for all five cities: 92 past days and 14 forecast days."""
    start = pd.Timestamp.today().normalize() - pd.Timedelta(days=92)
    days = pd.date_range(start, periods=106, freq="D").strftime("%Y-%m-%d").tolist()
    block = {"daily": {"time": days, "precipitation_sum": [12.0] * 106, "temperature_2m_mean": [29.5] * 106,
                       "temperature_2m_max": [33.0] * 106, "temperature_2m_min": [26.0] * 106,
                       "relative_humidity_2m_mean": [82.0] * 106}}
    return json.dumps([block] * len(live.CITY_COORDS)).encode()


def _save_old_weather(hours_old: float = 48) -> None:
    """Seed the cache as if the app downloaded weather `hours_old` hours ago, before Wi-Fi went off."""
    live.fetch_daily(opener=_canned_weather, offline=False)
    for f in Path(live.CACHE_DIR).glob("*.json"):
        record = json.loads(f.read_text(encoding="utf-8"))
        record["fetched_at"] = time.time() - hours_old * 3600
        f.write_text(json.dumps(record), encoding="utf-8")


def _open(page: str):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.run()
    at.switch_page(page)
    at.run()
    return at


def _text(at) -> str:
    parts = [e.value for e in at.get("html")] + [e.value for e in at.markdown] + [e.value for e in at.warning]
    return "\n".join(str(p) for p in parts)


# --------------------------------------------------------------------------- the guard itself
def test_wifi_off_really_cuts_the_internet(wifi_off):
    import urllib.request

    with pytest.raises(OSError):
        urllib.request.urlopen("https://api.open-meteo.com/v1/forecast", timeout=5)
    assert wifi_off == ["api.open-meteo.com"]


# --------------------------------------------------------------------------- every page
@pytest.mark.parametrize("page", list(PAGES), ids=list(PAGES.values()))
def test_every_page_works_with_wifi_off(wifi_off, page):
    at = _open(page)
    assert not at.exception, f"{PAGES[page]} crashed offline: {[e.value for e in at.exception]}"
    assert PAGES[page] in _text(at), f"{PAGES[page]} did not show its title"
    if page != LIVE:
        assert wifi_off == [], f"{PAGES[page]} tried the internet: {sorted(set(wifi_off))}"


# --------------------------------------------------------------------------- Live outlook
def test_live_outlook_without_saved_weather_explains_instead_of_crashing(wifi_off):
    at = _open(LIVE)
    assert not at.exception
    warnings = " ".join(w.value for w in at.warning)
    assert "Couldn't reach Open-Meteo" in warnings
    assert "every other page works offline" in warnings
    assert set(wifi_off) == {"api.open-meteo.com"}, "Live outlook should try one host, once refused, and stop"


def test_live_outlook_with_an_old_saved_copy_still_works(wifi_off):
    _save_old_weather(hours_old=48)
    wifi_off.clear()
    at = _open(LIVE)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.warning, [w.value for w in at.warning]
    assert "Offline copy" in _text(at)
    assert set(wifi_off) == {"api.open-meteo.com"}


def test_switch_on_means_no_network_attempt_at_all(wifi_off, monkeypatch):
    _save_old_weather(hours_old=48)
    wifi_off.clear()
    monkeypatch.setenv("MOSHARI_OFFLINE", "1")
    at = _open(LIVE)
    assert not at.exception, [e.value for e in at.exception]
    assert "Offline mode" in _text(at)
    assert wifi_off == [], f"offline switch on, yet the app tried {sorted(set(wifi_off))}"


def test_switch_on_without_saved_weather_explains(wifi_off, monkeypatch):
    monkeypatch.setenv("MOSHARI_OFFLINE", "1")
    at = _open(LIVE)
    assert not at.exception
    assert "Offline mode is on and no weather has been cached yet." in " ".join(w.value for w in at.warning)
    assert wifi_off == []
