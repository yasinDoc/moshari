"""Weekly briefing: risk, supplies, transfers, crews and notices as one decision, plus a one-page PDF."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from moshari import briefing as B
from moshari.briefing_pdf import briefing_pdf
from moshari.data import ward_label
from ui import i18n, state, theme

T, tr, num, BN = i18n.t, i18n.tr, i18n.num, i18n.is_bn()
LANG = i18n.lang()

issue_date, horizon, cities = st.session_state["_controls"]
key = state.data_key()
policy = state.policy()
target = issue_date + pd.Timedelta(weeks=horizon)
RED = theme.TIER_COLORS["Critical"]


@st.cache_data(show_spinner=T("Preparing the briefing…"), max_entries=64)
def make(key: str, issue_date, horizon: int, cities: tuple, policy: str,
         stock_pct: float, crews: int, surge_pct: int, lang: str = "en") -> tuple[dict, bytes]:
    """The briefing for these settings and its PDF (cached per scenario and language).

    The on-screen sentences follow ``lang``; the PDF is still the English one.
    """
    brief = B.build(state.service(), issue_date, horizon, cities, policy, stock_pct, crews, surge_pct, lang=lang)
    pdf_brief = brief if lang == "en" else B.build(state.service(), issue_date, horizon, cities, policy,
                                                   stock_pct, crews, surge_pct)
    return brief, briefing_pdf(pdf_brief)


theme.header(
    T("Weekly briefing"),
    T("One page for the city health officer, week of {week}", week=state.fmt_week(target)),
    [("event", T("Issued"), state.fmt_week(issue_date)), ("schedule", T("Horizon"), T("{n} weeks", n=horizon))],
)

with st.container(key="card-brief-controls"):
    theme.card_title(T("Supply scenario"),
                     T("The same settings as the Resources and Hospital beds pages. The briefing and its PDF "
                       "update as you change them."))
    c1, c2, c3 = st.columns([5, 3, 4], vertical_alignment="bottom")
    stock = c1.slider(T("Available regional stock"), 30, 100, 70, 5, format="%d%%", key="brief_stock",
                      help=T("Share of total ward demand that is actually in the regional store."))
    crews = c2.number_input(T("Total spraying crews"), 0, 300, 40, 5, key="brief_crews")
    surge = c3.slider(T("Surge beds per ward"), 0, 100, 0, 10, format="+%d%%", key="brief_surge",
                      help=T("Extra corridor or field beds opened in every ward."))

brief, pdf = make(key, issue_date, horizon, cities, policy, stock / 100, int(crews), int(surge), LANG)

theme.gap()

# ----------------------------------------------------------------------------- the decision
with st.container(key="card-brief-decision"):
    where = T("all five city corporations") if len(brief["cities"]) >= 5 else ", ".join(tr(c) for c in brief["cities"])
    theme.card_title(T("Decision for this week"), T("Built from all five modules, for {where}.", where=where))
    lines = "".join(
        f'<div class="m-row"><div class="n">{num(i)}</div><div><div class="w" style="font-weight:600">'
        f'{html.escape(line)}</div></div><div></div></div>'
        for i, line in enumerate(brief["decision"], 1))
    st.html(f'<div class="m-list">{lines}</div>')
    d1, d2 = st.columns([3, 2], vertical_alignment="center")
    d1.download_button(T("Download briefing (PDF)"), pdf, f"moshari_briefing_{target:%Y-%m-%d}.pdf",
                       "application/pdf", icon=":material/picture_as_pdf:", type="primary", width="stretch",
                       key="dl_briefing")
    d2.caption(T("One A4 page, ready to print or hand over. Made on this computer: no internet, no AI service."))

theme.gap()


def _red(n: int, text: str) -> str:
    return f"<span style='color:{RED if n else theme.INK}'>{text}</span>"


theme.stats([
    ("warning", T("High-risk wards"), _red(brief["high_wards"], num(brief['high_wards']))
     + f"<small> / {num(brief['wards'])}</small>", T("{n} expected critical", n=brief['critical_wards'])),
    ("inventory_2", T("Wards short of supplies"), _red(brief["deficit_wards"], num(brief['deficit_wards'])),
     B.alert_text({**brief["alerts"], "crews_short": 0, "out_of_beds_wards": 0}, LANG)),
    ("local_hospital", T("Patients without a bed"), _red(brief["unplaced"], num(brief['unplaced'])),
     T("after moving {n} within their city", n=brief['patients_moved'])),
    ("groups", T("Spraying crews"), _red(brief["crews_unmet"], num(brief['crews_assigned']))
     + f"<small>{T(' / {n} needed', n=brief['crews_needed'])}</small>",
     T("prevent about {n:,.0f} cases over weeks 2 to 4", n=brief['cases_prevented'])),
])

left, right = st.columns([7, 5])
with left:
    with st.container(key="card-brief-cities"):
        theme.card_title(T("Risk and response by city"), T("Worst-hit first."),
                         T("{n} cities", n=len(brief['by_city'])) if BN else f"{len(brief['by_city'])} cities")
        table = pd.DataFrame({
            "City": [c["city"] for c in brief["by_city"]],
            "High wards": [f"{c['high_wards']} / {c['wards']}" for c in brief["by_city"]],
            "Cases": [round(c["expected_cases"]) for c in brief["by_city"]],
            "Wards short": [c["short_wards"] for c in brief["by_city"]],
            "Crews": [f"{c['crews_assigned']} / {c['crews_needed']}" for c in brief["by_city"]],
            "Moved": [c["patients_moved"] for c in brief["by_city"]],
            "No bed": [c["unplaced"] for c in brief["by_city"]],
        })
        table, table_cfg = i18n.frame(table, formats={"Cases": "d", "Wards short": "d", "Moved": "d", "No bed": "d"})
        st.dataframe(table, hide_index=True, width="stretch", column_config=table_cfg)
        theme.card_title(T("Send teams here first"), T("Highest alert priority this week."), T("Top {n}", n=5))
        rows = [
            f'<div class="m-row"><div class="n">{num(i)}</div>'
            f'<div><div class="w">{i18n.ward(r["ward_id"])} {theme.badge(r["tier"])}</div>'
            f'<div class="c">{html.escape(tr(r["city"]))}, {html.escape(r["status"].lower())}</div></div>'
            f'<div class="e">{num(r["expected_cases"], ".1f")}<small>{T("cases")}</small></div></div>'
            for i, r in enumerate(brief["top_rows"], 1)]
        st.html(f'<div class="m-list">{"".join(rows)}</div>')

with right:
    with st.container(key="card-brief-transfers"):
        moves = brief["transfers"]
        theme.card_title(T("Patient transfers"), T("Overflow patients moved to wards with spare beds, in the same city."),
                         T("{n} patients", n=brief['patients_moved']))
        if moves:
            items = "".join(
                f'<div class="m-row"><div class="n">{num(i)}</div><div><div class="w">'
                f'{T("{a} to {b}", a=i18n.ward(t["from_ward"]), b=i18n.ward(t["to_ward"]))}</div>'
                f'<div class="c">{html.escape(tr(t["city"]))}</div></div>'
                f'<div class="e">{num(t["patients"])}<small>{T("patients") if BN else ("patient" if t["patients"] == 1 else "patients")}</small></div></div>'
                for i, t in enumerate(moves[:8], 1))
            st.html(f'<div class="m-list">{items}</div>')
            if len(moves) > 8:
                st.html(f'<p class="m-note">{T("{n} more on the Hospital beds page.", n=len(moves) - 8)}</p>')
        else:
            st.html(f'<div class="m-act" style="margin:0"><div class="h">{theme.icon("check_circle")}'
                    + T("No transfers needed") + '</div><div class="b">' + T("Every ward's own beds cover the forecast.")
                    + '</div></div>')
        if brief["out_of_beds"]:
            st.html(f'<p class="m-note" style="color:{RED};font-weight:700">'
                    + T("Still out of beds: {wards}. Try surge beds above.",
                        wards=html.escape(", ".join(i18n.ward(w) for w in brief["out_of_beds"]))) + '</p>')
    with st.container(key="card-brief-notices"):
        theme.card_title(T("Notices"), T("Ready on the Dispatch page: SMS, WhatsApp and a commissioner brief per ward."))
        st.html(f'<div class="m-prof" style="grid-template-columns:repeat(2,1fr)">'
                f'<div><div class="k">{T("Ready to send")}</div><div class="v">{num(brief["notices_ready"])}</div></div>'
                f'<div><div class="k">{T("Works offline")}</div><div class="v">{T("Yes")}</div></div></div>')
        st.page_link("ui/views/dispatch.py", label=T("Open Dispatch"), icon=":material/campaign:")

theme.footer(state.service().bundle.metadata)
