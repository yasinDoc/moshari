"""Offline kill switch (module 5): everything runs with the network cut off.

Network access is blocked at the socket level, so any accidental HTTP call,
DNS lookup or remote font/API fetch inside Python fails the test.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pandas as pd
import pytest

from moshari import allocation as A
from moshari import config as C
from moshari import live
from moshari import simulation as S
from moshari.model import ForecastBundle
from moshari.service import ForecastService

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not C.MODEL_PATH.exists(), reason="model not trained")

PAGES = ["ui/views/ward_net.py", "ui/views/resources.py", "ui/views/simulator.py", "ui/views/live.py",
         "ui/views/ward_forecast.py", "ui/views/model_check.py", "ui/views/data_source.py"]


class NetworkBlocked(OSError):
    pass


LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}


def _host(address) -> str:
    return str(address[0]) if isinstance(address, tuple) and address else str(address)


@pytest.fixture()
def no_network(monkeypatch):
    """Block every non-loopback connection and DNS lookup (loopback never leaves the machine;
    asyncio needs it internally on Windows)."""
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
    real_create, real_getaddrinfo = socket.create_connection, socket.getaddrinfo

    def guard(host):
        if host not in LOOPBACK:
            raise NetworkBlocked(f"network access to {host!r} attempted while offline")

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            guard(_host(address))
        return real_connect(self, address)

    def connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            guard(_host(address))
        return real_connect_ex(self, address)

    def create_connection(address, *args, **kwargs):
        guard(_host(address))
        return real_create(address, *args, **kwargs)

    def getaddrinfo(host, *args, **kwargs):
        guard(str(host or ""))
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setenv("MOSHARI_OFFLINE", "1")
    yield


def test_guard_really_blocks_the_internet(no_network):
    import urllib.request

    with pytest.raises(OSError):
        urllib.request.urlopen("https://api.open-meteo.com/v1/forecast", timeout=5)


def test_switch_reads_environment(monkeypatch):
    monkeypatch.setenv("MOSHARI_OFFLINE", "1")
    assert C.offline()
    monkeypatch.setenv("MOSHARI_OFFLINE", "0")
    assert not C.offline()


def test_core_pipeline_runs_without_network(no_network, raw):
    svc = ForecastService(raw, ForecastBundle.load())
    week = pd.Timestamp("2025-06-02")
    fc = svc.forecast_all(week, 3)
    alloc = A.allocate(fc, svc.wards, stock_pct=0.5, total_crews=30)
    table = S.build_effect_table(svc, week)
    _, by_h = S.simulate(table, S.recommend(table, 20))
    assert len(fc) == 60 and alloc["deficit_flag"].any() and by_h["cases_prevented"].sum() > 0


def test_live_weather_offline_without_cache_fails_cleanly(no_network, tmp_path):
    with pytest.raises(live.LiveWeatherUnavailable):
        live.fetch_daily(tmp_path)


def _canned_weather(url, timeout):
    """A fixed Open-Meteo-shaped response for two cities (no network)."""
    import json

    days = pd.date_range("2026-08-24", periods=91, freq="D").strftime("%Y-%m-%d").tolist()
    block = {"daily": {"time": days, "precipitation_sum": [10.0] * 91, "temperature_2m_mean": [30.0] * 91,
                       "temperature_2m_max": [33.0] * 91, "temperature_2m_min": [26.0] * 91,
                       "relative_humidity_2m_mean": [80.0] * 91}}
    return json.dumps([block, block]).encode()


TWO_CITIES = {"Dhaka North": (23.88, 90.38), "Chattogram": (22.36, 91.78)}


def test_live_weather_offline_uses_cache_and_makes_no_calls(no_network, tmp_path):
    live.fetch_daily(tmp_path, opener=_canned_weather, cities=TWO_CITIES, offline=False)   # seed the cache
    df, info = live.fetch_daily(tmp_path, cities=TWO_CITIES, offline=True)
    assert info.source == "offline cache" and info.api_calls == 0 and len(df) == 2 * 91


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_offline(no_network, page):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    at.switch_page(page)
    at.run()
    assert not at.exception, f"{page} raised: {[e.value for e in at.exception]}"
