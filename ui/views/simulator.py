"""Simulator: what spraying crews buy over the next 2–4 weeks (module 3)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from moshari import config as C
from moshari import simulation as S
from moshari.data import ward_label
from ui import i18n, state, theme

T, tr, num, BN = i18n.t, i18n.tr, i18n.num, i18n.is_bn()

issue_date, horizon, cities = st.session_state["_controls"]
svc = state.service()
key = state.data_key()


@st.cache_data(show_spinner=T("Simulating every ward at 0 to 6 crews…"), max_entries=32)
def effect_table(key: str, issue_date, cities: tuple, per_crew: float, cap: float) -> S.EffectTable:
    return S.build_effect_table(state.service(), issue_date, per_crew, cap, cities=list(cities) or None)


theme.header(
    T("Simulator"),
    T("Deploy larvicide and fogging crews, then see the cases, beds and saline they save 2 to 4 weeks out"),
    [("event", T("Issued"), state.fmt_week(issue_date)), ("groups", T("Wards"), num(60) if not cities else T("filtered"))],
)

with st.container(key="card-sim-controls"):
    theme.card_title(T("Crews and assumptions"),
                     T("Each crew removes a share of a ward's remaining breeding sites, so extra crews in the same "
                       "ward help less. The forecast models then re-run on the reduced breeding signal."))
    c1, c2, c3, c4 = st.columns([3, 4, 3, 4], vertical_alignment="bottom")
    total = c1.number_input(T("Crews available"), 0, 200, 30, 5, key="sim_total")
    per_crew = c2.slider(T("Effect per crew"), 10, 35, 20, 1, format="%d%%", key="sim_eff",
                         help=T("Share of remaining breeding pressure one crew removes. Capped at 75% per ward."))
    max_pw = c3.number_input(T("Max crews per ward"), 1, S.MAX_CREWS_PER_WARD, 4, 1, key="sim_maxpw")
    mode = c4.segmented_control(T("Plan"), ["Recommended", "Custom"], default="Recommended", key="sim_mode",
                                width="stretch", format_func=i18n.bound(i18n.core.t))

table = effect_table(key, issue_date, cities, per_crew / 100, S.DEFAULT_CAP)
recommended = S.recommend(table, int(total), int(max_pw))

if mode == "Custom":
    with st.container(key="card-sim-editor"):
        theme.card_title(T("Custom plan"), T("Set crews per ward. Wards are sorted by how much the first crew would prevent."))
        w0 = table.wards.assign(first=table.prevented()[:, 1]).sort_values("first", ascending=False)
        editor = pd.DataFrame({
            "ward_id": w0[C.WARD_COL],
            "Ward": w0[C.WARD_COL].map(ward_label),
            "Risk": w0["tier"],
            "First crew prevents": w0["first"].round(2),
            "Crews": [recommended.get(w, 0) for w in w0[C.WARD_COL]],
        })
        editor_cfg = {"ward_id": None,
                      "Crews": st.column_config.NumberColumn(T("Crews"), min_value=0, max_value=int(max_pw), step=1)}
        if BN:   # same columns; the read-only ones as Bangla text, headers as labels
            editor = editor.assign(Ward=editor["Ward"].map(tr), Risk=editor["Risk"].map(tr),
                                   **{"First crew prevents": editor["First crew prevents"].map(lambda v: num(v, ".2f"))})
            editor_cfg.update({c: st.column_config.TextColumn(T(c)) for c in ("Ward", "Risk", "First crew prevents")})
        edited = st.data_editor(
            editor, hide_index=True, width="stretch", height=300, key=f"sim_editor_{issue_date:%Y%m%d}_{per_crew}",
            disabled=["ward_id", "Ward", "Risk", "First crew prevents"],
            column_config=editor_cfg,
        )
        plan = {r.ward_id: int(r.Crews) for r in edited.itertuples() if int(r.Crews or 0) > 0}
        used = sum(plan.values())
        if used > total:
            st.warning(T("This plan uses {used} crews but only {total} are available. "
                         "Reduce crews or raise the number available.", used=used, total=int(total)))
else:
    plan = recommended

by_ward, by_h = S.simulate(table, plan)
used = int(by_ward["crews"].sum())
prevented = float(by_h["cases_prevented"].sum())
peak = by_h.loc[by_h["beds_freed"].idxmax()]

theme.gap()
theme.stats([
    ("health_and_safety", T("Cases prevented"), num(prevented, ",.0f"),
     T("over weeks 2 to 4, {p:.0%} of the forecast", p=prevented / max(by_h['cases_baseline'].sum(), 1e-9))),
    ("bed", T("Beds freed"), num(peak['beds_freed'], ",.0f"),
     T("in the peak week ({n} weeks ahead)", n=int(peak['horizon']))),
    ("water_drop", T("Saline saved"), f"{num(by_h['saline_saved'].sum(), ',.0f')}<small>{T(' bags')}</small>",
     T("over weeks 2 to 4")),
    ("groups", T("Crews used"), f"{num(used)}<small> / {num(int(total))}</small>",
     (T("{x:.1f} cases prevented per crew", x=prevented / used) if used else
      T("held in reserve: crews wouldn't change the forecast"))),
])

left, right = st.columns([6, 5])
with left:
    with st.container(key="card-sim-impact"):
        theme.card_title(T("Impact by week"), T("Forecast cases across the wards shown, without and with this plan."))
        labels = [T("{n} weeks", n=h) for h in by_h["horizon"]]
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
            f'<div class="m-step"><div class="h">{T("{n} weeks ahead", n=int(r.horizon))}</div>'
            f'<div class="c" style="font-size:20px">{T("−{n:.0f} cases", n=r.cases_prevented)}</div>'
            f'<div class="r">{T("−{b:.1f} beds, −{s:.0f} saline bags", b=r.beds_freed, s=r.saline_saved)}</div></div>'
            for r in by_h.itertuples()) + "</div>")

with right:
    with st.container(key="card-sim-roi"):
        theme.card_title(T("Where the next crew pays off most"),
                         T("Cases prevented by one more crew in each ward, given the plan above."))
        nxt = by_ward[by_ward["crews"] < int(max_pw)].sort_values("next_crew_gain", ascending=False).head(8)
        if nxt["next_crew_gain"].max() < S.MIN_GAIN:
            st.html(f'<div class="m-act" style="margin:0"><div class="h">{theme.icon("check_circle")}'
                    + T("No ward would gain from another crew") + '</div><div class="b">'
                    + T("Breeding pressure is low this week, so crews are better kept in reserve.") + '</div></div>')
        else:
            rows = []
            for i, r in enumerate(nxt.itertuples()):
                best = (f' <span class="m-badge" style="background:var(--accent);color:#fff">{T("Best next crew")}</span>'
                        if i == 0 else "")
                rows.append(
                    f'<div class="m-row"><div class="n">{num(i + 1)}</div>'
                    f'<div><div class="w">{i18n.ward(r.ward_id)} {theme.badge(r.tier)}{best}</div>'
                    f'<div class="c">' + (T("{n} crews now, {x:.1f} cases prevented", n=r.crews, x=r.cases_prevented) if BN else
                                          f'{r.crews} crew{"s" if r.crews != 1 else ""} now, {r.cases_prevented:.1f} cases prevented')
                    + f'</div></div><div class="e">{num(r.next_crew_gain, "+.1f")}<small>{T("cases")}</small></div></div>'
                )
            st.html('<div class="m-list">' + "".join(rows) + "</div>")

theme.gap()

with st.container(key="card-sim-plan"):
    sim_mae = state.metrics().get("horizons", {}).get("3", {}).get("simulation_model", {}).get("mae")
    theme.card_title(
        T("Deployment plan, ranked by return"),
        T("ROI is cases prevented per crew over weeks 2 to 4. ")
        + (T("Scored by a monotone simulation model (3-week hold-out error {e:.2f} cases), so adding a "
             "crew can never raise a forecast.", e=sim_mae) if sim_mae else ""),
        T("{n} wards", n=len(plan)),
    )
    if not plan:
        st.html(f'<p class="m-note">{T("No crews deployed.")}</p>')
    else:
        d = by_ward[by_ward["crews"] > 0].sort_values("roi", ascending=False)
        out = pd.DataFrame({
            "Ward": d[C.WARD_COL].map(ward_label),
            "City": d[C.CITY_COL],
            "Risk": d["tier"],
            "Crews": d["crews"],
            "Cases prevented": d["cases_prevented"].round(1),
            "ROI (cases per crew)": d["roi"].round(2),
            **{T("{h} wk: before → after", h=h): [f"{a:.1f} → {b:.1f}" for a, b in zip(d[f"baseline_h{h}"], d[f"with_crews_h{h}"])]
               for h in table.horizons},
        })
        out, out_cfg = i18n.frame(out, {"ROI (cases per crew)": st.column_config.ProgressColumn(
                         "ROI (cases per crew)", format="%.2f", min_value=0.0,
                         max_value=float(max(out["ROI (cases per crew)"].max(), 1e-6)))},
                         formats={"Crews": "d", "Cases prevented": ".1f", "ROI (cases per crew)": ".2f"})
        st.dataframe(out, hide_index=True, width="stretch", height=min(40 + 35 * len(out), 380),
                     column_config=out_cfg)
        st.download_button(T("Download deployment plan (CSV)"),
                           d.drop(columns=["population_density_sqkm"]).to_csv(index=False).encode(),
                           file_name=f"moshari_crew_plan_{issue_date:%Y%m%d}.csv", mime="text/csv",
                           icon=":material/download:")

theme.footer(svc.bundle.metadata)
