"""Weekly briefing: risk, supplies, transfers, crews and notices as one decision, plus a one-page PDF."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from moshari import briefing as B
from moshari.briefing_pdf import briefing_pdf
from moshari.data import ward_label
from ui import state, theme

issue_date, horizon, cities = st.session_state["_controls"]
key = state.data_key()
policy = state.policy()
target = issue_date + pd.Timedelta(weeks=horizon)
RED = theme.TIER_COLORS["Critical"]


@st.cache_data(show_spinner="Preparing the briefing…", max_entries=64)
def make(key: str, issue_date, horizon: int, cities: tuple, policy: str,
         stock_pct: float, crews: int, surge_pct: int) -> tuple[dict, bytes]:
    """The briefing for these settings and its PDF (cached per scenario)."""
    brief = B.build(state.service(), issue_date, horizon, cities, policy, stock_pct, crews, surge_pct)
    return brief, briefing_pdf(brief)


theme.header(
    "Weekly briefing",
    f"One page for the city health officer, week of {state.fmt_week(target)}",
    [("event", "Issued", state.fmt_week(issue_date)), ("schedule", "Horizon", f"{horizon} weeks")],
)

with st.container(key="card-brief-controls"):
    theme.card_title("Supply scenario",
                     "The same settings as the Resources and Hospital beds pages. The briefing and its PDF "
                     "update as you change them.")
    c1, c2, c3 = st.columns([5, 3, 4], vertical_alignment="bottom")
    stock = c1.slider("Available regional stock", 30, 100, 70, 5, format="%d%%", key="brief_stock",
                      help="Share of total ward demand that is actually in the regional store.")
    crews = c2.number_input("Total spraying crews", 0, 300, 40, 5, key="brief_crews")
    surge = c3.slider("Surge beds per ward", 0, 100, 0, 10, format="+%d%%", key="brief_surge",
                      help="Extra corridor or field beds opened in every ward.")

brief, pdf = make(key, issue_date, horizon, cities, policy, stock / 100, int(crews), int(surge))

theme.gap()

# ----------------------------------------------------------------------------- the decision
with st.container(key="card-brief-decision"):
    where = "all five city corporations" if len(brief["cities"]) >= 5 else ", ".join(brief["cities"])
    theme.card_title("Decision for this week", f"Built from all five modules, for {where}.")
    lines = "".join(
        f'<div class="m-row"><div class="n">{i}</div><div><div class="w" style="font-weight:600">'
        f'{html.escape(line)}</div></div><div></div></div>'
        for i, line in enumerate(brief["decision"], 1))
    st.html(f'<div class="m-list">{lines}</div>')
    d1, d2 = st.columns([3, 2], vertical_alignment="center")
    d1.download_button("Download briefing (PDF)", pdf, f"moshari_briefing_{target:%Y-%m-%d}.pdf",
                       "application/pdf", icon=":material/picture_as_pdf:", type="primary", width="stretch",
                       key="dl_briefing")
    d2.caption("One A4 page, ready to print or hand over. Made on this computer: no internet, no AI service.")

theme.gap()


def _red(n: int, text: str) -> str:
    return f"<span style='color:{RED if n else theme.INK}'>{text}</span>"


theme.stats([
    ("warning", "High-risk wards", _red(brief["high_wards"], f"{brief['high_wards']}")
     + f"<small> / {brief['wards']}</small>", f"{brief['critical_wards']} expected critical"),
    ("inventory_2", "Wards short of supplies", _red(brief["deficit_wards"], f"{brief['deficit_wards']}"),
     B.alert_text({**brief["alerts"], "crews_short": 0, "out_of_beds_wards": 0})),
    ("local_hospital", "Patients without a bed", _red(brief["unplaced"], f"{brief['unplaced']}"),
     f"after moving {brief['patients_moved']} within their city"),
    ("groups", "Spraying crews", _red(brief["crews_unmet"], f"{brief['crews_assigned']}")
     + f"<small> / {brief['crews_needed']} needed</small>",
     f"prevent about {brief['cases_prevented']:,.0f} cases over weeks 2 to 4"),
])

left, right = st.columns([7, 5])
with left:
    with st.container(key="card-brief-cities"):
        theme.card_title("Risk and response by city", "Worst-hit first.", f"{len(brief['by_city'])} cities")
        table = pd.DataFrame({
            "City": [c["city"] for c in brief["by_city"]],
            "High wards": [f"{c['high_wards']} / {c['wards']}" for c in brief["by_city"]],
            "Cases": [round(c["expected_cases"]) for c in brief["by_city"]],
            "Wards short": [c["short_wards"] for c in brief["by_city"]],
            "Crews": [f"{c['crews_assigned']} / {c['crews_needed']}" for c in brief["by_city"]],
            "Moved": [c["patients_moved"] for c in brief["by_city"]],
            "No bed": [c["unplaced"] for c in brief["by_city"]],
        })
        st.dataframe(table, hide_index=True, width="stretch")
        theme.card_title("Send teams here first", "Highest forecast alert priority this week, as on Overview. "
                         "Supplies follow the Resources ranking, which also weighs population density.", "Top 5")
        rows = [
            f'<div class="m-row"><div class="n">{i}</div>'
            f'<div><div class="w">{ward_label(r["ward_id"])} {theme.badge(r["tier"])}</div>'
            f'<div class="c">{html.escape(r["city"])}, {html.escape(r["status"].lower())}</div></div>'
            f'<div class="e">{r["expected_cases"]:.1f}<small>cases</small></div></div>'
            for i, r in enumerate(brief["top_rows"], 1)]
        st.html(f'<div class="m-list">{"".join(rows)}</div>')

with right:
    with st.container(key="card-brief-transfers"):
        moves = brief["transfers"]
        theme.card_title("Patient transfers", "Overflow patients moved to wards with spare beds, in the same city.",
                         f"{brief['patients_moved']} patients")
        if moves:
            items = "".join(
                f'<div class="m-row"><div class="n">{i}</div><div><div class="w">'
                f'{ward_label(t["from_ward"])} to {ward_label(t["to_ward"])}</div>'
                f'<div class="c">{html.escape(t["city"])}</div></div>'
                f'<div class="e">{t["patients"]}<small>{"patient" if t["patients"] == 1 else "patients"}</small></div></div>'
                for i, t in enumerate(moves[:8], 1))
            st.html(f'<div class="m-list">{items}</div>')
            if len(moves) > 8:
                st.html(f'<p class="m-note">{len(moves) - 8} more on the Hospital beds page.</p>')
        else:
            st.html(f'<div class="m-act" style="margin:0"><div class="h">{theme.icon("check_circle")}'
                    'No transfers needed</div><div class="b">Every ward\'s own beds cover the forecast.</div></div>')
        if brief["out_of_beds"]:
            st.html(f'<p class="m-note" style="color:{RED};font-weight:700">Still out of beds: '
                    f'{html.escape(", ".join(ward_label(w) for w in brief["out_of_beds"]))}. '
                    'Try surge beds above.</p>')
    with st.container(key="card-brief-notices"):
        theme.card_title("Notices", "Ready on the Dispatch page: SMS, WhatsApp and a commissioner brief per ward.")
        st.html(f'<div class="m-prof" style="grid-template-columns:repeat(2,1fr)">'
                f'<div><div class="k">Ready to send</div><div class="v">{brief["notices_ready"]}</div></div>'
                f'<div><div class="k">Works offline</div><div class="v">Yes</div></div></div>')
        st.page_link("ui/views/dispatch.py", label="Open Dispatch", icon=":material/campaign:")

theme.footer(state.service().bundle.metadata)
