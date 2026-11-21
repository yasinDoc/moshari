"""Live weather: aggregation, caching and offline fallback, with no real network calls."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from moshari import live
from moshari.data import load_dataset

CITIES = {"Dhaka North": (23.88, 90.38), "Chattogram": (22.36, 91.78)}


def _payload(start="2026-08-24", days=91):
    t = pd.date_range(start, periods=days, freq="D").strftime("%Y-%m-%d").tolist()
    block = {"daily": {"time": t, "precipitation_sum": [10.0] * days, "temperature_2m_mean": [30.0] * days,
                       "temperature_2m_max": [33.0] * days, "temperature_2m_min": [26.0] * days,
                       "relative_humidity_2m_mean": [80.0] * days}}
    return [block, block]


class FakeOpener:
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def __call__(self, url, timeout):
        self.calls += 1
        if self.fail:
            raise OSError("offline")
        return json.dumps(_payload()).encode()


def test_one_request_then_cache(tmp_path):
    op = FakeOpener()
    _, a = live.fetch_daily(tmp_path, opener=op, cities=CITIES)
    _, b = live.fetch_daily(tmp_path, opener=op, cities=CITIES)
    assert (a.source, b.source, op.calls) == ("network", "cache", 1)


def test_offline_falls_back_to_last_good_response(tmp_path):
    live.fetch_daily(tmp_path, opener=FakeOpener(), cities=CITIES)
    df, info = live.fetch_daily(tmp_path, force=True, opener=FakeOpener(fail=True), cities=CITIES)
    assert info.source == "stale cache" and len(df) == 2 * 91


def test_offline_without_cache_raises_clearly(tmp_path):
    with pytest.raises(live.LiveWeatherUnavailable):
        live.fetch_daily(tmp_path, opener=FakeOpener(fail=True), cities=CITIES)


def test_weekly_aggregation_matches_training_weeks(tmp_path):
    daily, _ = live.fetch_daily(tmp_path, opener=FakeOpener(), cities=CITIES)
    w = live.to_weekly(daily, today=pd.Timestamp("2026-11-22"))
    full = w[w["complete"]]
    assert (full["date"].dt.weekday == 0).all()          # Monday-start weeks
    assert (full["rainfall_mm"] == 70.0).all()           # 7 days x 10 mm
    assert (full["avg_temp_c"] == 30.0).all()


def test_live_frame_feeds_the_model(tmp_path):
    from moshari.features import FEATURE_COLS, build_features

    daily, _ = live.fetch_daily(tmp_path, opener=FakeOpener(), cities=CITIES)
    w = live.to_weekly(daily, today=pd.Timestamp("2026-11-22"))
    obs, _ = live.issue_weeks(w)
    raw = load_dataset()
    fr = live.live_frame(raw, w, obs)
    feats = build_features(fr)
    row = feats[feats["date"] == obs].dropna(subset=FEATURE_COLS)
    assert len(row) == raw[raw.city.isin(CITIES)]["ward_id"].nunique()


def test_nowcast_replaces_recent_case_estimates(tmp_path):
    from moshari.model import ForecastBundle

    daily, _ = live.fetch_daily(tmp_path, opener=FakeOpener(), cities=CITIES)
    w = live.to_weekly(daily, today=pd.Timestamp("2026-11-22"))
    obs, last = live.issue_weeks(w)
    raw = load_dataset()
    plain = live.live_frame(raw, w, last)
    nowcast = live.live_frame(raw, w, last, ForecastBundle.load(), nowcast_from=obs)
    recent = plain["date"] >= obs - pd.Timedelta(weeks=2)
    assert not plain.loc[recent, "dengue_cases"].equals(nowcast.loc[recent, "dengue_cases"])
    assert nowcast["dengue_cases"].ge(0).all()


def test_ward_weather_factors_are_near_neutral():
    f = live.ward_weather_factors(load_dataset())
    assert f["rain_ratio"].between(0.9, 1.1).all()
