"""Ward forecast: one ward's 2-to-4-week outlook, why, and what-if."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from moshari import config as C
from moshari.data import ward_label
from moshari.features import FEATURE_SPECS
from moshari.risk import TIERS
from moshari.service import Scenario
from ui import state, theme

issue_date, horizon, cities = st.session_state["_controls"]
svc = state.service()
key = state.data_key()

wards = svc.wards
if cities:
    wards = wards[wards[C.CITY_COL].isin(cities)]
options = list(wards.index)
if st.session_state.get("ward") not in options:
    ranked = state.forecast_all(key, issue_date, horizon, cities)
    st.session_state["ward"] = ranked.iloc[0][C.WARD_COL]

left, right = st.columns([3, 2], vertical_alignment="bottom")
with left:
    ward = st.selectbox("Ward", options, key="ward", format_func=lambda w: f"{ward_label(w)}, {svc.wards.loc[w, C.CITY_COL]}")
info = svc.wards.loc[ward]
with right:
    st.caption(
        f"Population density {info['population_density_sqkm']:,.0f}/km², "
        f"water-logging risk {info['water_logging_risk_index']:.2f}, "
        f"sanitation score {info['sanitation_score']:.2f}"
    )

outlook = svc.ward_outlook(ward, issue_date)
main = outlook[outlook["horizon"] == horizon].iloc[0]
tier = TIERS[main["tier"]]

# --------------------------------------------------------------------------- hero
c1, c2 = st.columns([5, 7], gap="large")
with c1:
    upside = ""
    if main["upside_tier"] != main["tier"]:
        upside = f" Could reach {theme.pill(main['upside_tier'])} if the upper end plays out."
    actual = "" if np.isnan(main["actual"]) else (
        f'<div class="m-note" style="margin-top:.35rem">Replay check: {main["actual"]:.0f} cases were actually reported that week.</div>')
    st.html(
        f"""<div class="m-hero">
          <div class="m-kicker">{ward_label(ward)} in the week of {state.fmt_week(main['target_date'])}</div>
          <div class="tier" style="color:{tier.color}">{tier.name} risk</div>
          <div class="num"><b>{main['expected_cases']:.1f}</b> expected dengue cases,
            80% range {main['lower_80']:.1f} to {main['upper_80']:.1f}.{upside}</div>{actual}
          <div class="act"><strong>{tier.action}</strong><span>{tier.detail}</span></div>
        </div>"""
    )
with c2:
    st.markdown("##### The next four weeks")
    cols = st.columns(len(outlook))
    for col, (_, r) in zip(cols, outlook.iterrows()):
        t = TIERS[r["tier"]]
        selected = "font-weight:700;" if r["horizon"] == horizon else ""
        col.html(
            f"""<div class="m-step" style="border-color:{t.color}">
              <div class="h" style="{selected}">In {r['horizon']} weeks, {pd.Timestamp(r['target_date']).strftime('%d %b')}</div>
              <div class="c" style="color:{t.color}">{r['expected_cases']:.1f}</div>
              <div class="r">{r['tier']}, {r['lower_80']:.1f} to {r['upper_80']:.1f}</div></div>"""
        )
    st.caption("Weeks 2 to 4 are the early-warning window: rain that falls now becomes adult mosquitoes "
               "in 7 to 14 days, and symptoms follow about a week later.")

# --------------------------------------------------------------------------- breeding clock chart
st.subheader("Rain now, cases later")
hist = svc.ward_history(ward, issue_date, weeks=20)
future = svc.ward_history(ward, issue_date + pd.Timedelta(weeks=max(svc.bundle.horizons)), weeks=max(svc.bundle.horizons))
fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_bar(x=hist[C.DATE_COL], y=hist["rainfall_mm"], name="Weekly rainfall (mm)",
            marker_color=theme.RAIN, opacity=0.55, secondary_y=True,
            hovertemplate="%{x|%d %b}: %{y:.0f} mm<extra></extra>")
fig.add_scatter(x=hist[C.DATE_COL], y=hist[C.TARGET_COL], name="Reported cases", mode="lines+markers",
                line=dict(color=theme.INK, width=2.4), marker=dict(size=5),
                hovertemplate="%{x|%d %b}: %{y:.0f} cases<extra></extra>")
fig.add_scatter(x=outlook["target_date"], y=outlook["upper_80"], mode="lines", line=dict(width=0),
                showlegend=False, hoverinfo="skip")
fig.add_scatter(x=outlook["target_date"], y=outlook["lower_80"], mode="lines", line=dict(width=0),
                fill="tonexty", fillcolor="rgba(15,110,106,0.16)", name="80% range", hoverinfo="skip")
fig.add_scatter(x=outlook["target_date"], y=outlook["expected_cases"], name="Moshari forecast",
                mode="lines+markers", line=dict(color=theme.LAGOON, width=2.6, dash="dot"),
                marker=dict(size=9, color=[TIERS[t].color for t in outlook["tier"]],
                            line=dict(color="white", width=1.5)),
                hovertemplate="%{x|%d %b}: %{y:.1f} expected<extra></extra>")
if not future.empty:
    fig.add_scatter(x=future[C.DATE_COL], y=future[C.TARGET_COL], name="What happened (replay)",
                    mode="markers", marker=dict(symbol="x-thin", size=10, line=dict(width=2.2, color=theme.SLATE)),
                    hovertemplate="%{x|%d %b}: %{y:.0f} reported<extra></extra>")
bw_end = main["target_date"] - pd.Timedelta(weeks=2)
bw_start = main["target_date"] - pd.Timedelta(weeks=4)
fig.add_vrect(x0=bw_start - pd.Timedelta(days=3.5), x1=bw_end + pd.Timedelta(days=3.5),
              fillcolor=theme.RAIN, opacity=0.08, line_width=0,
              annotation_text="Breeding window for the selected week", annotation_position="top left",
              annotation_font=dict(size=11, color=theme.SLATE))
fig.add_vline(x=issue_date, line=dict(color=theme.SLATE, width=1, dash="dash"))
fig.add_annotation(x=issue_date, y=1, yref="paper", text="Forecast issued", showarrow=False,
                   xanchor="right", yanchor="bottom", font=dict(size=11, color=theme.SLATE))
fig.update_yaxes(title_text="Cases per week", secondary_y=False, rangemode="tozero")
fig.update_yaxes(title_text="Rainfall (mm)", secondary_y=True, showgrid=False, rangemode="tozero")
fig.update_layout(height=400, hovermode="x unified", bargap=0.25, margin=dict(t=50))
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# --------------------------------------------------------------------------- drivers
st.subheader("What's driving this forecast")
groups, feats, baseline = svc.explain(ward, issue_date, horizon)
g = groups.sort_values("log_effect")
labels = [f"×{m:.2f}" for m in g["multiplier"]]
d1, d2 = st.columns([7, 5], gap="large")
with d1:
    fig = go.Figure(
        go.Bar(
            x=g["log_effect"],
            y=g["group"],
            orientation="h",
            marker_color=[TIERS["High"].color if v > 0 else theme.LAGOON for v in g["log_effect"]],
            text=labels,
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}: multiplies expected cases by %{text}<extra></extra>",
        )
    )
    lim = max(abs(g["log_effect"]).max() * 1.35, 0.3)
    ticks = [m for m in (0.25, 0.5, 1, 2, 4, 8, 16) if abs(np.log(m)) <= lim]
    fig.update_layout(height=300, margin=dict(l=8, r=40, t=10, b=8),
                      xaxis=dict(range=[-lim, lim], tickvals=np.log(ticks), ticktext=[f"×{m:g}" for m in ticks],
                                 zeroline=True, zerolinecolor=theme.INK, zerolinewidth=1.5),
                      yaxis=dict(showgrid=False))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
with d2:
    top = g.iloc[::-1]
    up = top[top["log_effect"] > 0.05]
    down = top[top["log_effect"] < -0.05]
    parts = ["Compared with an average ward-week in the training data:"]
    if not up.empty:
        parts.append("Pushing risk up: " + ", ".join(f"{r.group.lower()} (×{r.multiplier:.1f})" for r in up.itertuples()) + ".")
    if not down.empty:
        parts.append("Holding it down: " + ", ".join(f"{r.group.lower()} (×{r.multiplier:.2f})" for r in down.itertuples()) + ".")
    st.html(f'<p class="m-note" style="font-size:.98rem;color:{theme.INK}">{" ".join(parts)}</p>')
    with st.expander("Top individual signals"):
        show = feats.head(8)
        st.dataframe(
            pd.DataFrame(
                {
                    "Signal": show["label"],
                    "Value": [f"{v:,.1f}" if isinstance(v, (int, float, np.floating)) else str(v) for v in show["value"]],
                    "Effect": [f"×{m:.2f}" for m in show["multiplier"]],
                }
            ),
            hide_index=True,
            use_container_width=True,
        )
    st.caption("Effects are TreeSHAP values from the model, shown as multipliers on expected cases.")

# --------------------------------------------------------------------------- what-if
st.subheader("What if the weather were different?")
st.caption("Adjust the last two weeks of weather for this ward. Moshari rebuilds the lag features and re-runs the model.")
w1, w2, w3 = st.columns(3)
rain = w1.slider("Rainfall, last 2 weeks", 0.0, 3.0, 1.0, 0.1, format="×%.1f", key="wi_rain")
temp = w2.slider("Temperature change", -4.0, 4.0, 0.0, 0.5, format="%+.1f °C", key="wi_temp")
hum = w3.slider("Humidity change", -20.0, 20.0, 0.0, 1.0, format="%+.0f pts", key="wi_hum")
scenario = Scenario(rain, temp, hum)
if scenario.is_baseline:
    st.html('<p class="m-note">Move a slider to compare a scenario with the forecast above.</p>')
else:
    alt = svc.ward_outlook(ward, issue_date, scenario)
    cols = st.columns(len(alt))
    for col, (_, a), (_, b) in zip(cols, alt.iterrows(), outlook.iterrows()):
        col.metric(
            f"In {a['horizon']} weeks",
            f"{a['expected_cases']:.1f} cases",
            delta=f"{a['expected_cases'] - b['expected_cases']:+.1f} vs forecast",
            delta_color="inverse",
        )
        col.html(theme.pill(a["tier"], f"{a['tier']} risk"))
