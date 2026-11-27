"""Model accuracy: chronological hold-out validation, in plain view."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from moshari import config as C
from moshari.data import ward_label
from ui import i18n, state, theme

T, tr, num, BN = i18n.t, i18n.tr, i18n.num, i18n.is_bn()

issue_date, horizon, cities = st.session_state["_controls"]
m = state.metrics()
bt = state.backtest()
if not m or bt.empty:
    st.warning(T("No validation results yet. Run `python scripts/train.py` to train and evaluate the model."))
    st.stop()

hm = m["horizons"][str(horizon)]
BASE_NAMES = {"persistence": "Same as this week", "seasonal_naive": "Same week last year",
              "climatology": "Seasonal average"}
SOFT = {"Same as this week": "#D6CDBB", "Same week last year": "#C1B6A0", "Seasonal average": "#A69B84"}

theme.header(
    T("Model accuracy"),
    T("Tested on 2024 and 2025, two seasons the model never saw while training"),
    [("schedule", T("Horizon"), T("{n} weeks", n=horizon)), ("dataset", T("Test set"), T("{n:,} ward-weeks", n=hm['n_test']))],
)
theme.stats([
    ("straighten", T("Average miss"), f"{num(hm['model']['mae'], '.2f')}<small>{T(' cases')}</small>",
     T("per ward per week (MAE)")),
    ("trending_down", T("Error vs simple rules"), f"−{num(hm['mae_improvement_vs_best_baseline'], '.0%')}",
     T("against the best baseline")),
    ("target", T("Right risk tier"), num(hm['model']['tier_accuracy'], '.0%'),
     T("{p:.0%} within one tier", p=hm['model']['tier_within_one'])),
    ("fact_check", T("80% range hit rate"), num(hm['interval_coverage_80'], '.0%'), T("of actual counts inside the range")),
])

@st.fragment
def replay() -> None:
    """Choosing a ward re-runs only this chart."""
    with st.container(key="card-replay"):
        b = bt[bt["horizon"] == horizon]
        if cities:
            b = b[b["city"].isin(cities)]
        head, pick = st.columns([5, 2], vertical_alignment="bottom")
        with head:
            theme.card_title(T("Replay of 2024 and 2025"),
                             T("What Moshari forecast {h} weeks ahead, against what was actually reported.", h=horizon))
        opts = ["All selected wards"] + sorted(b["ward_id"].unique())
        who = pick.selectbox(T("Show"), opts, key="mc_who", label_visibility="collapsed",
                             format_func=i18n.bound(lambda w, lg: i18n.core.t(w, lg) if w == opts[0] else i18n.core.ward(w, lg)))
        if who == opts[0]:
            d = b.groupby("target_date")[["actual", "expected"]].sum().reset_index()
            traces = []
        else:
            d = b[b["ward_id"] == who].sort_values("target_date")
            traces = [
                go.Scatter(x=d["target_date"], y=d["upper_80"], line=dict(width=0), showlegend=False, hoverinfo="skip"),
                go.Scatter(x=d["target_date"], y=d["lower_80"], line=dict(width=0), fill="tonexty",
                           fillcolor="rgba(14,115,105,0.14)", name=T("80% range"), hoverinfo="skip"),
            ]
        traces += [
            go.Scatter(x=d["target_date"], y=d["actual"], name=T("Reported"), line=dict(color=theme.INK, width=2.2),
                       hovertemplate="%{y:.0f} reported<extra></extra>"),
            go.Scatter(x=d["target_date"], y=d["expected"], name=T("Forecast"), line=dict(color=theme.ACCENT, width=2.4, dash="dot"),
                       hovertemplate="%{y:.1f} forecast<extra></extra>"),
        ]
        fig = go.Figure(traces)
        fig.update_layout(hovermode="x unified")
        theme.plot(fig, 340)


replay()

theme.gap()

with st.container(key="card-alerts"):
    pols = hm.get("alert_policies", {})
    on_time = hm.get("alert_on_time", {})
    current = state.policy()
    theme.card_title(
        T("Alert sensitivity"),
        T("When should a ward go on alert? Missing an outbreak costs more than an extra larviciding visit, "
          "so Moshari defaults to the cautious rule, which raises the alarm before the season's first high-risk "
          "week far more often. Change it under Forecast settings."),
        T("Using: {policy}", policy=T(current)),
    )
    if pols:
        a, b = st.columns([3, 2])
        with a:
            names = list(pols)
            fig = go.Figure([
                go.Bar(x=names, y=[pols[n]["recall"] for n in names], name=T("High-risk weeks caught (recall)"),
                       marker_color=theme.ACCENT, marker_line_width=0,
                       text=[f"{pols[n]['recall']:.0%}" for n in names], textposition="outside", cliponaxis=False),
                go.Bar(x=names, y=[pols[n]["precision"] for n in names], name=T("Alerts that were real (precision)"),
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
                    f'<div><div class="w">{T(n)}</div><div class="c">'
                    f'{T("{m:,} high-risk weeks missed, {f:,} false alarms", m=v["missed"], f=v["false_alarms"])}</div></div>'
                    f'<div class="e">{num(on_time.get(n, float("nan")), ".0%")}<small>{T("alerted in time")}</small></div></div>'
                )
            st.html('<div class="m-list">' + "".join(rows) + "</div>")
        st.html('<p class="m-note">' + T("Counted over {n:,} ward-weeks in 2024 and 2025 at a {h}-week horizon. "
                "<b>Alerted in time</b> is the share of ward-seasons where an alert was already out by the first week "
                "cases actually reached High. The risk tier always shows the best estimate; the alert rule only decides "
                "who goes on the watch list.", n=hm["n_test"], h=horizon) + "</p>")

theme.gap()

pl, pr = st.columns(2)
with pl:
    with st.container(key="card-prob"):
        theme.card_title(T("Catching outbreak weeks"),
                         T("Expected cases are an average, so they smooth over peaks. Separate probability models "
                           "estimate the chance of reaching Critical, which catches far more outbreak weeks."))
        rows = []
        for h, v in m["horizons"].items():
            pc = v.get("probability", {}).get("Critical")
            if pc:
                rows.append({"h": T("{n} weeks", n=int(h)), "By expected cases": pc["recall_expected_rule"],
                             "By probability": pc["recall"], "auc": pc["auc"], "prec": pc["precision"]})
        if rows:
            df = pd.DataFrame(rows)
            fig = go.Figure([
                go.Bar(x=df["h"], y=df["By expected cases"], name=T("By expected cases"), marker_color="#C1B6A0",
                       marker_line_width=0, text=[f"{v:.0%}" for v in df["By expected cases"]], textposition="outside",
                       cliponaxis=False),
                go.Bar(x=df["h"], y=df["By probability"], name=T("By probability"), marker_color=theme.TIER_COLORS["Critical"],
                       marker_line_width=0, text=[f"{v:.0%}" for v in df["By probability"]], textposition="outside",
                       cliponaxis=False),
            ])
            fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.08, margin=dict(l=0, r=0, t=40, b=0),
                              yaxis=dict(range=[0, 1.05], tickformat=".0%", title=T("Critical weeks caught")))
            theme.plot(fig, 300)
            st.html('<p class="m-note">' + T("Ranking quality (AUC): {list}. The trade-off is more false alarms: about "
                    "{p:.0%} of Critical-watch flags at 3 weeks stay below Critical.",
                    list=", ".join(f'{r["h"]} {num(r["auc"], ".2f")}' for r in rows), p=1 - rows[1]["prec"]) + '</p>')

with pr:
    with st.container(key="card-rainfc"):
        theme.card_title(T("Adding a rain forecast"),
                         T("Cases 3 to 4 weeks out depend on rain that hasn't fallen yet. Live mode feeds in "
                           "Open-Meteo's 14-day forecast; this is the gain, tested with realistic forecast error."))
        rows = []
        for h, v in m["horizons"].items():
            fa = v.get("forecast_assisted")
            if fa:
                rows.append({"h": T("{n} weeks", n=int(h)), **fa})
        if rows:
            df = pd.DataFrame(rows)
            series = [("Seasonal average", "mae_seasonal_average", "#D6CDBB"),
                      ("Moshari", "mae_without_forecast", "#A69B84"),
                      ("+ rain forecast", "mae_realistic_forecast", theme.ACCENT)]
            fig = go.Figure([go.Bar(x=df["h"], y=df[c], name=T(n), marker_color=col, marker_line_width=0,
                                    hovertemplate=T("{name}: %{{y:.2f}}", name=T(n)) + "<extra></extra>")
                             for n, c, col in series])
            fig.update_layout(barmode="group", bargap=0.32, bargroupgap=0.08, margin=dict(l=0, r=0, t=40, b=0),
                              yaxis=dict(title=T("Average miss (cases)")))
            theme.plot(fig, 300)
            r4 = df.iloc[-1]
            st.html('<p class="m-note">' + T("At 4 weeks the rain forecast cuts the average miss from {a:.2f} to {b:.2f} "
                    "cases ({p:.0%} lower); a perfect forecast would reach {c:.2f}. Forecast error was simulated as "
                    "±65% on rain.", a=r4["mae_without_forecast"], b=r4["mae_realistic_forecast"],
                    p=1 - r4["mae_realistic_forecast"] / r4["mae_without_forecast"], c=r4["mae_perfect_forecast"]) + '</p>')

theme.gap()

left, right = st.columns(2)
with left:
    with st.container(key="card-baselines"):
        theme.card_title(T("Against simple rules"), T("Average miss in cases per ward per week. Lower is better."))
        rows = []
        for h, v in m["horizons"].items():
            rows.append({"h": T("{n} weeks", n=int(h)), "who": "Moshari", "mae": v["model"]["mae"]})
            for k, bv in v["baselines"].items():
                rows.append({"h": T("{n} weeks", n=int(h)), "who": BASE_NAMES[k], "mae": bv["mae"]})
        df = pd.DataFrame(rows)
        fig = go.Figure([go.Bar(x=g["h"], y=g["mae"], name=T(w), marker_color=SOFT.get(w, theme.ACCENT),
                                marker_line_width=0, hovertemplate=T("{name}: %{{y:.2f}}", name=T(w)) + "<extra></extra>")
                         for w, g in df.groupby("who", sort=False)])
        fig.update_layout(barmode="group", bargap=0.32, bargroupgap=0.1, margin=dict(l=0, r=0, t=40, b=0))
        theme.plot(fig, 330)

with right:
    with st.container(key="card-lag"):
        theme.card_title(T("Why lagged rain"), T("How closely cases follow rainfall from k weeks earlier, within each ward."))
        lc = pd.DataFrame(m["lag_correlations"])
        peak = lc.loc[lc["correlation"].idxmax()]
        fig = go.Figure(go.Bar(
            x=lc["lag_weeks"], y=lc["correlation"], marker_line_width=0,
            marker_color=[theme.ACCENT if k == peak["lag_weeks"] else "#D6CDBB" for k in lc["lag_weeks"]],
            hovertemplate="Rain %{x} weeks earlier: r = %{y:.2f}<extra></extra>"))
        fig.add_annotation(x=peak["lag_weeks"], y=peak["correlation"], text=T("Peak at {n} weeks", n=int(peak['lag_weeks'])),
                           showarrow=False, yshift=16, font=dict(color=theme.ACCENT, size=13))
        fig.update_layout(bargap=0.3, margin=dict(l=0, r=0, t=40, b=0),
                          xaxis=dict(dtick=1, title=T("Weeks between rain and cases")), yaxis=dict(range=[0, 0.9]))
        theme.plot(fig, 330)

theme.gap()

with st.container(key="card-details"):
    theme.card_title(T("Details"), T("How the data was split, how tiers compare, and which signals matter most."))
    t1, t2, t3 = st.tabs([T("Validation split"), T("Risk tiers"), T("Top signals")])
    with t1:
        split_note = T("Split by the week being forecast, never at random, so no future\n"
                       "            information leaks into training. The shipped model is refit on 2016 to 2023.")
        st.html(
            f"""<div class="m-steps">
              <div class="m-step"><div class="h">{T("Train")}</div><div class="c" style="font-size:22px">{T("2016 to 2022")}</div>
                <div class="r">{T("Fit the models")}</div></div>
              <div class="m-step"><div class="h">{T("Validate")}</div><div class="c" style="font-size:22px">{num(2023)}</div>
                <div class="r">{T("Pick boosting rounds, calibrate the 80% range")}</div></div>
              <div class="m-step on"><div class="h">{T("Test")}</div><div class="c" style="font-size:22px">{T("2024 and 2025")}</div>
                <div class="r">{T("Scored once, never used for training")}</div></div>
            </div>
            <p class="m-note" style="margin-top:16px">{split_note}</p>"""
        )
    with t2:
        cm = pd.DataFrame(hm["confusion"]).reindex(index=C.TIER_NAMES, columns=C.TIER_NAMES).fillna(0)
        z = cm.T.to_numpy()
        share = z / np.maximum(z.sum(axis=1, keepdims=True), 1)
        fig = go.Figure(go.Heatmap(
            z=share, x=[tr(n) for n in C.TIER_NAMES], y=[tr(n) for n in C.TIER_NAMES], customdata=z, showscale=False, xgap=6, ygap=6,
            colorscale=[[0, theme.BASE_HI], [1, theme.ACCENT]],
            text=[[num(int(v), ",") for v in row] for row in z], texttemplate="%{text}", textfont=dict(size=13),
            hovertemplate="Actual %{y}, forecast %{x}: %{customdata:,.0f} ward-weeks<extra></extra>"))
        fig.update_layout(margin=dict(l=0, r=0, t=8, b=0), xaxis=dict(title=T("Forecast tier")),
                          yaxis=dict(title=T("Actual tier"), autorange="reversed", showgrid=False))
        theme.plot(fig, 320)
        st.html('<p class="m-note">' + T("High-risk weeks caught: <b>{r:.0%}</b>. Of the weeks flagged high or above, "
                "<b>{p:.0%}</b> really were.", r=hm["model"]["alert_recall"], p=hm["model"]["alert_precision"]) + '</p>')
    with t3:
        imp = pd.Series(m["feature_importance"][str(horizon)]).head(8)[::-1]
        labels = m.get("feature_labels", {})
        fig = go.Figure(go.Bar(x=imp.to_numpy(), y=[T(labels.get(f, f)) for f in imp.index], orientation="h",
                               marker_color=theme.ACCENT, marker_line_width=0,
                               hovertemplate="%{y}: %{x:.1%}<extra></extra>"))
        fig.update_layout(bargap=0.4, margin=dict(l=0, r=0, t=8, b=0),
                          xaxis=dict(tickformat=".0%", showgrid=True, gridcolor=theme.LINE),
                          yaxis=dict(showgrid=False, tickfont=dict(size=13, color=theme.INK_2)))
        theme.plot(fig, 320)

theme.footer(state.service().bundle.metadata)
