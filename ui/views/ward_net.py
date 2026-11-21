"""Overview: every ward's risk for one week, and where to send teams first."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from moshari import config as C
from moshari.data import corporation_of, ward_label
from moshari.risk import TIERS
from ui import components, state, theme

issue_date, horizon, cities = st.session_state["_controls"]
svc = state.service()
key = state.data_key()
policy = state.policy()
fc = state.forecast_all(key, issue_date, horizon, cities, policy)
thr = svc.bundle.tier_thresholds
target = issue_date + pd.Timedelta(weeks=horizon)
CORP_ORDER = components.CORP_ORDER
fc["corp"] = fc[C.WARD_COL].map(corporation_of)

theme.header(
    "Overview",
    f"Dengue outlook for the week of {state.fmt_week(target)}",
    [("event", "Issued", state.fmt_week(issue_date)), ("schedule", "Horizon", f"{horizon} weeks")],
)

n_high = int((fc["tier_idx"] >= 2).sum())
n_on = int(fc["alert"].sum())
n_early = int((fc["alert"] & (fc["tier_idx"] < 2)).sum())
n_crit = int((fc["tier_idx"] == 3).sum())
n_up = int(((fc["upside_tier"] == "Critical") & (fc["tier"] != "Critical")).sum())
on_time = state.metrics().get("horizons", {}).get(str(horizon), {}).get("alert_on_time", {}).get(policy)
caught = f", alerted in time for {on_time:.0%} of season onsets in testing" if on_time is not None else ""
by_city = fc.groupby(C.CITY_COL)["tier_idx"].apply(lambda s: (s >= 2).mean()).sort_values(ascending=False)
crit_color = theme.TIER_COLORS["Critical"] if n_crit else theme.INK
theme.stats([
    ("notifications_active", "Wards on alert", f"{n_on}<small> / {len(fc)} wards</small>",
     f"{n_high} expected high, {n_early} early alerts"),
    ("e911_emergency", "Critical", f"<span style='color:{crit_color}'>{n_crit}</span><small> wards</small>",
     f"{n_up} more could tip into critical"),
    ("groups", "Expected cases", f"{fc['expected_cases'].sum():,.0f}", f"across {len(fc)} wards that week"),
    ("location_city", "Hardest-hit city", by_city.index[0] if len(by_city) else "None",
     f"{by_city.iloc[0]:.0%} of its wards high or above" if len(by_city) else ""),
])


with st.container(key="card-net"):
    theme.card_title("Risk across wards",
                     "Each tile is a ward, showing expected dengue cases that week. Hover a tile for its 80% range.",
                     f"{len(fc)} wards")
    t_week, t_season = st.tabs(["This week", "Whole season"])
    with t_week:
        early_label = None if policy == "Standard" else f"Early alert ({policy.lower()} rule{caught})"
        st.html(components.ward_net(fc, thr, early_label))

    with t_season:
        dates = pd.DatetimeIndex(svc.issue_dates)
        lo, hi_ = pd.Timestamp(f"{target.year}-04-20"), pd.Timestamp(f"{target.year}-11-30")
        tgt = dates + pd.Timedelta(weeks=horizon)
        window = dates[(tgt >= lo) & (tgt <= hi_)]
        tl = state.forecast_timeline(key, tuple(window), horizon, cities)
        tl["o"] = tl[C.WARD_COL].map(lambda w: CORP_ORDER.index(corporation_of(w)) if corporation_of(w) in CORP_ORDER else 9)
        tl = tl.sort_values(["o", C.WARD_COL], ascending=[False, False])
        z = tl.pivot_table(index=C.WARD_COL, columns="target_date", values="tier_idx", sort=False)
        cases = tl.pivot_table(index=C.WARD_COL, columns="target_date", values="expected_cases", sort=False)
        scale = []
        for i, n in enumerate(C.TIER_NAMES):
            scale += [[i / 4, theme.TIER_COLORS[n]], [(i + 1) / 4, theme.TIER_COLORS[n]]]
        fig = go.Figure(go.Heatmap(
            z=z.to_numpy(), x=z.columns, y=[ward_label(w) for w in z.index], customdata=cases.to_numpy(),
            colorscale=scale, zmin=-0.5, zmax=3.5, xgap=2, ygap=2, showscale=False,
            hovertemplate="%{y}<br>Week of %{x|%d %b}<br>%{customdata:.1f} expected cases<extra></extra>"))
        fig.add_vrect(x0=target - pd.Timedelta(days=3.5), x1=target + pd.Timedelta(days=3.5),
                      line=dict(color=theme.INK, width=2), fillcolor="rgba(0,0,0,0)")
        fig.update_layout(margin=dict(l=0, r=0, t=8, b=0),
                          yaxis=dict(showticklabels=False, showgrid=False), xaxis=dict(tickformat="%b"))
        st.html(f'<p class="m-note">{horizon}-week forecasts for every week of the {target.year} season, one row per ward '
                f'with Dhaka North at the top. The outlined column is the week shown in "This week".</p>')
        theme.plot(fig, max(420, 10 * len(z) + 60))

theme.gap()

left, right = st.columns([7, 5])
with left:
    with st.container(key="card-dispatch"):
        theme.card_title("Send teams here first",
                         f"Ranked by alert priority under the {policy.lower()} rule, with the recommended response.",
                         "Top 6")
        rows = []
        for i, r in enumerate(fc.head(6).itertuples(), 1):
            early = (' <span class="m-badge" style="box-shadow:inset 0 0 0 1.5px '
                     f'{theme.TIER_COLORS["Critical"]};color:{theme.TIER_COLORS["Critical"]}">Early alert</span>'
                     if r.alert and r.tier_idx < 2 else "")
            rows.append(
                f'<div class="m-row"><div class="n">{i}</div>'
                f'<div><div class="w">{ward_label(r.ward_id)} {theme.badge(r.tier)}{early}</div>'
                f'<div class="c">{r.city}, {TIERS[r.tier].action.lower()}</div></div>'
                f'<div class="e">{r.expected_cases:.1f}<small>{r.lower_80:.0f} to {r.upper_80:.0f} cases</small></div></div>'
            )
        st.html(f'<div class="m-list">{"".join(rows)}</div>')
        c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
        pick = c1.selectbox("Open a ward", list(fc[C.WARD_COL]), format_func=ward_label, key="net_pick")
        if c2.button("View forecast", width="stretch", type="primary", icon=":material/arrow_forward:"):
            st.session_state["ward"] = pick
            st.switch_page("ui/views/ward_forecast.py")

with right:
    with st.container(key="card-mix"):
        theme.card_title("Risk by city corporation", "Number of wards in each tier.")
        mix = fc.groupby(C.CITY_COL)["tier"].value_counts().unstack(fill_value=0).reindex(columns=C.TIER_NAMES, fill_value=0)
        mix = mix.loc[mix.sum(axis=1).sort_values().index]
        fig = go.Figure([
            go.Bar(y=mix.index, x=mix[n], name=n, orientation="h", marker_color=theme.TIER_COLORS[n],
                   marker_line_width=0, hovertemplate=f"%{{y}}: %{{x}} {n.lower()}<extra></extra>")
            for n in C.TIER_NAMES
        ])
        fig.update_layout(barmode="stack", bargap=0.5, showlegend=False, margin=dict(l=0, r=0, t=8, b=0),
                          xaxis=dict(showgrid=True, gridcolor=theme.LINE, dtick=5), yaxis=dict(showgrid=False))
        theme.plot(fig, 380)

theme.footer(svc.bundle.metadata)
