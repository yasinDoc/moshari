"""Simulator: what spraying crews buy over the next 2–4 weeks (module 3)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from moshari import config as C
from moshari import simulation as S
from moshari.data import ward_label
from ui import state, theme

issue_date, horizon, cities = st.session_state["_controls"]
svc = state.service()
key = state.data_key()


@st.cache_data(show_spinner="Simulating every ward at 0 to 6 crews…", max_entries=32)
def effect_table(key: str, issue_date, cities: tuple, per_crew: float, cap: float) -> S.EffectTable:
    return S.build_effect_table(state.service(), issue_date, per_crew, cap, cities=list(cities) or None)


theme.header(
    "Simulator",
    "Deploy larvicide and fogging crews, then see the cases, beds and saline they save 2 to 4 weeks out",
    [("event", "Issued", state.fmt_week(issue_date)), ("groups", "Wards", f"{60 if not cities else 'filtered'}")],
)

with st.container(key="card-sim-controls"):
    theme.card_title("Crews and assumptions",
                     "Each crew removes a share of a ward's remaining breeding sites, so extra crews in the same "
                     "ward help less. The forecast models then re-run on the reduced breeding signal.")
    c1, c2, c3, c4 = st.columns([3, 4, 3, 4], vertical_alignment="bottom")
    total = c1.number_input("Crews available", 0, 200, 30, 5, key="sim_total")
    per_crew = c2.slider("Effect per crew", 10, 35, 20, 1, format="%d%%", key="sim_eff",
                         help="Share of remaining breeding pressure one crew removes. Capped at 75% per ward.")
    max_pw = c3.number_input("Max crews per ward", 1, S.MAX_CREWS_PER_WARD, 4, 1, key="sim_maxpw")
    mode = c4.segmented_control("Plan", ["Recommended", "Custom"], default="Recommended", key="sim_mode",
                                width="stretch")

table = effect_table(key, issue_date, cities, per_crew / 100, S.DEFAULT_CAP)
recommended = S.recommend(table, int(total), int(max_pw))

if mode == "Custom":
    with st.container(key="card-sim-editor"):
        theme.card_title("Custom plan", "Set crews per ward. Wards are sorted by how much the first crew would prevent.")
        w0 = table.wards.assign(first=table.prevented()[:, 1]).sort_values("first", ascending=False)
        editor = pd.DataFrame({
            "ward_id": w0[C.WARD_COL],
            "Ward": w0[C.WARD_COL].map(ward_label),
            "Risk": w0["tier"],
            "First crew prevents": w0["first"].round(2),
            "Crews": [recommended.get(w, 0) for w in w0[C.WARD_COL]],
        })
        edited = st.data_editor(
            editor, hide_index=True, width="stretch", height=300, key=f"sim_editor_{issue_date:%Y%m%d}_{per_crew}",
            disabled=["ward_id", "Ward", "Risk", "First crew prevents"],
            column_config={"ward_id": None,
                           "Crews": st.column_config.NumberColumn("Crews", min_value=0, max_value=int(max_pw), step=1)},
        )
        plan = {r.ward_id: int(r.Crews) for r in edited.itertuples() if int(r.Crews or 0) > 0}
        used = sum(plan.values())
        if used > total:
            st.warning(f"This plan uses {used} crews but only {total} are available. "
                       "Reduce crews or raise the number available.")
else:
    plan = recommended

by_ward, by_h = S.simulate(table, plan)
used = int(by_ward["crews"].sum())
prevented = float(by_h["cases_prevented"].sum())
peak = by_h.loc[by_h["beds_freed"].idxmax()]

theme.gap()
theme.stats([
    ("health_and_safety", "Cases prevented", f"{prevented:,.0f}",
     f"over weeks 2 to 4, {prevented / max(by_h['cases_baseline'].sum(), 1e-9):.0%} of the forecast"),
    ("bed", "Beds freed", f"{peak['beds_freed']:,.0f}", f"in the peak week ({int(peak['horizon'])} weeks ahead)"),
    ("water_drop", "Saline saved", f"{by_h['saline_saved'].sum():,.0f}<small> bags</small>", "over weeks 2 to 4"),
    ("groups", "Crews used", f"{used}<small> / {int(total)}</small>",
     (f"{prevented / used:.1f} cases prevented per crew" if used else
      "held in reserve: crews wouldn't change the forecast")),
])

left, right = st.columns([6, 5])
with left:
    with st.container(key="card-sim-impact"):
        theme.card_title("Impact by week", "Forecast cases across the wards shown, without and with this plan.")
        labels = [f"{h} weeks" for h in by_h["horizon"]]
        fig = go.Figure([
            go.Bar(x=labels, y=by_h["cases_baseline"], name="No extra crews", marker_color="#D6CDBB",
                   marker_line_width=0, hovertemplate="%{y:.0f} cases<extra></extra>"),
            go.Bar(x=labels, y=by_h["cases_with_crews"], name="With this plan", marker_color=theme.ACCENT,
                   marker_line_width=0, hovertemplate="%{y:.0f} cases<extra></extra>",
                   text=[f"−{p:.0f}" for p in by_h["cases_prevented"]], textposition="outside", cliponaxis=False),
        ])
        fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.08, margin=dict(l=0, r=0, t=40, b=0),
                          yaxis=dict(title="Expected cases"))
        theme.plot(fig, 300)
        st.html('<div class="m-steps">' + "".join(
            f'<div class="m-step"><div class="h">{int(r.horizon)} weeks ahead</div>'
            f'<div class="c" style="font-size:20px">−{r.cases_prevented:.0f} cases</div>'
            f'<div class="r">−{r.beds_freed:.1f} beds, −{r.saline_saved:.0f} saline bags</div></div>'
            for r in by_h.itertuples()) + "</div>")

with right:
    with st.container(key="card-sim-roi"):
        theme.card_title("Where the next crew pays off most",
                         "Cases prevented by one more crew in each ward, given the plan above.")
        nxt = by_ward[by_ward["crews"] < int(max_pw)].sort_values("next_crew_gain", ascending=False).head(8)
        if nxt["next_crew_gain"].max() < S.MIN_GAIN:
            st.html(f'<div class="m-act" style="margin:0"><div class="h">{theme.icon("check_circle")}'
                    'No ward would gain from another crew</div><div class="b">Breeding pressure is low this week, '
                    'so crews are better kept in reserve.</div></div>')
        else:
            rows = []
            for i, r in enumerate(nxt.itertuples()):
                best = ' <span class="m-badge" style="background:var(--accent);color:#fff">Best next crew</span>' if i == 0 else ""
                rows.append(
                    f'<div class="m-row"><div class="n">{i + 1}</div>'
                    f'<div><div class="w">{ward_label(r.ward_id)} {theme.badge(r.tier)}{best}</div>'
                    f'<div class="c">{r.crews} crew{"s" if r.crews != 1 else ""} now, '
                    f'{r.cases_prevented:.1f} cases prevented</div></div>'
                    f'<div class="e">+{r.next_crew_gain:.1f}<small>cases</small></div></div>'
                )
            st.html('<div class="m-list">' + "".join(rows) + "</div>")

theme.gap()

with st.container(key="card-sim-plan"):
    sim_mae = state.metrics().get("horizons", {}).get("3", {}).get("simulation_model", {}).get("mae")
    theme.card_title(
        "Deployment plan, ranked by return",
        "ROI is cases prevented per crew over weeks 2 to 4. "
        + (f"Scored by a monotone simulation model (3-week hold-out error {sim_mae:.2f} cases), so adding a "
           "crew can never raise a forecast." if sim_mae else ""),
        f"{len(plan)} wards",
    )
    if not plan:
        st.html('<p class="m-note">No crews deployed.</p>')
    else:
        d = by_ward[by_ward["crews"] > 0].sort_values("roi", ascending=False)
        out = pd.DataFrame({
            "Ward": d[C.WARD_COL].map(ward_label),
            "City": d[C.CITY_COL],
            "Risk": d["tier"],
            "Crews": d["crews"],
            "Cases prevented": d["cases_prevented"].round(1),
            "ROI (cases per crew)": d["roi"].round(2),
            **{f"{h} wk: before → after": [f"{a:.1f} → {b:.1f}" for a, b in zip(d[f"baseline_h{h}"], d[f"with_crews_h{h}"])]
               for h in table.horizons},
        })
        st.dataframe(out, hide_index=True, width="stretch", height=min(40 + 35 * len(out), 380),
                     column_config={"ROI (cases per crew)": st.column_config.ProgressColumn(
                         "ROI (cases per crew)", format="%.2f", min_value=0.0,
                         max_value=float(max(out["ROI (cases per crew)"].max(), 1e-6)))})
        st.download_button("Download deployment plan (CSV)",
                           d.drop(columns=["population_density_sqkm"]).to_csv(index=False).encode(),
                           file_name=f"moshari_crew_plan_{issue_date:%Y%m%d}.csv", mime="text/csv",
                           icon=":material/download:")

theme.footer(svc.bundle.metadata)
