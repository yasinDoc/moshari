"""Live outlook: today's real weather from Open-Meteo, run through the trained model."""

from __future__ import annotations

import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from moshari import config as C
from moshari import live
from moshari.data import ward_label
from moshari.risk import TIERS
from ui import components, state, theme

_, horizon, cities = st.session_state["_controls"]
policy = state.policy()
svc_hist = state.service()

try:
    daily, info = state.live_weather(st.session_state.get("live_refresh", 0))
except live.LiveWeatherUnavailable as e:
    theme.header("Live outlook", "Real weather from Open-Meteo, run through the trained model")
    st.warning(f"{e} Live mode needs one internet request; the rest of Moshari works offline.")
    st.stop()

weekly = live.to_weekly(daily)
obs_week, fc_week = live.issue_weeks(weekly)

age_min = (time.time() - info["fetched_at"]) / 60
age = "just now" if age_min < 1 else (f"{age_min:.0f} min ago" if age_min < 90 else f"{age_min / 60:.1f} h ago")
src = {"network": "Live", "cache": "Cached", "stale cache": "Offline copy"}[info["source"]]

top_l, top_r = st.columns([5, 2], vertical_alignment="bottom")
with top_l:
    theme.header(
        "Live outlook",
        "Real weather from Open-Meteo, run through the same trained model",
        [("cloud", "Weather", src), ("update", "Updated", age)],
    )
mode = top_r.segmented_control(
    "Weather used", ["Observed", "With 14-day forecast"], default="Observed", key="live_mode", width="stretch")
issue = fc_week if mode == "With 14-day forecast" else obs_week
lsvc = state.live_service(info["fetched_at"], issue)
fc = lsvc.forecast_all(issue, horizon, list(cities) or None, policy)
target = issue + pd.Timedelta(weeks=horizon)

wk = weekly[weekly["complete"]]
past4 = wk[(wk["date"] > obs_week - pd.Timedelta(weeks=4)) & (wk["date"] <= obs_week)]
ahead = daily[daily["day"] > pd.Timestamp(obs_week) + pd.Timedelta(days=6)]
rain_4w = past4.groupby("city")["rainfall_mm"].sum()
rain_next = ahead.groupby("city")["rainfall_mm"].sum()
city_risk = fc.groupby(C.CITY_COL)["expected_cases"].sum().sort_values(ascending=False)
theme.stats([
    ("water_drop", "Rain, last 4 weeks", f"{rain_4w.mean():.0f}<small> mm</small>", "average across the 5 cities"),
    ("rainy", "Rain, next 14 days", f"{rain_next.mean():.0f}<small> mm</small>", "Open-Meteo forecast"),
    ("notifications_active", "Wards on alert", f"{int(fc['alert'].sum())}<small> / {len(fc)}</small>",
     f"for the week of {state.fmt_short(target)}"),
    ("location_city", "Highest expected", city_risk.index[0] if len(city_risk) else "None",
     f"{city_risk.iloc[0]:.0f} cases across its wards" if len(city_risk) else ""),
])

with st.container(key="card-live-rain"):
    theme.card_title("Rain by city", "Weekly rainfall from Open-Meteo. Lighter bars are forecast weeks.",
                     f"{len(live.CITY_COORDS)} cities, 1 request")
    shown = wk[wk["date"] > obs_week - pd.Timedelta(weeks=10)]
    palette = [theme.ACCENT, theme.RAIN, "#B79A62", "#7C8A96", "#9DB38A"]
    fig = go.Figure()
    for color, (city, g) in zip(palette, shown.groupby("city")):
        fut = g["observed_days"] < 7
        fig.add_bar(x=g["date"], y=g["rainfall_mm"], name=city, marker_line_width=0,
                    marker_color=color, marker_opacity=[0.4 if f else 1.0 for f in fut],
                    hovertemplate=f"{city}, week of %{{x|%d %b}}: %{{y:.0f}} mm<extra></extra>")
    fig.add_vline(x=obs_week + pd.Timedelta(days=3.5), line=dict(color=theme.MUTED, width=1, dash="dash"))
    fig.add_annotation(x=obs_week + pd.Timedelta(days=3.5), y=1, yref="paper", text="Forecast", showarrow=False,
                       xanchor="left", xshift=6, yanchor="top", font=dict(size=12, color=theme.MUTED))
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.05, xaxis=dict(tickformat="%d %b"))
    theme.plot(fig, 320)

theme.gap()

with st.container(key="card-live-net"):
    hi_any = int((fc["tier_idx"] >= 2).sum())
    sub = (f"Forecast issued for the week of {state.fmt_week(issue)}, looking {horizon} weeks ahead to "
           f"{state.fmt_week(target)}.")
    theme.card_title("Ward risk from live weather", sub, f"{len(fc)} wards")
    if hi_any == 0 and fc["alert"].sum() == 0:
        st.html('<div class="m-act" style="margin:0"><div class="h">' + theme.icon("check_circle") +
                'No ward is expected to reach high risk</div><div class="b">Recent rain is too light to sustain '
                'Aedes breeding at outbreak levels. Routine surveillance is enough; Moshari will flag wards here as '
                'the monsoon builds.</div></div>')
    early_label = None if policy == "Standard" else f"Early alert ({policy.lower()} rule)"
    st.html(components.ward_net(fc, lsvc.bundle.tier_thresholds, early_label))
    top = fc.head(3)
    st.html('<p class="m-note">Highest priority now: ' + ", ".join(
        f"<b>{ward_label(r.ward_id)}</b> ({r.expected_cases:.1f}, {TIERS[r.tier].name.lower()})"
        for r in top.itertuples()) + ".</p>")

theme.gap()

left, right = st.columns([3, 2])
with left:
    with st.container(key="card-live-how"):
        theme.card_title("How live mode works")
        steps = [
            ("cloud_download", "One request for all five cities",
             "92 days of observed weather plus a 14-day forecast, no API key"),
            ("save", "Cached on disk for 6 hours",
             "Reopening the page or switching settings costs no further calls"),
            ("wifi_off", "Works offline",
             "If the network drops, the last good response is used and labelled"),
            ("info", "Case history is estimated",
             "Live case reports aren't connected yet, so each ward's recent cases use its seasonal average"),
        ]
        st.html('<div class="m-list">' + "".join(
            f'<div class="m-row"><div class="n">{theme.icon(i)}</div><div><div class="w">{t}</div>'
            f'<div class="c">{d}</div></div><div></div></div>' for i, t, d in steps) + "</div>")

with right:
    with st.container(key="card-live-refresh"):
        theme.card_title("Weather data", f"{src} copy from Open-Meteo, downloaded {age}.")
        st.html(f'<div class="m-prof" style="grid-template-columns:1fr 1fr">'
                f'<div><div class="k">API calls this load</div><div class="v">{info["api_calls"]}</div></div>'
                f'<div><div class="k">Cache lifetime</div><div class="v">6 h</div></div></div>')
        if st.button("Refresh weather", icon=":material/refresh:", width="stretch",
                     disabled=age_min < 10, help="Available 10 minutes after the last download."):
            st.session_state["live_refresh"] = st.session_state.get("live_refresh", 0) + 1
            state.live_weather.clear()
            st.rerun()
        if age_min < 10:
            st.html('<p class="m-note">Refresh unlocks 10 minutes after the last download, '
                    'so the page can never spam the API.</p>')

theme.footer(svc_hist.bundle.metadata)
