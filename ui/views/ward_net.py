"""Overview: every ward's risk for one week, and where to send teams first."""

from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from moshari import allocation as A
from moshari import briefing as B
from moshari import config as C
from moshari.data import corporation_of
from moshari.risk import TIERS
from ui import components, i18n, state, theme

T, tr = i18n.t, i18n.tr

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
    T("Overview"),
    T("Dengue outlook for the week of {week}", week=state.fmt_week(target)),
    [("event", T("Issued"), state.fmt_week(issue_date)), ("schedule", T("Horizon"), T("{n} weeks", n=horizon))],
)
POL = T(policy) if i18n.is_bn() else policy.lower()   # "cautious rule" / "সতর্ক নিয়ম"



# --------------------------------------------------------------------------- supply alert strip
@st.cache_data(show_spinner=False, max_entries=128)
def supply_alerts(key: str, issue_date, horizon: int, cities: tuple, policy: str) -> dict:
    """Shortages at the Resources / Hospital beds defaults, so the officer sees them here first."""
    f = state.forecast_all(key, issue_date, horizon, cities, policy)
    alloc = A.allocate(f, state.service().wards, B.OVERVIEW_STOCK, B.OVERVIEW_CREWS)
    return B.supply_alerts(alloc, B.beds_routing(state.service(), f, B.OVERVIEW_SURGE).ward_summary)


alerts = supply_alerts(key, issue_date, horizon, cities, policy)
parts = B.alert_parts(alerts)
if i18n.is_bn():
    _bn_alert = {"saline_wards": "{n} wards short on saline", "kits_wards": "{n} wards short on test kits",
                 "crews_short": "{n} crews short", "out_of_beds_wards": "{n} wards out of beds"}
    parts = [(T(_bn_alert[k], n=int(alerts[k])), kind) for k, (_, kind) in
             zip([k for k in _bn_alert if int(alerts.get(k, 0))], parts)]
scenario = T("At {stock:.0%} stock and {crews} crews.", stock=B.OVERVIEW_STOCK, crews=B.OVERVIEW_CREWS)
if parts:
    shown = '<span class="sep"> · </span>'.join(f'<b>{html.escape(t)}</b>' for t, _ in parts)
    st.html(f'<div class="m-alert bad">{theme.icon("report")}<div><div class="t">{shown}</div>'
            f'<div class="s">{scenario}{T(" Open Resources or Hospital beds to change the plan, or the Weekly briefing for a one-page summary.")}</div></div></div>')
else:
    st.html(f'<div class="m-alert ok">{theme.icon("check_circle")}<div><div class="t"><b>{T(B.alert_text(alerts))}</b>'
            f'</div><div class="s">{scenario}{T(" No ward is short of saline, test kits, crews or beds.")}</div></div></div>')
with st.container(key="alert-links", horizontal=True):
    kinds = {k for _, k in parts}
    if kinds & {"supplies", "crews"}:
        st.page_link("ui/views/resources.py", label=T("Resources"), icon=":material/inventory_2:")
    if "beds" in kinds:
        st.page_link("ui/views/hospital.py", label=T("Hospital beds"), icon=":material/local_hospital:")
    st.page_link("ui/views/briefing.py", label=T("Weekly briefing"), icon=":material/summarize:")

n_high = int((fc["tier_idx"] >= 2).sum())
n_on = int(fc["alert"].sum())
n_early = int((fc["alert"] & (fc["tier_idx"] < 2)).sum())
n_crit = int((fc["tier_idx"] == 3).sum())
n_cw = int((fc["crit_watch"] | (fc["tier_idx"] == 3)).sum()) if "crit_watch" in fc else n_crit
on_time = state.metrics().get("horizons", {}).get(str(horizon), {}).get("alert_on_time", {}).get(policy)
caught = T(", alerted in time for {p:.0%} of season onsets in testing", p=on_time) if on_time is not None else ""
by_city = fc.groupby(C.CITY_COL)["tier_idx"].apply(lambda s: (s >= 2).mean()).sort_values(ascending=False)
crit_color = theme.TIER_COLORS["Critical"] if n_cw else theme.INK
theme.stats([
    ("warning", T("Expected high risk"), T("{a}<small> / {n} wards</small>", a=n_high, n=len(fc)),
     (T("{n} more on watch ({policy} rule)", n=n_early, policy=POL) if n_early else T("need vector control this week"))),
    ("e911_emergency", T("Critical watch"), f"<span style='color:{crit_color}'>{i18n.num(n_cw)}</span><small>{T(' wards')}</small>",
     T("{a} expected critical, {b} more likely enough to prepare", a=n_crit, b=n_cw - n_crit if n_cw > n_crit else 0)),
    ("groups", T("Expected cases"), i18n.num(fc['expected_cases'].sum(), ",.0f"), T("across {n} wards that week", n=len(fc))),
    ("location_city", T("Hardest-hit city"), tr(by_city.index[0]) if len(by_city) else T("None"),
     T("{p:.0%} of its wards high or above", p=by_city.iloc[0]) if len(by_city) else ""),
])


with st.container(key="card-net"):
    theme.card_title(T("Risk across wards"),
                     T("Each tile is a ward, showing expected dengue cases that week. Hover for details, click to open its forecast."),
                     T("{n} wards", n=len(fc)))
    t_week, t_season = st.tabs([T("This week"), T("Whole season")])
    with t_week:
        early_label = None if policy == "Standard" else T("Early alert ({policy} rule{caught})", policy=POL, caught=caught)
        st.html(components.ward_net(fc, thr, early_label, link=state.link_params(issue_date, horizon, cities)))

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
            z=z.to_numpy(), x=z.columns, y=[i18n.ward(w) for w in z.index], customdata=cases.to_numpy(),
            colorscale=scale, zmin=-0.5, zmax=3.5, xgap=2, ygap=2, showscale=False,
            hovertemplate="%{y}<br>Week of %{x|%d %b}<br>%{customdata:.1f} expected cases<extra></extra>"))
        fig.add_vrect(x0=target - pd.Timedelta(days=3.5), x1=target + pd.Timedelta(days=3.5),
                      line=dict(color=theme.INK, width=2), fillcolor="rgba(0,0,0,0)")
        # Divider lines between city corporations, so the 60 rows read as 5 groups.
        corps = [corporation_of(w) for w in z.index]
        for i in range(1, len(corps)):
            if corps[i] != corps[i - 1]:
                fig.add_hline(y=i - 0.5, line=dict(color=theme.BASE, width=5))
        fig.update_layout(margin=dict(l=0, r=0, t=8, b=0), xaxis=dict(tickformat="%b", side="top"),
                          yaxis=dict(showgrid=False, tickfont=dict(size=10, color=theme.INK_2), ticksuffix="  "))
        st.html(f'<p class="m-note">' + T('{h}-week forecasts for every week of the {year} season, one row per ward '
                'grouped by city corporation. The outlined column is the week shown in "This week". '
                'Hover any cell for its expected cases.', h=horizon, year=target.year) + '</p>')
        theme.plot(fig, max(420, 15 * len(z) + 60))

theme.gap()

left, right = st.columns([7, 5])
with left:
    with st.container(key="card-dispatch"):
        theme.card_title(T("Send teams here first"),
                         T("Ranked by alert priority under the {policy} rule, with the recommended response.", policy=POL),
                         T("Top {n}", n=6))
        rows = []
        for i, r in enumerate(fc.head(6).itertuples(), 1):
            early = (' <span class="m-badge" style="box-shadow:inset 0 0 0 1.5px '
                     f'{theme.TIER_COLORS["Critical"]};color:{theme.TIER_COLORS["Critical"]}">{T("Early alert")}</span>'
                     if r.alert and r.tier_idx < 2 else "")
            rows.append(
                f'<div class="m-row"><div class="n">{i18n.num(i)}</div>'
                f'<div><div class="w">{i18n.ward(r.ward_id)} {theme.badge(r.tier)}{early}</div>'
                f'<div class="c">{tr(r.city)}, {T(TIERS[r.tier].action).lower()}</div></div>'
                f'<div class="e">{i18n.num(r.expected_cases, ".1f")}<small>{T("{lo:.0f} to {hi:.0f} cases", lo=r.lower_80, hi=r.upper_80)}</small></div></div>'
            )
        st.html(f'<div class="m-list">{"".join(rows)}</div>')
        c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
        pick = c1.selectbox(T("Open a ward"), list(fc[C.WARD_COL]), format_func=i18n.bound(i18n.ward), key="net_pick")
        if c2.button(T("View forecast"), width="stretch", type="primary", icon=":material/arrow_forward:"):
            st.session_state["ward"] = pick
            st.switch_page("ui/views/ward_forecast.py")

with right:
    with st.container(key="card-mix"):
        theme.card_title(T("Risk by city corporation"), T("Number of wards in each tier."))
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
