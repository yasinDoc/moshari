"""Cached resources and the shared forecast settings.

Cost controls live here: the model is deserialised once per server process
(``cache_resource``), features once per dataset fingerprint, and every
forecast table is memoised by its inputs (``cache_data``). Moving a slider
back to a value you've seen before costs nothing.
"""

from __future__ import annotations

import hashlib
import json
from io import BytesIO

import pandas as pd
import streamlit as st

from moshari import config as C
from moshari.data import file_fingerprint, load_dataset
from moshari.model import ForecastBundle
from moshari.risk import ALERT_POLICIES, DEFAULT_ALERT_POLICY
from moshari.service import ForecastService

BUNDLED = "bundled"


@st.cache_resource(show_spinner="Loading the forecast model…")
def get_bundle() -> ForecastBundle:
    return ForecastBundle.load()


@st.cache_resource(show_spinner="Preparing ward features…", max_entries=4)
def _service_for(key: str, payload: bytes | None) -> ForecastService:
    raw = load_dataset() if payload is None else load_dataset(BytesIO(payload))
    return ForecastService(raw, get_bundle())


def data_key() -> str:
    return st.session_state.get("data_key", f"{BUNDLED}:{file_fingerprint(C.RAW_DATA_PATH)}")


def service() -> ForecastService:
    return _service_for(data_key(), st.session_state.get("data_payload"))


def use_upload(payload: bytes, name: str) -> None:
    st.session_state["data_payload"] = payload
    st.session_state["data_name"] = name
    st.session_state["data_key"] = f"upload:{hashlib.sha1(payload).hexdigest()[:12]}"


def use_bundled() -> None:
    for k in ("data_payload", "data_name", "data_key"):
        st.session_state.pop(k, None)


def data_name() -> str:
    return st.session_state.get("data_name", "Challenge dataset (bundled)")


@st.cache_data(show_spinner=False, max_entries=256)
def forecast_all(key: str, issue_date: pd.Timestamp, horizon: int, cities: tuple[str, ...],
                 policy: str = DEFAULT_ALERT_POLICY) -> pd.DataFrame:
    return service().forecast_all(issue_date, horizon, list(cities) or None, policy)


def policy() -> str:
    return st.session_state.get("alert_policy") or DEFAULT_ALERT_POLICY


@st.cache_data(show_spinner=False, max_entries=64)
def forecast_timeline(key: str, issue_dates: tuple, horizon: int, cities: tuple[str, ...]) -> pd.DataFrame:
    return service().forecast_timeline(list(issue_dates), horizon, list(cities) or None)


@st.cache_data(show_spinner=False)
def metrics() -> dict:
    return json.loads(C.METRICS_PATH.read_text(encoding="utf-8")) if C.METRICS_PATH.exists() else {}


@st.cache_data(show_spinner=False)
def backtest() -> pd.DataFrame:
    return pd.read_parquet(C.BACKTEST_PATH) if C.BACKTEST_PATH.exists() else pd.DataFrame()


def fmt_week(d) -> str:
    return pd.Timestamp(d).strftime("%d %b %Y")


def fmt_short(d) -> str:
    return pd.Timestamp(d).strftime("%d %b")


def settings() -> tuple[pd.Timestamp, int, tuple[str, ...]]:
    """Render the forecast settings panel (inside the sidebar) and return its values."""
    svc = service()
    dates = svc.issue_dates
    _apply_query_params(svc)
    if st.session_state.get("issue_date") not in dates:
        st.session_state["issue_date"] = svc.default_issue_date()
    if st.session_state.get("horizon") not in svc.bundle.horizons:
        st.session_state["horizon"] = 3
    if st.session_state.get("alert_policy") not in ALERT_POLICIES:
        st.session_state["alert_policy"] = DEFAULT_ALERT_POLICY

    with st.container(key="settings"):
        st.select_slider(
            "Forecast issued",
            options=dates,
            key="issue_date",
            format_func=fmt_week,
            help="Moshari only uses data up to this week, as a health officer would on that Monday.",
        )
        st.segmented_control(
            "Weeks ahead",
            options=svc.bundle.horizons,
            key="horizon",
            width="stretch",
            help="Rain takes 2 to 4 weeks to turn into cases, so this is the early-warning window.",
        )
        st.selectbox(
            "Alert sensitivity",
            options=list(ALERT_POLICIES),
            key="alert_policy",
            format_func=lambda p: {"Standard": "Standard (expected)", "Balanced": "Balanced (midpoint)",
                                   "Cautious": "Cautious (upper range)"}[p],
        )
        cities = sorted(svc.wards[C.CITY_COL].unique())
        chosen = st.multiselect("City corporations", cities, key="cities", placeholder="All five")
    horizon = st.session_state.get("horizon") or 3
    return pd.Timestamp(st.session_state["issue_date"]), int(horizon), tuple(chosen)


# --------------------------------------------------------------------------- live weather
@st.cache_data(ttl=600, show_spinner="Fetching live weather…")
def live_weather(refresh_token: int = 0) -> tuple[pd.DataFrame, dict]:
    """Daily Open-Meteo weather. Disk cache (6 h) inside; this layer just avoids re-reading it."""
    from moshari import live

    daily, info = live.fetch_daily(force=refresh_token > 0)
    return daily, {"source": info.source, "fetched_at": info.fetched_at, "api_calls": info.api_calls}


@st.cache_resource(show_spinner="Running the model on live weather…", max_entries=8)
def live_service(fetched_at: float, observed_week: pd.Timestamp, last_week: pd.Timestamp,
                 use_forecast: bool) -> ForecastService:
    """Live rows run through the model: ward-adjusted weather, nowcast case history and,
    when ``use_forecast``, the Open-Meteo rain forecast for the weeks after ``observed_week``."""
    from moshari import live

    daily, _ = live_weather(st.session_state.get("live_refresh", 0))
    weekly = live.to_weekly(daily)
    frame = live.live_frame(service().raw, weekly, last_week, get_bundle(), nowcast_from=observed_week)
    return ForecastService(frame, get_bundle(), use_forecast=use_forecast)


# --------------------------------------------------------------------------- deep links
def link_params(issue_date, horizon: int, cities: tuple[str, ...]) -> dict:
    """Query parameters that reproduce the current settings (used by clickable ward tiles)."""
    params = {"issue": pd.Timestamp(issue_date).strftime("%Y-%m-%d"), "h": int(horizon), "policy": policy()}
    if cities:
        params["cities"] = ",".join(cities)
    return params


def _apply_query_params(svc: ForecastService) -> None:
    """Restore settings from a deep link once per session, then clear the URL."""
    qp = st.query_params
    if not qp or st.session_state.get("_qp_applied"):
        return
    st.session_state["_qp_applied"] = True
    try:
        if "issue" in qp:
            d = pd.Timestamp(qp["issue"])
            if d in set(svc.issue_dates):
                st.session_state["issue_date"] = d
        if "h" in qp and int(qp["h"]) in svc.bundle.horizons:
            st.session_state["horizon"] = int(qp["h"])
        if qp.get("policy") in ALERT_POLICIES:
            st.session_state["alert_policy"] = qp["policy"]
        if "cities" in qp:
            known = set(svc.wards[C.CITY_COL])
            st.session_state["cities"] = [c for c in qp["cities"].split(",") if c in known]
        if qp.get("ward") in set(svc.wards.index):
            st.session_state["ward"] = qp["ward"]
    except (ValueError, TypeError):
        pass  # a malformed link falls back to defaults
    st.query_params.clear()
