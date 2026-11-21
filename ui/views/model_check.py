"""Model accuracy: chronological hold-out validation, in plain view."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from moshari import config as C
from moshari.data import ward_label
from ui import state, theme

issue_date, horizon, cities = st.session_state["_controls"]
m = state.metrics()
bt = state.backtest()
if not m or bt.empty:
    st.warning("No validation results yet. Run `python scripts/train.py` to train and evaluate the model.")
    st.stop()

hm = m["horizons"][str(horizon)]
BASE_NAMES = {"persistence": "Same as this week", "seasonal_naive": "Same week last year",
              "climatology": "Seasonal average"}
SOFT = {"Same as this week": "#D6CDBB", "Same week last year": "#C1B6A0", "Seasonal average": "#A69B84"}

theme.header(
    "Model accuracy",
    "Tested on 2024 and 2025, two seasons the model never saw while training",
    [("schedule", "Horizon", f"{horizon} weeks"), ("dataset", "Test set", f"{hm['n_test']:,} ward-weeks")],
)
theme.stats([
    ("straighten", "Average miss", f"{hm['model']['mae']:.2f}<small> cases</small>", "per ward per week (MAE)"),
    ("trending_down", "Error vs simple rules", f"−{hm['mae_improvement_vs_best_baseline']:.0%}",
     "against the best baseline"),
    ("target", "Right risk tier", f"{hm['model']['tier_accuracy']:.0%}", f"{hm['model']['tier_within_one']:.0%} within one tier"),
    ("fact_check", "80% range hit rate", f"{hm['interval_coverage_80']:.0%}", "of actual counts inside the range"),
])

with st.container(key="card-replay"):
    b = bt[bt["horizon"] == horizon]
    if cities:
        b = b[b["city"].isin(cities)]
    head, pick = st.columns([5, 2], vertical_alignment="bottom")
    with head:
        theme.card_title("Replay of 2024 and 2025",
                         f"What Moshari forecast {horizon} weeks ahead, against what was actually reported.")
    opts = ["All selected wards"] + sorted(b["ward_id"].unique())
    who = pick.selectbox("Show", opts, format_func=lambda w: w if w == opts[0] else ward_label(w),
                         key="mc_who", label_visibility="collapsed")
    if who == opts[0]:
        d = b.groupby("target_date")[["actual", "expected"]].sum().reset_index()
        traces = []
    else:
        d = b[b["ward_id"] == who].sort_values("target_date")
        traces = [
            go.Scatter(x=d["target_date"], y=d["upper_80"], line=dict(width=0), showlegend=False, hoverinfo="skip"),
            go.Scatter(x=d["target_date"], y=d["lower_80"], line=dict(width=0), fill="tonexty",
                       fillcolor="rgba(14,115,105,0.14)", name="80% range", hoverinfo="skip"),
        ]
    traces += [
        go.Scatter(x=d["target_date"], y=d["actual"], name="Reported", line=dict(color=theme.INK, width=2.2),
                   hovertemplate="%{y:.0f} reported<extra></extra>"),
        go.Scatter(x=d["target_date"], y=d["expected"], name="Forecast", line=dict(color=theme.ACCENT, width=2.4, dash="dot"),
                   hovertemplate="%{y:.1f} forecast<extra></extra>"),
    ]
    fig = go.Figure(traces)
    fig.update_layout(hovermode="x unified")
    theme.plot(fig, 340)

theme.gap()

with st.container(key="card-alerts"):
    pols = hm.get("alert_policies", {})
    on_time = hm.get("alert_on_time", {})
    current = state.policy()
    theme.card_title(
        "Alert sensitivity",
        "When should a ward go on alert? Missing an outbreak costs more than an extra larviciding visit, "
        "so Moshari defaults to the cautious rule, which raises the alarm before the season's first high-risk "
        "week far more often. Change it under Forecast settings.",
        f"Using: {current}",
    )
    if pols:
        a, b = st.columns([3, 2])
        with a:
            names = list(pols)
            fig = go.Figure([
                go.Bar(x=names, y=[pols[n]["recall"] for n in names], name="High-risk weeks caught (recall)",
                       marker_color=theme.ACCENT, marker_line_width=0,
                       text=[f"{pols[n]['recall']:.0%}" for n in names], textposition="outside", cliponaxis=False),
                go.Bar(x=names, y=[pols[n]["precision"] for n in names], name="Alerts that were real (precision)",
                       marker_color="#C1B6A0", marker_line_width=0,
                       text=[f"{pols[n]['precision']:.0%}" for n in names], textposition="outside", cliponaxis=False),
            ])
            fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.08, margin=dict(l=0, r=0, t=40, b=0),
                              yaxis=dict(range=[0, 1.12], tickformat=".0%"))
            theme.plot(fig, 300)
        with b:
            rows = []
            for n, v in pols.items():
                on = " on" if n == current else ""
                rows.append(
                    f'<div class="m-row{on}"><div class="n">{theme.icon("notifications_active" if n == current else "notifications")}</div>'
                    f'<div><div class="w">{n}</div><div class="c">{v["missed"]:,} high-risk weeks missed, '
                    f'{v["false_alarms"]:,} false alarms</div></div>'
                    f'<div class="e">{on_time.get(n, float("nan")):.0%}<small>alerted in time</small></div></div>'
                )
            st.html('<div class="m-list">' + "".join(rows) + "</div>")
        st.html(f'<p class="m-note">Counted over {hm["n_test"]:,} ward-weeks in 2024 and 2025 at a {horizon}-week horizon. '
                "<b>Alerted in time</b> is the share of ward-seasons where an alert was already out by the first week "
                "cases actually reached High. The risk tier always shows the best estimate; the alert rule only decides "
                "who goes on the watch list.</p>")

theme.gap()

left, right = st.columns(2)
with left:
    with st.container(key="card-baselines"):
        theme.card_title("Against simple rules", "Average miss in cases per ward per week. Lower is better.")
        rows = []
        for h, v in m["horizons"].items():
            rows.append({"h": f"{h} weeks", "who": "Moshari", "mae": v["model"]["mae"]})
            for k, bv in v["baselines"].items():
                rows.append({"h": f"{h} weeks", "who": BASE_NAMES[k], "mae": bv["mae"]})
        df = pd.DataFrame(rows)
        fig = go.Figure([go.Bar(x=g["h"], y=g["mae"], name=w, marker_color=SOFT.get(w, theme.ACCENT),
                                marker_line_width=0, hovertemplate=f"{w}: %{{y:.2f}}<extra></extra>")
                         for w, g in df.groupby("who", sort=False)])
        fig.update_layout(barmode="group", bargap=0.32, bargroupgap=0.1, margin=dict(l=0, r=0, t=40, b=0))
        theme.plot(fig, 330)

with right:
    with st.container(key="card-lag"):
        theme.card_title("Why lagged rain", "How closely cases follow rainfall from k weeks earlier, within each ward.")
        lc = pd.DataFrame(m["lag_correlations"])
        peak = lc.loc[lc["correlation"].idxmax()]
        fig = go.Figure(go.Bar(
            x=lc["lag_weeks"], y=lc["correlation"], marker_line_width=0,
            marker_color=[theme.ACCENT if k == peak["lag_weeks"] else "#D6CDBB" for k in lc["lag_weeks"]],
            hovertemplate="Rain %{x} weeks earlier: r = %{y:.2f}<extra></extra>"))
        fig.add_annotation(x=peak["lag_weeks"], y=peak["correlation"], text=f"Peak at {int(peak['lag_weeks'])} weeks",
                           showarrow=False, yshift=16, font=dict(color=theme.ACCENT, size=13))
        fig.update_layout(bargap=0.3, margin=dict(l=0, r=0, t=40, b=0),
                          xaxis=dict(dtick=1, title="Weeks between rain and cases"), yaxis=dict(range=[0, 0.9]))
        theme.plot(fig, 330)

theme.gap()

with st.container(key="card-details"):
    theme.card_title("Details", "How the data was split, how tiers compare, and which signals matter most.")
    t1, t2, t3 = st.tabs(["Validation split", "Risk tiers", "Top signals"])
    with t1:
        st.html(
            """<div class="m-steps">
              <div class="m-step"><div class="h">Train</div><div class="c" style="font-size:22px">2016 to 2022</div>
                <div class="r">Fit the models</div></div>
              <div class="m-step"><div class="h">Validate</div><div class="c" style="font-size:22px">2023</div>
                <div class="r">Pick boosting rounds, calibrate the 80% range</div></div>
              <div class="m-step on"><div class="h">Test</div><div class="c" style="font-size:22px">2024 and 2025</div>
                <div class="r">Scored once, never used for training</div></div>
            </div>
            <p class="m-note" style="margin-top:16px">Split by the week being forecast, never at random, so no future
            information leaks into training. The shipped model is refit on 2016 to 2023.</p>"""
        )
    with t2:
        cm = pd.DataFrame(hm["confusion"]).reindex(index=C.TIER_NAMES, columns=C.TIER_NAMES).fillna(0)
        z = cm.T.to_numpy()
        share = z / np.maximum(z.sum(axis=1, keepdims=True), 1)
        fig = go.Figure(go.Heatmap(
            z=share, x=list(C.TIER_NAMES), y=list(C.TIER_NAMES), customdata=z, showscale=False, xgap=6, ygap=6,
            colorscale=[[0, theme.BASE_HI], [1, theme.ACCENT]],
            text=[[f"{int(v):,}" for v in row] for row in z], texttemplate="%{text}", textfont=dict(size=13),
            hovertemplate="Actual %{y}, forecast %{x}: %{customdata:,.0f} ward-weeks<extra></extra>"))
        fig.update_layout(margin=dict(l=0, r=0, t=8, b=0), xaxis=dict(title="Forecast tier"),
                          yaxis=dict(title="Actual tier", autorange="reversed", showgrid=False))
        theme.plot(fig, 320)
        st.html(f'<p class="m-note">High-risk weeks caught: <b>{hm["model"]["alert_recall"]:.0%}</b>. '
                f'Of the weeks flagged high or above, <b>{hm["model"]["alert_precision"]:.0%}</b> really were.</p>')
    with t3:
        imp = pd.Series(m["feature_importance"][str(horizon)]).head(8)[::-1]
        labels = m.get("feature_labels", {})
        fig = go.Figure(go.Bar(x=imp.to_numpy(), y=[labels.get(f, f) for f in imp.index], orientation="h",
                               marker_color=theme.ACCENT, marker_line_width=0,
                               hovertemplate="%{y}: %{x:.1%}<extra></extra>"))
        fig.update_layout(bargap=0.4, margin=dict(l=0, r=0, t=8, b=0),
                          xaxis=dict(tickformat=".0%", showgrid=True, gridcolor=theme.LINE),
                          yaxis=dict(showgrid=False, tickfont=dict(size=13, color=theme.INK_2)))
        theme.plot(fig, 320)

theme.footer(state.service().bundle.metadata)
