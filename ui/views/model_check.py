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

theme.header(
    "Model accuracy",
    "Tested on 2024 and 2025, two seasons the model never saw while training",
    [("Showing", f"{horizon}-week forecasts")],
)
theme.stats([
    ("Average miss", f"{hm['model']['mae']:.2f}", "cases per ward per week (MAE)"),
    ("Better than simple rules", f"{hm['mae_improvement_vs_best_baseline']:.0%}", "lower error than the best baseline"),
    ("Right risk tier", f"{hm['model']['tier_accuracy']:.0%}", f"{hm['model']['tier_within_one']:.0%} within one tier"),
    ("80% range hit rate", f"{hm['interval_coverage_80']:.0%}", "of actual counts fell inside the range"),
])

# --------------------------------------------------------------------------- replay
with st.container(key="card-replay"):
    theme.card_title("Replay of 2024 and 2025",
                     f"What Moshari forecast {horizon} weeks ahead, against what was actually reported.")
    b = bt[bt["horizon"] == horizon]
    if cities:
        b = b[b["city"].isin(cities)]
    opts = ["All selected wards"] + sorted(b["ward_id"].unique())
    c1, _ = st.columns([2, 3])
    who = c1.selectbox("Show", opts, format_func=lambda w: w if w == opts[0] else ward_label(w), key="mc_who")
    if who == opts[0]:
        d = b.groupby("target_date")[["actual", "expected"]].sum().reset_index()
        traces = []
    else:
        d = b[b["ward_id"] == who].sort_values("target_date")
        traces = [
            go.Scatter(x=d["target_date"], y=d["upper_80"], line=dict(width=0), showlegend=False, hoverinfo="skip"),
            go.Scatter(x=d["target_date"], y=d["lower_80"], line=dict(width=0), fill="tonexty",
                       fillcolor="rgba(17,117,109,0.15)", name="80% range", hoverinfo="skip"),
        ]
    traces += [
        go.Scatter(x=d["target_date"], y=d["actual"], name="Reported", line=dict(color=theme.INK, width=2.2)),
        go.Scatter(x=d["target_date"], y=d["expected"], name="Forecast", line=dict(color=theme.ACCENT, width=2.4, dash="dot")),
    ]
    fig = go.Figure(traces)
    fig.update_layout(height=330, hovermode="x unified", margin=dict(l=4, r=4, t=30, b=4))
    st.plotly_chart(fig, use_container_width=True, config=theme.PLOT_CONFIG, theme=None)

st.html('<div style="height:1.4rem"></div>')

left, right = st.columns(2, gap="large")
with left:
    with st.container(key="card-baselines"):
        theme.card_title("Against simple rules", "Average miss in cases per ward per week. Lower is better.")
        rows = []
        for h, v in m["horizons"].items():
            rows.append({"h": f"{h} wk", "who": "Moshari", "mae": v["model"]["mae"]})
            for k, bv in v["baselines"].items():
                rows.append({"h": f"{h} wk", "who": BASE_NAMES[k], "mae": bv["mae"]})
        df = pd.DataFrame(rows)
        colors = {"Moshari": theme.ACCENT, "Same as this week": "#CFC6B4",
                  "Same week last year": "#B9AF9B", "Seasonal average": "#9F957F"}
        fig = go.Figure([go.Bar(x=g["h"], y=g["mae"], name=w, marker_color=colors[w], marker_line_width=0,
                                hovertemplate=f"{w}: %{{y:.2f}}<extra></extra>")
                         for w, g in df.groupby("who", sort=False)])
        fig.update_layout(barmode="group", height=320, bargap=0.3, bargroupgap=0.08,
                          legend=dict(y=-0.18, yanchor="top"), margin=dict(l=4, r=4, t=10, b=4))
        st.plotly_chart(fig, use_container_width=True, config=theme.PLOT_CONFIG, theme=None)

with right:
    with st.container(key="card-lag"):
        theme.card_title("Why lagged rain", "How closely cases follow rainfall from k weeks earlier, within each ward.")
        lc = pd.DataFrame(m["lag_correlations"])
        peak = lc.loc[lc["correlation"].idxmax()]
        fig = go.Figure(go.Bar(
            x=lc["lag_weeks"], y=lc["correlation"], marker_line_width=0,
            marker_color=[theme.ACCENT if k == peak["lag_weeks"] else "#CFC6B4" for k in lc["lag_weeks"]],
            hovertemplate="Rain %{x} weeks earlier: r = %{y:.2f}<extra></extra>"))
        fig.add_annotation(x=peak["lag_weeks"], y=peak["correlation"], text=f"peak at {int(peak['lag_weeks'])} weeks",
                           showarrow=False, yshift=14, font=dict(color=theme.ACCENT, size=12))
        fig.update_layout(height=320, xaxis=dict(dtick=1, title="weeks between rain and cases"),
                          yaxis=dict(range=[0, 0.9]), margin=dict(l=4, r=4, t=10, b=4))
        st.plotly_chart(fig, use_container_width=True, config=theme.PLOT_CONFIG, theme=None)

st.html('<div style="height:1.4rem"></div>')

with st.container(key="card-details"):
    theme.card_title("Details", "How the data was split, how tiers compare and which signals matter most.")
    t1, t2, t3 = st.tabs(["Validation split", "Risk tiers", "Top signals"])
    with t1:
        st.html(
            f"""<div class="m-steps">
              <div class="m-step"><div class="h">Train</div><div class="c" style="font-size:1.25rem">2016 to 2022</div>
                <div class="r">fit the models</div></div>
              <div class="m-step"><div class="h">Validate</div><div class="c" style="font-size:1.25rem">2023</div>
                <div class="r">pick boosting rounds, calibrate the 80% range</div></div>
              <div class="m-step on"><div class="h">Test</div><div class="c" style="font-size:1.25rem">2024 and 2025</div>
                <div class="r">scored once, never used for training</div></div>
            </div>
            <p class="m-sub" style="margin-top:1rem">Split by the week being forecast, never at random, so no future
            information leaks into training. The shipped model is refit on 2016 to 2023.</p>"""
        )
    with t2:
        cm = pd.DataFrame(hm["confusion"]).reindex(index=C.TIER_NAMES, columns=C.TIER_NAMES).fillna(0)
        z = cm.T.to_numpy()
        share = z / np.maximum(z.sum(axis=1, keepdims=True), 1)
        fig = go.Figure(go.Heatmap(
            z=share, x=list(C.TIER_NAMES), y=list(C.TIER_NAMES), customdata=z, showscale=False, xgap=4, ygap=4,
            colorscale=[[0, theme.BASE_HI], [1, theme.ACCENT]],
            text=[[f"{int(v):,}" for v in row] for row in z], texttemplate="%{text}",
            hovertemplate="Actual %{y}, forecast %{x}: %{customdata:,.0f} ward-weeks<extra></extra>"))
        fig.update_layout(height=320, xaxis=dict(title="forecast tier", side="bottom"),
                          yaxis=dict(title="actual tier", autorange="reversed"), margin=dict(l=4, r=4, t=10, b=4))
        st.plotly_chart(fig, use_container_width=True, config=theme.PLOT_CONFIG, theme=None)
        st.caption(f"High-risk weeks caught: {hm['model']['alert_recall']:.0%}. "
                   f"Of the weeks flagged high or above, {hm['model']['alert_precision']:.0%} really were.")
    with t3:
        imp = pd.Series(m["feature_importance"][str(horizon)]).head(8)[::-1]
        labels = m.get("feature_labels", {})
        fig = go.Figure(go.Bar(x=imp.to_numpy(), y=[labels.get(f, f) for f in imp.index], orientation="h",
                               marker_color=theme.ACCENT, marker_line_width=0,
                               hovertemplate="%{y}: %{x:.1%}<extra></extra>"))
        fig.update_layout(height=320, xaxis=dict(tickformat=".0%", showgrid=True, gridcolor=theme.LINE),
                          yaxis=dict(showgrid=False), margin=dict(l=4, r=4, t=10, b=4))
        st.plotly_chart(fig, use_container_width=True, config=theme.PLOT_CONFIG, theme=None)
