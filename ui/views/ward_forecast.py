"""Ward forecast: one ward's outlook, why, and what-if."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from moshari import config as C
from moshari.data import ward_label
from moshari.risk import TIERS
from moshari.service import Scenario
from ui import state, theme

issue_date, horizon, cities = st.session_state["_controls"]
svc = state.service()
key = state.data_key()

wards = svc.wards if not cities else svc.wards[svc.wards[C.CITY_COL].isin(cities)]
options = list(wards.index)
if st.session_state.get("ward") not in options:
    st.session_state["ward"] = state.forecast_all(key, issue_date, horizon, cities).iloc[0][C.WARD_COL]

ward = st.session_state["ward"]
info = svc.wards.loc[ward]
theme.header(
    "Ward forecast",
    f"{ward_label(ward)}, {info[C.CITY_COL]}",
    [("Issued", state.fmt_short(issue_date)), ("Ahead", f"{horizon} weeks")],
)

sel, p1, p2, p3 = st.columns([4, 2, 2, 2], vertical_alignment="bottom", gap="medium")
sel.selectbox("Ward", options, key="ward",
              format_func=lambda w: f"{ward_label(w)}, {svc.wards.loc[w, C.CITY_COL]}")
for col, (k, v) in zip((p1, p2, p3), [
    ("People per km²", f"{info['population_density_sqkm']:,.0f}"),
    ("Water-logging risk", f"{info['water_logging_risk_index']:.2f}"),
    ("Sanitation score", f"{info['sanitation_score']:.2f}"),
]):
    col.html(f'<div class="m-stat" style="padding:.6rem .9rem"><div class="k">{k}</div>'
             f'<div class="v" style="font-size:1.2rem">{v}</div></div>')
st.html('<div style="height:1.2rem"></div>')

outlook = svc.ward_outlook(ward, issue_date)
main = outlook[outlook["horizon"] == horizon].iloc[0]
tier = TIERS[main["tier"]]
groups, feats, _ = svc.explain(ward, issue_date, horizon)

# --------------------------------------------------------------------------- hero + outlook
left, right = st.columns([5, 7], gap="large")
with left:
    with st.container(key="card-hero"):
        upside = (f" It could reach {theme.badge(main['upside_tier'])} at the upper end."
                  if main["upside_tier"] != main["tier"] else "")
        replay = ("" if np.isnan(main["actual"]) else
                  f'<div class="m-sub" style="margin:.5rem 0 0">Replay check: {main["actual"]:.0f} cases were reported that week.</div>')
        st.html(
            f"""<div class="m-hero">
                  <div class="k">Week of {state.fmt_week(main['target_date'])}</div>
                  <div class="tier" style="color:{tier.color}">{tier.name} risk</div>
                  <div class="num"><b>{main['expected_cases']:.1f}</b> expected cases, likely between
                    {main['lower_80']:.1f} and {main['upper_80']:.1f}.{upside}</div>{replay}
                  <div class="m-act"><b>{tier.action}</b><span>{tier.detail}</span></div>
                </div>"""
        )

with right:
    with st.container(key="card-outlook"):
        theme.card_title("Outlook", "Rain becomes mosquitoes in 1 to 2 weeks and symptoms follow, so the next 2 to 4 weeks are predictable.")
        steps = []
        for _, r in outlook.iterrows():
            t = TIERS[r["tier"]]
            steps.append(
                f'<div class="m-step{" on" if r["horizon"] == horizon else ""}">'
                f'<div class="h">In {r["horizon"]} weeks, {state.fmt_short(r["target_date"])}</div>'
                f'<div class="c" style="color:{t.color}">{r["expected_cases"]:.1f}</div>'
                f'<div class="r">{r["tier"]}, {r["lower_80"]:.0f} to {r["upper_80"]:.0f}</div></div>'
            )
        st.html(f'<div class="m-steps">{"".join(steps)}</div>')

        g = groups.sort_values("log_effect", ascending=False)
        up = g[g["log_effect"] > 0.05]
        down = g[g["log_effect"] < -0.05]
        why = []
        if not up.empty:
            why.append("Pushed up by " + ", ".join(
                f"<b>{r.group.lower()}</b> ×{r.multiplier:.1f}" for r in up.itertuples()) + ".")
        if not down.empty:
            why.append("Held down by " + ", ".join(
                f"<b>{r.group.lower()}</b> ×{r.multiplier:.2f}" for r in down.itertuples()) + ".")
        st.html(f'<div class="m-act" style="margin-top:1.2rem"><b>Why</b>'
                f'<span class="m-why">{" ".join(why) or "Close to an average ward-week."}</span></div>')

st.html('<div style="height:1.4rem"></div>')

# --------------------------------------------------------------------------- evidence
with st.container(key="card-evidence"):
    theme.card_title("What the model sees", "Recent rain and cases in this ward, and how each driver moves the forecast.")
    t_rain, t_drivers = st.tabs(["Rain and cases", "Drivers"])
    with t_rain:
        hist = svc.ward_history(ward, issue_date, weeks=16)
        after = svc.ward_history(ward, issue_date + pd.Timedelta(weeks=max(svc.bundle.horizons)),
                                 weeks=max(svc.bundle.horizons))
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_bar(x=hist[C.DATE_COL], y=hist["rainfall_mm"], name="Rainfall (mm)", marker_color=theme.RAIN,
                    opacity=0.35, marker_line_width=0, secondary_y=True,
                    hovertemplate="%{x|%d %b}: %{y:.0f} mm<extra></extra>")
        fig.add_scatter(x=hist[C.DATE_COL], y=hist[C.TARGET_COL], name="Reported cases", mode="lines",
                        line=dict(color=theme.INK, width=2.4, shape="spline"),
                        hovertemplate="%{x|%d %b}: %{y:.0f} cases<extra></extra>")
        fig.add_scatter(x=outlook["target_date"], y=outlook["upper_80"], mode="lines", line=dict(width=0),
                        showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=outlook["target_date"], y=outlook["lower_80"], mode="lines", line=dict(width=0),
                        fill="tonexty", fillcolor="rgba(17,117,109,0.15)", name="80% range", hoverinfo="skip")
        fig.add_scatter(x=outlook["target_date"], y=outlook["expected_cases"], name="Forecast", mode="lines+markers",
                        line=dict(color=theme.ACCENT, width=2.6, dash="dot"),
                        marker=dict(size=10, color=[TIERS[t].color for t in outlook["tier"]],
                                    line=dict(color=theme.BASE, width=2)),
                        hovertemplate="%{x|%d %b}: %{y:.1f} expected<extra></extra>")
        if not after.empty:
            fig.add_scatter(x=after[C.DATE_COL], y=after[C.TARGET_COL], name="Actually reported", mode="markers",
                            marker=dict(symbol="circle-open", size=10, line=dict(width=2, color=theme.MUTED)),
                            hovertemplate="%{x|%d %b}: %{y:.0f} reported<extra></extra>")
        fig.add_vline(x=issue_date, line=dict(color=theme.MUTED, width=1, dash="dash"))
        fig.update_yaxes(title_text=None, secondary_y=False, rangemode="tozero")
        fig.update_yaxes(title_text=None, secondary_y=True, showgrid=False, rangemode="tozero",
                         tickfont=dict(color=theme.RAIN))
        fig.update_layout(height=340, hovermode="x unified", bargap=0.3, margin=dict(l=4, r=4, t=36, b=4))
        st.plotly_chart(fig, use_container_width=True, config=theme.PLOT_CONFIG, theme=None)
        st.caption("Bars are weekly rainfall (right axis); the line is reported cases (left axis). "
                   "The dashed line marks the week the forecast was issued.")

    with t_drivers:
        g = groups.sort_values("log_effect")
        lim = max(float(np.abs(g["log_effect"]).max()) * 1.3, 0.3)
        ticks = [m for m in (0.25, 0.5, 1, 2, 4, 8) if abs(np.log(m)) <= lim]
        fig = go.Figure(go.Bar(
            x=g["log_effect"], y=g["group"], orientation="h", marker_line_width=0,
            marker_color=[TIERS["High"].color if v > 0 else theme.ACCENT for v in g["log_effect"]],
            text=[f"×{m:.2f}" for m in g["multiplier"]], textposition="outside", cliponaxis=False,
            hovertemplate="%{y}: ×%{text}<extra></extra>"))
        fig.update_layout(height=300, margin=dict(l=4, r=48, t=10, b=4),
                          xaxis=dict(range=[-lim, lim], tickvals=np.log(ticks), ticktext=[f"×{m:g}" for m in ticks],
                                     zeroline=True, zerolinecolor=theme.INK, zerolinewidth=1.5),
                          yaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True, config=theme.PLOT_CONFIG, theme=None)
        st.caption("TreeSHAP values from the model, shown as multipliers on expected cases. "
                   "Orange pushes risk up, teal holds it down.")

st.html('<div style="height:1.4rem"></div>')

# --------------------------------------------------------------------------- what-if
with st.container(key="card-whatif"):
    theme.card_title("What if the weather changed?",
                     "Adjust the last two weeks of weather. Moshari rebuilds the lag features and runs the model again.")
    with st.container(key="tray-sliders"):
        w1, w2, w3 = st.columns(3, gap="large")
        rain = w1.slider("Rainfall", 0.0, 3.0, 1.0, 0.1, format="×%.1f", key="wi_rain")
        temp = w2.slider("Temperature", -4.0, 4.0, 0.0, 0.5, format="%+.1f °C", key="wi_temp")
        hum = w3.slider("Humidity", -20.0, 20.0, 0.0, 1.0, format="%+.0f pts", key="wi_hum")
    st.html('<div style="height:1rem"></div>')
    scenario = Scenario(rain, temp, hum)
    if scenario.is_baseline:
        st.html('<p class="m-sub" style="margin:0">Move a slider to see how the outlook would change.</p>')
    else:
        alt = svc.ward_outlook(ward, issue_date, scenario)
        steps = []
        for (_, a), (_, b) in zip(alt.iterrows(), outlook.iterrows()):
            d = a["expected_cases"] - b["expected_cases"]
            color = TIERS["Critical"].color if d > 0.05 else (theme.ACCENT if d < -0.05 else theme.MUTED)
            steps.append(
                f'<div class="m-step"><div class="h">In {a["horizon"]} weeks</div>'
                f'<div class="c" style="color:{TIERS[a["tier"]].color}">{a["expected_cases"]:.1f}</div>'
                f'<div class="r"><span style="color:{color};font-weight:700">{d:+.1f}</span> vs forecast, {a["tier"]}</div></div>'
            )
        st.html(f'<div class="m-steps">{"".join(steps)}</div>')
