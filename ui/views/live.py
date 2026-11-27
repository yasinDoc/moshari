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
from ui import components, i18n, state, theme

T, tr, num, BN = i18n.t, i18n.tr, i18n.num, i18n.is_bn()

_, horizon, cities = st.session_state["_controls"]
policy = state.policy()
svc_hist = state.service()

try:
    daily, info = state.live_weather(st.session_state.get("live_refresh", 0), state.is_offline())
except live.LiveWeatherUnavailable as e:
    theme.header(T("Live outlook"), T("Real weather from Open-Meteo, run through the trained model"))
    # The reason comes from the weather client in English; in Bangla the page says it in general terms.
    st.warning(T("Live weather is unavailable right now. Live outlook needs one internet request (or a cached "
                 "copy); every other page works offline.") if BN else
               f"{e} Live outlook needs one internet request (or a cached copy); every other page works offline.")
    st.stop()

weekly = live.to_weekly(daily)
obs_week, fc_week = live.issue_weeks(weekly)

age_min = (time.time() - info["fetched_at"]) / 60
age = T("just now") if age_min < 1 else (T("{m:.0f} min ago", m=age_min) if age_min < 90
                                         else T("{h:.1f} h ago", h=age_min / 60))
src = T({"network": "Live", "cache": "Cached", "stale cache": "Offline copy",
         "offline cache": "Offline mode"}[info["source"]])

top_l, top_r = st.columns([5, 2], vertical_alignment="bottom")
with top_l:
    theme.header(
        T("Live outlook"),
        T("Real weather from Open-Meteo, run through the same trained model"),
        [("cloud", T("Weather"), src), ("update", T("Updated"), age)],
    )
use_fc = top_r.toggle(T("Use the 14-day rain forecast"), value=True, key="live_use_fc",
                       help=T("Rain falling in the next two weeks drives cases 3 to 4 weeks out. "
                              "With a realistic forecast, 4-week errors drop about 9% in testing."))
issue = obs_week
lsvc = state.live_service(info["fetched_at"], obs_week, fc_week, bool(use_fc))
fc = lsvc.forecast_all(issue, horizon, list(cities) or None, policy)
target = issue + pd.Timedelta(weeks=horizon)

wk = weekly[weekly["complete"]]
past4 = wk[(wk["date"] > obs_week - pd.Timedelta(weeks=4)) & (wk["date"] <= obs_week)]
ahead = daily[daily["day"] > pd.Timestamp(obs_week) + pd.Timedelta(days=6)]
rain_4w = past4.groupby("city")["rainfall_mm"].sum()
rain_next = ahead.groupby("city")["rainfall_mm"].sum()
city_risk = fc.groupby(C.CITY_COL)["expected_cases"].sum().sort_values(ascending=False)
theme.stats([
    ("water_drop", T("Rain, last 4 weeks"), f"{num(rain_4w.mean(), '.0f')}<small>{T(' mm')}</small>",
     T("average across the 5 cities")),
    ("rainy", T("Rain, next 14 days"), f"{num(rain_next.mean(), '.0f')}<small>{T(' mm')}</small>", T("Open-Meteo forecast")),
    ("notifications_active", T("Wards on alert"), f"{num(int(fc['alert'].sum()))}<small> / {num(len(fc))}</small>",
     T("for the week of {week}", week=state.fmt_short(target))),
    ("location_city", T("Highest expected"), tr(city_risk.index[0]) if len(city_risk) else T("None"),
     T("{n:.0f} cases across its wards", n=city_risk.iloc[0]) if len(city_risk) else ""),
])

with st.container(key="card-live-rain"):
    theme.card_title(T("Rain by city"), T("Weekly rainfall from Open-Meteo. Lighter bars are forecast weeks."),
                     T("{n} cities, {k} request", n=len(live.CITY_COORDS), k=1))
    shown = wk[wk["date"] > obs_week - pd.Timedelta(weeks=10)]
    palette = [theme.ACCENT, theme.RAIN, "#B79A62", "#7C8A96", "#9DB38A"]
    fig = go.Figure()
    for color, (city, g) in zip(palette, shown.groupby("city")):
        fut = g["observed_days"] < 7
        fig.add_bar(x=g["date"], y=g["rainfall_mm"], name=city, marker_line_width=0,
                    marker_color=color, marker_opacity=[0.4 if f else 1.0 for f in fut],
                    hovertemplate=T("{city}, week of %{{x|%d %b}}: %{{y:.0f}} mm", city=tr(city)) + "<extra></extra>")
    fig.add_vline(x=obs_week + pd.Timedelta(days=3.5), line=dict(color=theme.MUTED, width=1, dash="dash"))
    fig.add_annotation(x=obs_week + pd.Timedelta(days=3.5), y=1, yref="paper", text=T("Forecast"), showarrow=False,
                       xanchor="left", xshift=6, yanchor="top", font=dict(size=12, color=theme.MUTED))
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.05, xaxis=dict(tickformat="%d %b"))
    theme.plot(fig, 320)

theme.gap()

with st.container(key="card-live-net"):
    hi_any = int((fc["tier_idx"] >= 2).sum())
    sub = T("Forecast issued for the week of {issue}, looking {h} weeks ahead to {target}.",
            issue=state.fmt_week(issue), h=horizon, target=state.fmt_week(target))
    theme.card_title(T("Ward risk from live weather"), sub, T("{n} wards", n=len(fc)))
    if hi_any == 0 and fc["alert"].sum() == 0:
        st.html('<div class="m-act" style="margin:0"><div class="h">' + theme.icon("check_circle") +
                T("No ward is expected to reach high risk") + '</div><div class="b">'
                + T("Recent rain is too light to sustain Aedes breeding at outbreak levels. Routine surveillance is "
                    "enough; Moshari will flag wards here as the monsoon builds.") + '</div></div>')
    early_label = None if policy == "Standard" else T("Early alert ({policy} rule{caught})",
                                                       policy=T(policy) if BN else policy.lower(), caught="")
    st.html(components.ward_net(fc, lsvc.bundle.tier_thresholds, early_label))
    top = fc.head(3)
    st.html('<p class="m-note">' + T("Highest priority now: {wards}.", wards=", ".join(
        f"<b>{i18n.ward(r.ward_id)}</b> ({num(r.expected_cases, '.1f')}, {tr(TIERS[r.tier].name).lower()})"
        for r in top.itertuples())) + "</p>")

theme.gap()

left, right = st.columns([3, 2])
with left:
    with st.container(key="card-live-how"):
        theme.card_title(T("How live mode works"))
        steps = [
            ("cloud_download", "One request for all five cities",
             "92 days of observed weather plus a 14-day forecast, no API key"),
            ("save", "Cached on disk for 6 hours",
             "Reopening the page or switching settings costs no further calls"),
            ("wifi_off", "Works offline",
             "If the network drops, the last good response is used and labelled"),
            ("query_stats", "Case history is nowcast",
             "Live case reports aren't connected yet, so recent cases come from the model's own 2-week "
             "forecasts run on the live weather"),
            ("grid_on", "Ward-level weather",
             "City weather is adjusted to each ward using its history; in this data wards differ from "
             "their city by about 1% in rain, so little is lost"),
        ]
        st.html('<div class="m-list">' + "".join(
            f'<div class="m-row"><div class="n">{theme.icon(i)}</div><div><div class="w">{T(t)}</div>'
            f'<div class="c">{T(d)}</div></div><div></div></div>' for i, t, d in steps) + "</div>")

with right:
    with st.container(key="card-live-refresh"):
        theme.card_title(T("Weather data"), T("{src} copy from Open-Meteo, downloaded {age}.", src=src, age=age))
        st.html(f'<div class="m-prof" style="grid-template-columns:1fr 1fr">'
                f'<div><div class="k">{T("API calls this load")}</div><div class="v">{num(info["api_calls"])}</div></div>'
                f'<div><div class="k">{T("Cache lifetime")}</div><div class="v">{T("6 h")}</div></div></div>')
        if st.button(T("Refresh weather"), icon=":material/refresh:", width="stretch",
                     disabled=age_min < 10 or state.is_offline(),
                     help=T("Available 10 minutes after the last download, and not in offline mode.")):
            st.session_state["live_refresh"] = st.session_state.get("live_refresh", 0) + 1
            state.live_weather.clear()
            st.rerun()
        if age_min < 10:
            st.html('<p class="m-note">' + T("Refresh unlocks 10 minutes after the last download, "
                                             "so the page can never spam the API.") + '</p>')

theme.footer(svc_hist.bundle.metadata)
