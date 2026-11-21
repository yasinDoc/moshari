"""Live mode: real weather from Open-Meteo, run through the trained model.

Cost controls
-------------
* **One request** fetches all five city corporations (Open-Meteo accepts a list of
  coordinates), 92 days of observed weather plus a 14-day forecast.
* **Disk cache** keyed by request: responses younger than ``ttl_hours`` are reused,
  so a dashboard open all day costs at most one call every six hours.
* **Graceful offline**: if the network fails, the last good response is used and
  labelled stale; if there is none, the caller gets a clear error.
* No API key, no personal data in the request.

Assumption: live dengue case reports are not connected yet, so each ward's recent
case history is estimated from its own seasonal average for those weeks. Weather
and ward vulnerability are real; the case-history features are estimates.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from . import config as C

API_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_DIR = C.PROJECT_ROOT / ".cache" / "open_meteo"
DAILY_VARS = ["precipitation_sum", "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
              "relative_humidity_2m_mean"]

# City corporation centres (approximate).
CITY_COORDS: dict[str, tuple[float, float]] = {
    "Dhaka North": (23.8759, 90.3795),
    "Dhaka South": (23.7104, 90.4074),
    "Chattogram": (22.3569, 91.7832),
    "Gazipur": (23.9999, 90.4203),
    "Narayanganj": (23.6238, 90.5000),
}


class LiveWeatherUnavailable(RuntimeError):
    """No network and no cached response to fall back on."""


@dataclass
class FetchInfo:
    source: str          # "network", "cache" or "stale cache"
    fetched_at: float    # unix time the data was downloaded
    api_calls: int       # requests made by this call (0 or 1)

    @property
    def age_minutes(self) -> float:
        return (time.time() - self.fetched_at) / 60


def _default_opener(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "moshari-dengue-early-warning/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def build_url(cities: dict[str, tuple[float, float]] = CITY_COORDS, past_days: int = 92, forecast_days: int = 14) -> str:
    params = {
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in cities.values()),
        "longitude": ",".join(f"{lon:.4f}" for _, lon in cities.values()),
        "daily": ",".join(DAILY_VARS),
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": "Asia/Dhaka",
    }
    return f"{API_URL}?{urllib.parse.urlencode(params)}"


def fetch_daily(
    cache_dir: Path = CACHE_DIR,
    ttl_hours: float = 6.0,
    force: bool = False,
    opener: Callable[[str, float], bytes] = _default_opener,
    cities: dict[str, tuple[float, float]] = CITY_COORDS,
) -> tuple[pd.DataFrame, FetchInfo]:
    """Daily weather per city (observed + forecast), from cache when fresh."""
    url = build_url(cities)
    key = hashlib.sha1(url.encode()).hexdigest()[:12]
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"

    cached = None
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if not force and time.time() - cached["fetched_at"] < ttl_hours * 3600:
            return _to_frame(cached["payload"], cities), FetchInfo("cache", cached["fetched_at"], 0)

    try:
        payload = json.loads(opener(url, 20.0))
        record = {"fetched_at": time.time(), "url": url, "payload": payload}
        path.write_text(json.dumps(record), encoding="utf-8")
        return _to_frame(payload, cities), FetchInfo("network", record["fetched_at"], 1)
    except Exception as exc:  # network down, timeout, bad JSON…
        if cached is not None:
            return _to_frame(cached["payload"], cities), FetchInfo("stale cache", cached["fetched_at"], 1)
        raise LiveWeatherUnavailable(f"Couldn't reach Open-Meteo and no cached weather exists yet ({exc}).") from exc


def _to_frame(payload, cities: dict[str, tuple[float, float]]) -> pd.DataFrame:
    payload = payload if isinstance(payload, list) else [payload]
    frames = []
    for city, block in zip(cities, payload):
        d = pd.DataFrame(block["daily"])
        d["city"] = city
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"])
    return df.rename(columns={
        "time": "day",
        "precipitation_sum": "rainfall_mm",
        "temperature_2m_mean": "avg_temp_c",
        "temperature_2m_max": "max_temp_c",
        "temperature_2m_min": "min_temp_c",
        "relative_humidity_2m_mean": "relative_humidity_pct",
    })


def to_weekly(daily: pd.DataFrame, today: pd.Timestamp | None = None) -> pd.DataFrame:
    """Aggregate to Monday-start weeks, like the training data.

    ``observed_days`` counts days up to ``today``; ``complete`` marks 7-day weeks.
    """
    today = pd.Timestamp(today or pd.Timestamp.now(tz="Asia/Dhaka").date()).normalize()
    d = daily.copy()
    d["date"] = d["day"] - pd.to_timedelta(d["day"].dt.weekday, unit="D")
    d["observed"] = d["day"] <= today
    agg = d.groupby(["city", "date"]).agg(
        rainfall_mm=("rainfall_mm", "sum"),
        avg_temp_c=("avg_temp_c", "mean"),
        max_temp_c=("max_temp_c", "mean"),
        min_temp_c=("min_temp_c", "mean"),
        relative_humidity_pct=("relative_humidity_pct", "mean"),
        days=("day", "count"),
        observed_days=("observed", "sum"),
    ).reset_index()
    agg["complete"] = agg["days"] == 7
    for col in ("rainfall_mm", "avg_temp_c", "max_temp_c", "min_temp_c", "relative_humidity_pct"):
        agg[col] = agg[col].round(2)
    return agg


def live_frame(raw: pd.DataFrame, weekly: pd.DataFrame, through: pd.Timestamp) -> pd.DataFrame:
    """Training-shaped rows for every ward, using live weather up to week ``through``.

    Case counts are each ward's seasonal average for that ISO week (see module docstring).
    """
    wk = weekly[(weekly["complete"]) & (weekly["date"] <= through)]
    clim = (raw.assign(woy=raw[C.DATE_COL].dt.isocalendar().week.astype(int))
               .groupby([C.WARD_COL, "woy"])[C.TARGET_COL].mean())
    wards = raw.drop_duplicates(C.WARD_COL)[[C.WARD_COL, C.CITY_COL, *C.STATIC_COLS]]
    rows = wards.merge(wk, left_on=C.CITY_COL, right_on="city", how="inner")
    woy = rows["date"].dt.isocalendar().week.astype(int)
    keys = pd.MultiIndex.from_arrays([rows[C.WARD_COL], woy])
    rows[C.TARGET_COL] = np.round(clim.reindex(keys).fillna(0).to_numpy(), 2)
    return rows[C.REQUIRED_COLS].sort_values([C.WARD_COL, C.DATE_COL]).reset_index(drop=True)


def issue_weeks(weekly: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    """(last fully observed week, last complete week including forecast days)."""
    complete = weekly[weekly["complete"]]
    observed = complete[complete["observed_days"] == 7]["date"].max()
    with_forecast = complete["date"].max()
    return pd.Timestamp(observed), pd.Timestamp(with_forecast)
