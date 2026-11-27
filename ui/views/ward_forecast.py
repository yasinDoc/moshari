"""Ward forecast: one ward's outlook, why, and what-if."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from moshari import config as C
from moshari.data import ward_label
from moshari.risk import TIERS, apply_alert_policy
from moshari.service import Scenario
from ui import i18n, state, theme

T, tr, num, BN = i18n.t, i18n.tr, i18n.num, i18n.is_bn()

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
    T("Ward forecast"),
    f"{i18n.ward(ward)}, {tr(C.CITY_CORPORATIONS.get(ward.split('_')[0], info[C.CITY_COL]))}",
    [("event", T("Issued"), state.fmt_week(issue_date)), ("schedule", T("Horizon"), T("{n} weeks", n=horizon))],
)

with st.container(key="card-ward"):
    c1, c2 = st.columns([2, 3], vertical_alignment="bottom")
    c1.selectbox(T("Ward"), options, key="ward",
                 format_func=i18n.bound(lambda w, lg: f"{i18n.core.ward(w, lg)}, {i18n.core.tr(svc.wards.loc[w, C.CITY_COL], lg)}"))
    c2.html(
        f"""<div class="m-prof">
              <div><div class="k">{T("People per km²")}</div><div class="v">{num(info['population_density_sqkm'], ',.0f')}</div></div>
              <div><div class="k">{T("Water-logging risk")}</div><div class="v">{num(info['water_logging_risk_index'], '.2f')}</div></div>
              <div><div class="k">{T("Sanitation score")}</div><div class="v">{num(info['sanitation_score'], '.2f')}</div></div>
            </div>"""
    )
theme.gap()

policy = state.policy()
outlook = apply_alert_policy(svc.ward_outlook(ward, issue_date), svc.bundle.tier_thresholds, policy)
main = outlook[outlook["horizon"] == horizon].iloc[0]
tier = TIERS[main["tier"]]
groups, feats, _ = svc.explain(ward, issue_date, horizon)

left, right = st.columns([5, 7])
with left:
    with st.container(key="card-hero"):
        upside = (T(" It could reach {tier} at the upper end.", tier=theme.badge(main['upside_tier']))
                  if main["upside_tier"] != main["tier"] else "")
        early = ""
        if main["alert"] and main["tier_idx"] < 2:
            early = (f'<p class="m-note" style="margin-top:8px;color:{theme.TIER_COLORS["Critical"]};font-weight:700">'
                     + T("On early alert: the upper end of the range reaches High ({policy} rule).",
                         policy=T(policy) if BN else policy.lower()) + '</p>')
        probs = ""
        if "p_high" in main and not pd.isna(main["p_high"]):
            bar = lambda p, c: (f'<span class="pb"><span style="width:{max(p, 0.02) * 100:.0f}%;background:{c}"></span></span>')  # noqa: E731
            probs = (f'<div class="m-probs">'
                     f'<div><span>{T("Chance of High")}</span>{bar(main["p_high"], TIERS["High"].color)}<b>{num(main["p_high"], ".0%")}</b></div>'
                     f'<div><span>{T("Chance of Critical")}</span>{bar(main["p_crit"], TIERS["Critical"].color)}<b>{num(main["p_crit"], ".0%")}</b></div>'
                     f'</div>')
            if bool(main.get("crit_watch")) and main["tier"] != "Critical":
                probs += (f'<p class="m-note" style="margin-top:6px;color:{theme.TIER_COLORS["Critical"]};font-weight:700">'
                          + T("Critical watch: outbreak-level cases are likely enough to prepare.") + '</p>')
        replay = ("" if np.isnan(main["actual"]) else
                  f'<p class="m-note" style="margin-top:8px">{T("Replay check: {n:.0f} cases were reported that week.", n=main["actual"])}</p>')
        st.html(
            f"""<div class="m-hero">
                  <div class="k">{T("Week of {week}", week=state.fmt_week(main['target_date']))}</div>
                  <div class="tier" style="color:{tier.ink}">{T("{tier} risk", tier=tr(tier.name))}</div>
                  <div class="num">{T("<b>{e:.1f}</b> expected cases, likely between\n                    {lo:.1f} and {hi:.1f}.",
                                      e=main['expected_cases'], lo=main['lower_80'], hi=main['upper_80'])}{upside}</div>{probs}{early}{replay}
                  <div class="m-act"><div class="h">{theme.icon('task_alt')}{T(tier.action)}</div>
                    <div class="b">{T(tier.detail)}</div></div>
                </div>"""
        )

with right:
    with st.container(key="card-outlook"):
        theme.card_title(T("Outlook"), T("Rain becomes mosquitoes in 1 to 2 weeks and symptoms follow, "
                                         "so the next 2 to 4 weeks can be forecast."))
        steps = []
        for _, r in outlook.iterrows():
            t = TIERS[r["tier"]]
            steps.append(
                f'<div class="m-step{" on" if r["horizon"] == horizon else ""}">'
                f'<div class="h">{T("In {n} weeks, {week}", n=r["horizon"], week=state.fmt_short(r["target_date"]))}</div>'
                f'<div class="c" style="color:{t.ink}">{num(r["expected_cases"], ".1f")}</div>'
                f'<div class="r">{tr(r["tier"])}, {T("{lo:.0f} to {hi:.0f} cases", lo=r["lower_80"], hi=r["upper_80"])}</div>'
                + (f'<div class="r">{T("Chance of Critical {p:.0%}", p=r["p_crit"])}</div>' if "p_crit" in r else "")
                + '</div>'
            )
        st.html(f'<div class="m-steps">{"".join(steps)}</div>')
        g = groups.sort_values("log_effect", ascending=False)
        up = g[g["log_effect"] > 0.05]
        down = g[g["log_effect"] < -0.05]
        why = []
        if not up.empty:
            why.append(T("Pushed up by {drivers}.", drivers=", ".join(
                f"<b>{T(r.group).lower()}</b> ×{num(r.multiplier, '.1f')}" for r in up.itertuples())))
        if not down.empty:
            why.append(T("Held down by {drivers}.", drivers=", ".join(
                f"<b>{T(r.group).lower()}</b> ×{num(r.multiplier, '.2f')}" for r in down.itertuples())))
        st.html(f'<div class="m-act" style="margin-top:0"><div class="h">{theme.icon("insights")}{T("Why")}</div>'
                f'<div class="b">{" ".join(why) or T("Close to an average ward-week.")}</div></div>')

theme.gap()

with st.container(key="card-evidence"):
    theme.card_title(T("What the model sees"), T("Recent rain and cases in this ward, and how each driver moves the forecast."))
    t_rain, t_drivers = st.tabs([T("Rain and cases"), T("Drivers")])
    with t_rain:
        hist = svc.ward_history(ward, issue_date, weeks=16)
        after = svc.ward_history(ward, issue_date + pd.Timedelta(weeks=max(svc.bundle.horizons)),
                                 weeks=max(svc.bundle.horizons))
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_bar(x=hist[C.DATE_COL], y=hist["rainfall_mm"], name=T("Rainfall (mm, right)"), marker_color=theme.RAIN,
                    opacity=0.35, marker_line_width=0, secondary_y=True,
                    hovertemplate="%{x|%d %b}: %{y:.0f} mm<extra></extra>")
        fig.add_scatter(x=hist[C.DATE_COL], y=hist[C.TARGET_COL], name=T("Reported cases"), mode="lines",
                        line=dict(color=theme.INK, width=2.4),
                        hovertemplate="%{x|%d %b}: %{y:.0f} cases<extra></extra>")
        fig.add_scatter(x=outlook["target_date"], y=outlook["upper_80"], mode="lines", line=dict(width=0),
                        showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=outlook["target_date"], y=outlook["lower_80"], mode="lines", line=dict(width=0),
                        fill="tonexty", fillcolor="rgba(14,115,105,0.14)", name=T("80% range"), hoverinfo="skip")
        fig.add_scatter(x=outlook["target_date"], y=outlook["expected_cases"], name=T("Forecast"), mode="lines+markers",
                        line=dict(color=theme.ACCENT, width=2.6, dash="dot"),
                        marker=dict(size=10, color=[TIERS[t].ink for t in outlook["tier"]],
                                    line=dict(color=theme.BASE, width=2)),
                        hovertemplate="%{x|%d %b}: %{y:.1f} expected<extra></extra>")
        if not after.empty:
            fig.add_scatter(x=after[C.DATE_COL], y=after[C.TARGET_COL], name=T("Actually reported"), mode="markers",
                            marker=dict(symbol="circle-open", size=10, color=theme.MUTED, line=dict(width=2, color=theme.MUTED)),
                            hovertemplate="%{x|%d %b}: %{y:.0f} reported<extra></extra>")
        fig.add_vline(x=issue_date, line=dict(color=theme.MUTED, width=1, dash="dash"))
        fig.add_annotation(x=issue_date, y=1, yref="paper", text=T("Issued"), showarrow=False, xanchor="left",
                           xshift=6, yanchor="top", font=dict(size=12, color=theme.MUTED))
        fig.update_yaxes(secondary_y=False, rangemode="tozero")
        fig.update_yaxes(secondary_y=True, showgrid=False, rangemode="tozero", tickfont=dict(color=theme.RAIN))
        fig.update_layout(hovermode="x unified", bargap=0.3)
        theme.plot(fig, 360)

    with t_drivers:
        g = groups.sort_values("log_effect")
        lim = max(float(np.abs(g["log_effect"]).max()) * 1.3, 0.3)
        ticks = [m for m in (0.25, 0.5, 1, 2, 4, 8) if abs(np.log(m)) <= lim]
        fig = go.Figure(go.Bar(
            x=g["log_effect"], y=[T(x) for x in g["group"]], orientation="h", marker_line_width=0,
            marker_color=[TIERS["High"].color if v > 0 else theme.ACCENT for v in g["log_effect"]],
            text=[f"×{num(m, '.2f')}" for m in g["multiplier"]], textposition="outside", cliponaxis=False,
            textfont=dict(size=12, color=theme.INK_2),
            hovertemplate="%{y}: %{text}<extra></extra>"))
        fig.update_layout(margin=dict(l=0, r=48, t=8, b=0), bargap=0.45,
                          xaxis=dict(range=[-lim, lim], tickvals=np.log(ticks), ticktext=[f"×{num(m, 'g')}" for m in ticks],
                                     zeroline=True, zerolinecolor=theme.INK_2, zerolinewidth=1.5),
                          yaxis=dict(showgrid=False, tickfont=dict(size=13, color=theme.INK_2)))
        theme.plot(fig, 320)
        st.html('<p class="m-note">' + T("TreeSHAP values from the model, shown as multipliers on expected cases. "
                                         "Orange pushes risk up, teal holds it down.") + '</p>')

theme.gap()

@st.fragment
def what_if() -> None:
    """Runs on its own: moving a slider re-runs only this card, not the whole page."""
    with st.container(key="card-whatif"):
        theme.card_title(T("What if the weather changed?"),
                         T("Adjust the last two weeks of weather. Moshari rebuilds the lag features and runs the model again."))
        with st.container(key="tray-sliders"):
            w1, w2, w3 = st.columns(3)
            rain = w1.slider(T("Rainfall"), 0.0, 3.0, 1.0, 0.1, format="×%.1f", key="wi_rain")
            temp = w2.slider(T("Temperature"), -4.0, 4.0, 0.0, 0.5, format="%+.1f °C", key="wi_temp")
            hum = w3.slider(T("Humidity"), -20.0, 20.0, 0.0, 1.0, format=T("%+.0f pts"), key="wi_hum")
        scenario = Scenario(rain, temp, hum)
        if scenario.is_baseline:
            st.html('<p class="m-note">' + T("Move a slider to compare a scenario with the forecast above.") + '</p>')
        else:
            alt = svc.ward_outlook(ward, issue_date, scenario)
            steps = []
            for (_, a), (_, b) in zip(alt.iterrows(), outlook.iterrows()):
                d = a["expected_cases"] - b["expected_cases"]
                color = TIERS["Critical"].color if d > 0.05 else (theme.ACCENT if d < -0.05 else theme.MUTED)
                steps.append(
                    f'<div class="m-step"><div class="h">{T("In {n} weeks", n=a["horizon"])}</div>'
                    f'<div class="c" style="color:{TIERS[a["tier"]].ink}">{num(a["expected_cases"], ".1f")}</div>'
                    f'<div class="r">' + T('<span style="color:{color};font-weight:700">{d:+.1f}</span> vs forecast, {tier}',
                                            color=color, d=d, tier=tr(a["tier"])) + '</div></div>'
                )
            st.html(f'<div class="m-steps">{"".join(steps)}</div>')


what_if()

theme.footer(svc.bundle.metadata)
