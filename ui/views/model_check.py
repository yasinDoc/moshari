"""How accurate is it? Chronological hold-out validation, in plain view."""

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
    st.warning("No validation results found. Run `python scripts/train.py` to train and evaluate the model.")
    st.stop()

hm = m["horizons"][str(horizon)]
meta = m["metadata"]
best_base = min(hm["baselines"], key=lambda k: hm["baselines"][k]["mae"])
BASE_NAMES = {"persistence": "Same as this week", "seasonal_naive": "Same week last year",
              "climatology": "Ward's seasonal average"}

st.html(f'<p class="m-kicker">Tested on 2024 and 2025, which the model never saw during training</p>')
st.html(
    f'<p class="m-lede">Moshari\'s {horizon}-week forecasts miss by <b>{hm["model"]["mae"]:.2f} cases</b> '
    f'per ward per week on average, <b>{hm["mae_improvement_vs_best_baseline"]:.0%} closer</b> than the best '
    f'simple rule, and put {hm["model"]["tier_accuracy"]:.0%} of ward-weeks in the right risk tier.</p>'
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Mean absolute error", f"{hm['model']['mae']:.2f}", help="Average miss, in cases per ward per week.")
k2.metric("Root mean squared error", f"{hm['model']['rmse']:.2f}", help="Penalises big misses more.")
k3.metric("High-risk weeks caught", f"{hm['model']['alert_recall']:.0%}",
          help="Of the ward-weeks that turned out High or Critical, the share Moshari flagged as High or Critical.")
k4.metric("80% range coverage", f"{hm['interval_coverage_80']:.0%}",
          help="Share of actual counts that fell inside the 80% range. Calibrated on 2023 with conformal prediction.")

# --------------------------------------------------------------------------- timeline split
st.subheader("How the data was split")
fig = go.Figure()
spans = [("Train", "2016-01-04", C.TRAIN_END, theme.LAGOON),
         ("Validate", C.TRAIN_END, C.VALID_END, theme.RAIN),
         ("Test (hold-out)", C.VALID_END, "2025-12-29", theme.TIER_COLORS["High"])]
for name, a, b, color in spans:
    fig.add_shape(type="rect", x0=a, x1=b, y0=0, y1=1, fillcolor=color, opacity=0.85, line_width=0)
    fig.add_annotation(x=pd.Timestamp(a) + (pd.Timestamp(b) - pd.Timestamp(a)) / 2, y=0.5, text=name,
                       showarrow=False, font=dict(color="white", size=13))
fig.update_layout(height=90, margin=dict(l=8, r=8, t=4, b=8), yaxis=dict(visible=False, range=[0, 1]),
                  xaxis=dict(range=["2016-01-01", "2026-01-05"], showgrid=False, type="date"))
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "staticPlot": True})
st.caption("Split by the week being forecast, never at random, so no future information leaks into training. "
           "2023 picks the number of boosting rounds and calibrates the 80% range; the shipped model is then "
           f"refit on 2016 to 2023. Model trained through {meta['trained_through']}.")

# --------------------------------------------------------------------------- error vs baselines
c1, c2 = st.columns(2, gap="large")
with c1:
    st.subheader("Error against simple rules")
    rows = []
    for h, v in m["horizons"].items():
        rows.append({"h": f"{h} weeks", "who": "Moshari", "mae": v["model"]["mae"]})
        for b, bv in v["baselines"].items():
            rows.append({"h": f"{h} weeks", "who": BASE_NAMES[b], "mae": bv["mae"]})
    df = pd.DataFrame(rows)
    colors = {"Moshari": theme.LAGOON, "Same as this week": "#B9C6C0",
              "Same week last year": "#9AABA4", "Ward's seasonal average": "#7C8F88"}
    fig = go.Figure([go.Bar(x=d["h"], y=d["mae"], name=who, marker_color=colors[who],
                            text=d["mae"].round(2), textposition="outside", cliponaxis=False)
                     for who, d in df.groupby("who", sort=False)])
    fig.update_layout(barmode="group", height=340, yaxis_title="Mean absolute error (cases)")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with c2:
    st.subheader("Risk tiers: forecast against actual")
    cm = pd.DataFrame(hm["confusion"]).reindex(index=C.TIER_NAMES, columns=C.TIER_NAMES).fillna(0)
    # stored as {forecast: {actual: n}}
    z = cm.T.to_numpy()
    share = z / np.maximum(z.sum(axis=1, keepdims=True), 1)
    fig = go.Figure(go.Heatmap(
        z=share, x=list(C.TIER_NAMES), y=list(C.TIER_NAMES), customdata=z,
        colorscale=[[0, "#FFFFFF"], [1, theme.LAGOON]], showscale=False, xgap=2, ygap=2,
        text=[[f"{int(v)}" for v in row] for row in z], texttemplate="%{text}",
        hovertemplate="Actual %{y}, forecast %{x}: %{customdata:.0f} ward-weeks<extra></extra>"))
    fig.update_layout(height=340, xaxis_title="Forecast tier", yaxis_title="Actual tier",
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# --------------------------------------------------------------------------- backtest
st.subheader("Replay of the hold-out years")
b = bt[bt["horizon"] == horizon]
if cities:
    b = b[b["city"].isin(cities)]
wards = ["All selected wards"] + sorted(b["ward_id"].unique())
who = st.selectbox("Show", wards, format_func=lambda w: w if w == wards[0] else ward_label(w))
if who == wards[0]:
    agg = b.groupby("target_date")[["actual", "expected"]].sum().reset_index()
    fig = go.Figure([
        go.Scatter(x=agg["target_date"], y=agg["actual"], name="Reported", line=dict(color=theme.INK, width=2)),
        go.Scatter(x=agg["target_date"], y=agg["expected"], name=f"Forecast {horizon} weeks earlier",
                   line=dict(color=theme.LAGOON, width=2.4, dash="dot")),
    ])
else:
    w = b[b["ward_id"] == who].sort_values("target_date")
    fig = go.Figure([
        go.Scatter(x=w["target_date"], y=w["upper_80"], line=dict(width=0), showlegend=False, hoverinfo="skip"),
        go.Scatter(x=w["target_date"], y=w["lower_80"], line=dict(width=0), fill="tonexty",
                   fillcolor="rgba(15,110,106,0.16)", name="80% range", hoverinfo="skip"),
        go.Scatter(x=w["target_date"], y=w["actual"], name="Reported", line=dict(color=theme.INK, width=2)),
        go.Scatter(x=w["target_date"], y=w["expected"], name=f"Forecast {horizon} weeks earlier",
                   line=dict(color=theme.LAGOON, width=2.4, dash="dot")),
    ])
fig.update_layout(height=360, hovermode="x unified", yaxis_title="Cases per week")
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# --------------------------------------------------------------------------- evidence
c1, c2 = st.columns(2, gap="large")
with c1:
    st.subheader("Evidence for the breeding clock")
    lc = pd.DataFrame(m["lag_correlations"])
    peak = lc.loc[lc["correlation"].idxmax()]
    fig = go.Figure(go.Bar(
        x=lc["lag_weeks"], y=lc["correlation"],
        marker_color=[theme.LAGOON if k == peak["lag_weeks"] else "#B9C6C0" for k in lc["lag_weeks"]],
        hovertemplate="Rain %{x} weeks earlier: r = %{y:.2f}<extra></extra>"))
    fig.update_layout(height=300, xaxis_title="Weeks between rainfall and cases", yaxis_title="Correlation",
                      xaxis=dict(dtick=1))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption(f"Within each ward, cases track rainfall from {int(peak['lag_weeks'])} weeks earlier most closely "
               f"(r = {peak['correlation']:.2f}), not same-week rain. That's why every forecast is built on lagged rain.")
with c2:
    st.subheader("Signals the model leans on")
    imp = pd.Series(m["feature_importance"][str(horizon)]).head(10)[::-1]
    labels = m.get("feature_labels", {})
    fig = go.Figure(go.Bar(x=imp.to_numpy(), y=[labels.get(f, f) for f in imp.index], orientation="h",
                           marker_color=theme.LAGOON, hovertemplate="%{y}: %{x:.1%} of total gain<extra></extra>"))
    fig.update_layout(height=300, xaxis=dict(tickformat=".0%", title="Share of total split gain"),
                      yaxis=dict(showgrid=False))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with st.expander("All metrics by horizon"):
    rows = []
    for h, v in m["horizons"].items():
        rows.append({
            "Horizon": f"{h} weeks", "MAE": v["model"]["mae"], "RMSE": v["model"]["rmse"],
            "Tier accuracy": v["model"]["tier_accuracy"], "Within one tier": v["model"]["tier_within_one"],
            "Macro F1 (tiers)": v["model"]["tier_macro_f1"], "Alert recall": v["model"]["alert_recall"],
            "Alert precision": v["model"]["alert_precision"], "80% coverage": v["interval_coverage_80"],
            "Test ward-weeks": v["n_test"],
        })
    st.dataframe(pd.DataFrame(rows).round(3), hide_index=True, use_container_width=True)
