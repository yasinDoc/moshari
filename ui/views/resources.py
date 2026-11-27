"""Resources: supplies and spraying crews under scarcity (module 1)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from moshari import allocation as A
from moshari import config as C
from moshari.data import ward_label
from ui import state, theme

issue_date, horizon, cities = st.session_state["_controls"]
svc = state.service()
key = state.data_key()
policy = state.policy()
target = issue_date + pd.Timedelta(weeks=horizon)


@st.cache_data(show_spinner=False, max_entries=128)
def run_allocation(key: str, issue_date, horizon: int, cities: tuple, policy: str,
                   stock_pct: float, crews: int, plan_for: str) -> pd.DataFrame:
    fc = state.forecast_all(key, issue_date, horizon, cities, policy)
    return A.allocate(fc, state.service().wards, stock_pct, crews, plan_for)


theme.header(
    "Resources",
    f"Supplies and spraying crews for the week of {state.fmt_week(target)}",
    [("event", "Issued", state.fmt_week(issue_date)), ("schedule", "Horizon", f"{horizon} weeks")],
)

with st.container(key="card-controls"):
    theme.card_title("Scarcity controls",
                     "Set how much regional stock is available and how many spraying crews you have. "
                     "Allocation re-runs instantly, serving the highest-risk, most crowded wards first.")
    c1, c2, c3 = st.columns([5, 3, 4], vertical_alignment="bottom")
    stock = c1.slider("Available regional stock", 30, 100, 70, 5, format="%d%%", key="res_stock",
                      help="Share of total ward demand that is actually in the regional store.")
    crews = c2.number_input("Total spraying crews", 0, 300, 40, 5, key="res_crews")
    plan = c3.segmented_control("Plan for", ["Expected cases", "Upper 80% range"], default="Expected cases",
                                key="res_plan", width="stretch")
plan_for = "upper" if plan == "Upper 80% range" else "expected"

alloc = run_allocation(key, issue_date, horizon, cities, policy, stock / 100, int(crews), plan_for)
summary = A.summarize(alloc, int(crews))
res = summary["resources"]

theme.gap()


def fill_tile(icon: str, label: str, r: dict) -> tuple:
    colour = theme.TIER_COLORS["Critical"] if r["short"] else theme.INK
    return (icon, label.capitalize(),
            f"<span style='color:{colour}'>{r['fill']:.0%}</span><small> filled</small>",
            f"{r['allocated']:,} of {r['needed']:,} needed" + (f", {r['short']:,} short" if r["short"] else ""))


crit = summary["critical_deficits"]
theme.stats([
    fill_tile("water_drop", "Saline bags", res["saline bags"]),
    fill_tile("biotech", "Test kits", res["test kits"]),
    fill_tile("bed", "Hospital beds", res["beds"]),
    ("warning", "Wards in supply deficit",
     f"<span style='color:{theme.TIER_COLORS['Critical'] if summary['deficit_wards'] else theme.INK}'>"
     f"{summary['deficit_wards']}</span><small> / {len(alloc)}</small>",
     f"{crit} of them High or Critical" if summary["deficit_wards"] else "every ward fully supplied"),
])

left, right = st.columns([6, 5])
with left:
    with st.container(key="card-deficits"):
        short = alloc[alloc["deficit_flag"]]
        theme.card_title("Critical supply deficits",
                         "Wards that can't get 100% of their demand at this stock level, highest priority first.",
                         f"{len(short)} wards")
        if short.empty:
            st.html(f'<div class="m-act" style="margin:0"><div class="h">{theme.icon("check_circle")}'
                    'Every ward is fully supplied</div><div class="b">Lower the stock slider to see how '
                    'shortages would be shared out.</div></div>')
        else:
            rows = []
            for r in short.head(7).itertuples():
                rows.append(
                    f'<div class="m-row"><div class="n">{r.priority_rank}</div>'
                    f'<div><div class="w">{ward_label(r.ward_id)} {theme.badge(r.tier)}</div>'
                    f'<div class="c" style="color:{theme.TIER_COLORS["Critical"]}">{r.deficit_note}</div></div>'
                    f'<div class="e">{r.fill_rate:.0%}<small>supplied</small></div></div>'
                )
            st.html('<div class="m-list">' + "".join(rows) + "</div>")
            if len(short) > 7:
                st.html(f'<p class="m-note">{len(short) - 7} more wards short; see the full table below.</p>')

with right:
    with st.container(key="card-crews"):
        cr = summary["crews"]
        theme.card_title("Spraying crews",
                         f"High and Critical wards need one crew per {A.CASES_PER_CREW:g} expected cases. "
                         "Every such ward gets one crew first, then the rest go by priority.")
        st.html(
            f"""<div class="m-prof" style="grid-template-columns:repeat(3,1fr)">
                  <div><div class="k">Needed</div><div class="v">{cr['needed']}</div></div>
                  <div><div class="k">Assigned</div><div class="v">{cr['assigned']}</div></div>
                  <div><div class="k">Still needed</div><div class="v" style="color:{theme.TIER_COLORS['Critical'] if cr['unmet'] else theme.INK}">{cr['unmet']}</div></div>
                </div>"""
        )
        by_city = alloc.groupby(C.CITY_COL)[["crews_assigned", "crews_needed"]].sum().sort_values("crews_needed")
        fig = go.Figure([
            go.Bar(y=by_city.index, x=by_city["crews_assigned"], name="Assigned", orientation="h",
                   marker_color=theme.ACCENT, marker_line_width=0),
            go.Bar(y=by_city.index, x=(by_city["crews_needed"] - by_city["crews_assigned"]).clip(lower=0),
                   name="Still needed", orientation="h", marker_color="#D6CDBB", marker_line_width=0),
        ])
        fig.update_layout(barmode="stack", bargap=0.45, margin=dict(l=0, r=0, t=30, b=0),
                          xaxis=dict(showgrid=True, gridcolor=theme.LINE), yaxis=dict(showgrid=False))
        theme.plot(fig, 230)

theme.gap()

with st.container(key="card-table"):
    ratios = A.demand_ratios()
    theme.card_title(
        "Allocation by ward",
        f"Demand per {'expected' if plan_for == 'expected' else 'upper-range'} case: "
        f"{ratios.ratios['saline_bags_needed']:.2f} saline bags, {ratios.ratios['diagnostic_kits_needed']:.2f} "
        f"test kits, {ratios.ratios['hospital_beds_required']:.2f} beds ({ratios.source}, R² ≥ "
        f"{min(ratios.r2.values()) if ratios.r2 else 0:.2f}). Rounded up so demand is never understated.",
    )
    table = pd.DataFrame({
        "Rank": alloc["priority_rank"],
        "Ward": alloc[C.WARD_COL].map(ward_label),
        "City": alloc[C.CITY_COL],
        "Risk": alloc["tier"],
        "Priority": alloc["priority_score"],
        "Cases": alloc["planned_cases"].round(1),
        "Saline": [f"{a} / {n}" for a, n in zip(alloc["saline_bags_allocated"], alloc["saline_bags_needed"])],
        "Kits": [f"{a} / {n}" for a, n in zip(alloc["diagnostic_kits_allocated"], alloc["diagnostic_kits_needed"])],
        "Beds": [f"{a} / {n}" for a, n in zip(alloc["hospital_beds_allocated"], alloc["hospital_beds_required"])],
        "Crews": [f"{a} / {n}" if n else "–" for a, n in zip(alloc["crews_assigned"], alloc["crews_needed"])],
        "Supplied": alloc["fill_rate"],
        "Status": alloc["deficit_note"],
    })
    st.dataframe(
        table, hide_index=True, width="stretch", height=420,
        column_config={
            "Supplied": st.column_config.ProgressColumn("Supplied", format="percent", min_value=0.0, max_value=1.0),
            "Priority": st.column_config.NumberColumn("Priority", format="%.1f",
                                                      help="Risk (tier and chance of High) × relative density"),
        },
    )
    export = alloc[[C.WARD_COL, C.CITY_COL, "tier", "planned_cases", "priority_rank", "priority_score",
                    *[c for trio in A.RESOURCES for c in trio[:2]], "crews_needed", "crews_assigned",
                    "deficit_flag", "deficit_note"]]
    st.download_button("Download allocation (CSV)", export.to_csv(index=False).encode(),
                       file_name=f"moshari_allocation_{issue_date:%Y%m%d}_h{horizon}_stock{stock}.csv",
                       mime="text/csv", icon=":material/download:")

theme.footer(svc.bundle.metadata)
