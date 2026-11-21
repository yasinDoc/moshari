"""Ward risk net: every ward's outlook at a glance, as cells of a net."""

from __future__ import annotations

import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from moshari import config as C
from moshari.data import corporation_of, ward_label
from moshari.risk import TIERS
from ui import state, theme

issue_date, horizon, cities = st.session_state["_controls"]
svc = state.service()
key = state.data_key()
fc = state.forecast_all(key, issue_date, horizon, cities)
thresholds = svc.bundle.tier_thresholds
target = issue_date + pd.Timedelta(weeks=horizon)

# --------------------------------------------------------------------------- lede
alert = fc[fc["tier_idx"] >= 2]
n_crit = int((fc["tier_idx"] == 3).sum())
first = [ward_label(w) for w in alert[C.WARD_COL].head(3)]

st.html(f'<p class="m-kicker">Outlook for the week of {state.fmt_week(target)}, '
        f'issued {state.fmt_week(issue_date)}</p>')
if len(alert):
    crit = f", <b>{n_crit} critical</b>" if n_crit else ""
    lede = (f"<b>{len(alert)} of {len(fc)} wards</b> are heading for high dengue risk{crit} "
            f"in {horizon} weeks. Start vector control in {', '.join(first[:-1])}"
            f"{' and ' if len(first) > 1 else ''}{first[-1]} first.")
else:
    med = int((fc["tier_idx"] == 1).sum())
    lede = (f"No ward is expected to reach high risk in {horizon} weeks. "
            f"<b>{med} ward{'s' if med != 1 else ''}</b> need routine source reduction.")
st.html(f'<p class="m-lede">{lede}</p>')

# --------------------------------------------------------------------------- the net
CORP_ORDER = ["DNCC", "DSCC", "CCC", "GCC", "NCC"]


def cell(r: pd.Series) -> str:
    t = TIERS[r["tier"]]
    strength = float(np.clip(r["expected_cases"] / thresholds[2], 0, 1))
    if r["tier_idx"] == 3:
        bg = t.color
    else:
        alpha = 0.10 + 0.62 * strength
        rgb = tuple(int(t.color[i:i + 2], 16) for i in (1, 3, 5))
        bg = f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{alpha:.2f})"
    up = r["upside_tier"] == "Critical" and r["tier"] != "Critical"
    tip = (f"{ward_label(r[C.WARD_COL])}: {r['tier']} risk, {r['expected_cases']:.1f} expected cases "
           f"(80% range {r['lower_80']:.1f} to {r['upper_80']:.1f})")
    if not np.isnan(r["actual"]):
        tip += f". Actually reported: {r['actual']:.0f}"
    num = r[C.WARD_COL].rsplit("_", 1)[-1]
    return (f'<div class="m-cell t{r["tier_idx"]}{" up" if up else ""}" style="background:{bg}" '
            f'title="{html.escape(tip)}" aria-label="{html.escape(tip)}">'
            f'<span class="w">Ward {num}</span><span class="v">{r["expected_cases"]:.1f}</span></div>')


fc["corp"] = fc[C.WARD_COL].map(corporation_of)
blocks = []
for corp in CORP_ORDER:
    sub = fc[fc["corp"] == corp].sort_values(C.WARD_COL)
    if sub.empty:
        continue
    hi = int((sub["tier_idx"] >= 2).sum())
    blocks.append(
        f'<section class="m-corp"><h4>{C.CITY_CORPORATIONS.get(corp, corp)}</h4>'
        f'<p>{len(sub)} wards, {hi} at high risk or above</p>'
        f'<div class="m-mesh">{"".join(cell(r) for _, r in sub.iterrows())}</div></section>'
    )
legend = "".join(
    f'<span><span class="sw" style="background:{t.color}"></span>{n} '
    f'{"below " + str(thresholds[0]) if n == "Low" else ("≥ " + str(thresholds[C.TIER_NAMES.index(n) - 1]))}</span>'
    for n, t in TIERS.items()
)
legend += ('<span><span class="sw" style="background:#fff;border:1.5px solid '
           f'{TIERS["Critical"].color};border-radius:50%"></span>could reach critical (upper 80% bound)</span>')
st.html(f'<div class="m-net">{"".join(blocks)}</div>'
        f'<div class="m-legend">Expected cases per ward that week. {legend}</div>')

# --------------------------------------------------------------------------- priority list
st.subheader("Where to send teams first")
st.caption("Ranked by expected cases. Select a ward to open its full forecast.")
table = pd.DataFrame(
    {
        "Ward": fc[C.WARD_COL].map(ward_label),
        "City": fc[C.CITY_COL],
        "Risk": fc["tier"],
        "Expected cases": fc["expected_cases"].round(1),
        "80% range": [f"{a:.1f} to {b:.1f}" for a, b in zip(fc["lower_80"], fc["upper_80"])],
        "Rain 2–4 wks ago (mm)": fc["rain_breeding_window"].round(0),
        "Cases this week": fc["cases_lag_0w"].astype(int),
        "Reported (replay)": fc["actual"],
        "Response": fc["tier"].map(lambda t: TIERS[t].action),
    }
)
sel = st.dataframe(
    table,
    hide_index=True,
    use_container_width=True,
    height=min(38 + 35 * len(table), 420),
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Expected cases": st.column_config.ProgressColumn(
            "Expected cases", format="%.1f", min_value=0.0, max_value=float(max(fc["upper_80"].max(), 1))
        ),
        "Reported (replay)": st.column_config.NumberColumn(
            "Reported (replay)", format="%d", help="What actually happened that week, when the data has it."
        ),
    },
)
if sel and sel.selection.rows:
    st.session_state["ward"] = fc.iloc[sel.selection.rows[0]][C.WARD_COL]
    st.switch_page("ui/views/ward_forecast.py")

# --------------------------------------------------------------------------- season heatmap
st.subheader(f"The {target.year} season, ward by ward")
st.caption(f"Each cell is the forecast Moshari made {horizon} weeks before that week. "
           "The outlined column is the week shown in the net above.")
dates = pd.DatetimeIndex(svc.issue_dates)
season_targets = pd.date_range(f"{target.year}-04-20", f"{target.year}-11-30", freq="7D")
window = dates[((dates + pd.Timedelta(weeks=horizon)) >= season_targets[0])
               & ((dates + pd.Timedelta(weeks=horizon)) <= season_targets[-1])]
tl = state.forecast_timeline(key, tuple(window), horizon, cities)
tl["corp_order"] = tl[C.WARD_COL].map(lambda w: CORP_ORDER.index(corporation_of(w)) if corporation_of(w) in CORP_ORDER else 9)
tl = tl.sort_values(["corp_order", C.WARD_COL], ascending=[False, False])
z = tl.pivot_table(index=C.WARD_COL, columns="target_date", values="tier_idx", sort=False)
cases = tl.pivot_table(index=C.WARD_COL, columns="target_date", values="expected_cases", sort=False)
colors = [theme.TIER_COLORS[n] for n in theme.TIER_ORDER]
scale = []
for i, c in enumerate(colors):
    scale += [[i / 4, c], [(i + 1) / 4, c]]
fig = go.Figure(
    go.Heatmap(
        z=z.to_numpy(),
        x=z.columns,
        y=[ward_label(w) for w in z.index],
        customdata=cases.to_numpy(),
        colorscale=scale,
        zmin=-0.5,
        zmax=3.5,
        xgap=1.5,
        ygap=1.5,
        showscale=False,
        hovertemplate="%{y}<br>Week of %{x|%d %b %Y}<br>%{customdata:.1f} expected cases<extra></extra>",
    )
)
fig.add_vrect(x0=target - pd.Timedelta(days=3.5), x1=target + pd.Timedelta(days=3.5),
              line=dict(color=theme.INK, width=2), fillcolor="rgba(0,0,0,0)")
fig.update_layout(height=max(320, 14 * len(z) + 80), margin=dict(l=8, r=8, t=10, b=8),
                  yaxis=dict(tickfont=dict(size=10), showgrid=False),
                  xaxis=dict(showgrid=False, tickformat="%d %b"))
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
