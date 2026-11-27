"""Dispatch: ready-to-send SMS, WhatsApp and commissioner briefs per ward (module 4)."""

from __future__ import annotations

import html
import importlib

import pandas as pd
import streamlit as st
import streamlit.components.v1 as stc

from moshari import config as C
from moshari import dispatch as D
from moshari.data import ward_label
from ui import state, theme

issue_date, horizon, cities = st.session_state["_controls"]
svc = state.service()
key = state.data_key()
policy = state.policy()
target = issue_date + pd.Timedelta(weeks=horizon)


def _optional(name: str):
    """The allocation / routing engines live in teammates' modules; use them when present."""
    try:
        return importlib.import_module(f"moshari.{name}")
    except Exception:  # not merged yet, or not importable on this branch: fall back
        return None


ALLOC = _optional("allocation")
ROUTING = _optional("routing")


@st.cache_data(show_spinner="Preparing notices…", max_entries=64)
def build_table(key: str, issue_date, horizon: int, cities: tuple, policy: str,
                stock_pct: float, crews: int) -> tuple[pd.DataFrame, bool, bool]:
    """Dispatch table for these settings, plus which real engines were used."""
    fc = state.forecast_all(key, issue_date, horizon, cities, policy)
    if ALLOC is not None:
        alloc = ALLOC.allocate(fc, state.service().wards, stock_pct, crews)
    else:
        alloc = D.standin_allocation(fc)
    routing = None
    if ROUTING is not None:
        try:
            routing = ROUTING.route_overflow(alloc, ROUTING.load_bed_capacity())
        except (FileNotFoundError, ValueError):
            routing = None
    return D.dispatch_table(alloc, routing), ALLOC is not None, routing is not None


@st.cache_data(show_spinner="Packing notices…", max_entries=32)
def bundle(key: str, issue_date, horizon: int, cities: tuple, policy: str, stock_pct: float, crews: int,
           ward_ids: tuple) -> tuple[bytes, str]:
    """Zip of every notice plus one printable file with all briefs (cached per selection)."""
    table = build_table(key, issue_date, horizon, cities, policy, stock_pct, crews)[0]
    rows = table[table[C.WARD_COL].isin(ward_ids)].to_dict("records")
    return D.export_zip(rows), D.briefs_html(rows)


theme.header(
    "Dispatch",
    f"Ready-to-send notices for the week of {state.fmt_week(target)}",
    [("event", "Issued", state.fmt_week(issue_date)), ("schedule", "Horizon", f"{horizon} weeks")],
)

# ----------------------------------------------------------------------------- who and what
with st.container(key="card-dispatch-controls"):
    theme.card_title("Who gets a notice",
                     "Pick the wards, then preview, copy or download their SMS, WhatsApp message and printable brief.")
    c1, c2 = st.columns([7, 5], vertical_alignment="bottom")
    MODES = {"high": "High risk", "deficit": "In deficit", "pick": "Choose", "all": "All"}
    mode = c1.segmented_control("Send to", list(MODES), format_func=MODES.get, default="high",
                                key="disp_mode", width="stretch",
                                help="High risk = High and Critical wards. In deficit = short of supplies, "
                                     "crews or beds.") or "high"
    stock, crews = 70, 40  # Resources page defaults
    if ALLOC is not None:
        with c2.popover("Supply scenario", icon=":material/tune:", width="stretch"):
            stock = st.slider("Available regional stock", 30, 100, 70, 5, format="%d%%", key="disp_stock",
                              help="Share of total ward demand in the regional store, as on the Resources page.")
            crews = st.number_input("Total spraying crews", 0, 300, 40, 5, key="disp_crews")

table, real_alloc, real_routing = build_table(key, issue_date, horizon, cities, policy, stock / 100, int(crews))

if mode == "pick":
    picked = st.multiselect(
        "Wards", table[C.WARD_COL].tolist(), key="disp_wards", format_func=ward_label,
        placeholder="Type a ward, e.g. DNCC Ward 12",
        default=table[C.WARD_COL].head(1).tolist() if "disp_wards" not in st.session_state else None,
    )
    chosen = D.select_rows(table, "pick", picked)
else:
    chosen = D.select_rows(table, mode)

if not real_alloc:
    st.info("The allocation engine isn't merged on this branch yet, so supplies show full demand with no "
            "shortages. Once Resources is merged, these notices use the real scarcity plan automatically.",
            icon=":material/info:")

rows = chosen.to_dict("records")
sms_all = [D.sms(r) for r in rows]
n_def = sum(bool(D.deficit_items(r)) for r in rows)
n_moves = sum(len(r["transfers_out"]) for r in rows)
longest = max((D.gsm_length(s) for s in sms_all), default=0)

theme.stats([
    ("outgoing_mail", "Notices ready", f"{len(rows)}<small> wards</small>", "3 formats each"),
    ("warning", "With a deficit",
     f"<span style='color:{theme.TIER_COLORS['Critical'] if n_def else theme.INK}'>{n_def}</span>"
     f"<small> / {len(rows)}</small>", "supplies, crews or beds short" if n_def else "everyone fully supplied"),
    ("local_hospital", "Patient transfers", f"{n_moves}",
     "within the same city" if real_routing else "routing not merged yet"),
    ("sms", "Longest SMS", f"{longest}<small> / {D.SMS_LIMIT}</small>", "always one SMS, never split"),
])

if not rows:
    with st.container(key="card-dispatch-empty"):
        msg = {"high": "No ward is High or Critical this week.", "deficit": "No ward is short of anything.",
               "pick": "Choose at least one ward above.", "all": "No wards match the city filter."}[mode]
        st.html(f'<div class="m-act" style="margin:0"><div class="h">{theme.icon("check_circle")}{msg}</div>'
                '<div class="b">Try another "Send to" option, a later issue week, or less stock in the supply '
                'scenario.</div></div>')
    st.stop()

# ----------------------------------------------------------------------------- preview
left, right = st.columns([11, 13])
with left:
    with st.container(key="card-dispatch-list"):
        theme.card_title("Wards", "Highest priority first. Pick one to preview.", f"{len(rows)}")
        overview = pd.DataFrame({
            "Ward": [ward_label(r[C.WARD_COL]) for r in rows],
            "Risk": [r["tier"] for r in rows],
            "Cases": [r["expected_cases"] for r in rows],
            "Status": [D.deficit_text(r) or "Fully supplied" for r in rows],
        })
        ev = st.dataframe(
            overview, hide_index=True, width="stretch", height=min(38 + 35 * len(rows), 460),
            on_select="rerun", selection_mode="single-row", key="disp_table",
            column_config={"Ward": st.column_config.TextColumn(width=118, pinned=True),
                           "Cases": st.column_config.NumberColumn(format="%.1f", width=58),
                           "Risk": st.column_config.TextColumn(width=64),
                           "Status": st.column_config.TextColumn(width=150)},
        )
        sel = ev.selection.rows[0] if ev and ev.selection.rows else 0
        sel = min(sel, len(rows) - 1)

row = rows[sel]
wid = row[C.WARD_COL]
with right:
    with st.container(key="card-dispatch-preview"):
        theme.card_title(ward_label(wid), D.deficit_text(row) or "Fully supplied for the planned caseload",
                         theme.badge(row["tier"]))
        t_sms, t_wa, t_brief = st.tabs([":material/sms: SMS", ":material/chat: WhatsApp",
                                        ":material/description: Brief"])
        with t_sms:
            text = sms_all[sel]
            n = D.gsm_length(text)
            st.code(text, language=None, wrap_lines=True)
            st.caption(f"{n} / {D.SMS_LIMIT} characters, one SMS. Use the copy icon to paste into your SMS gateway.")
            st.download_button("Download SMS", text + "\n", f"{wid}_sms.txt", "text/plain",
                               icon=":material/download:", key="dl_sms")
        with t_wa:
            msg = D.whatsapp(row)
            st.code(msg, language=None, wrap_lines=True)
            st.caption(r"WhatsApp shows \*text\* as bold and \_text\_ as italics.")
            st.download_button("Download WhatsApp text", msg + "\n", f"{wid}_whatsapp.txt", "text/plain",
                               icon=":material/download:", key="dl_wa")
        with t_brief:
            brief = D.brief_html(row)
            st.download_button("Download brief (HTML, print to PDF)", brief, f"{wid}_brief.html", "text/html",
                               icon=":material/download:", key="dl_brief")
            if hasattr(st, "iframe"):  # Streamlit 1.5x+; every value in the brief is HTML-escaped
                st.iframe(brief, height=820)
            else:
                stc.html(brief, height=820, scrolling=True)

# ----------------------------------------------------------------------------- batch download
with st.container(key="card-dispatch-batch"):
    theme.card_title("Send them all",
                     "Every selected ward in one go: a zip with each SMS, WhatsApp message and brief, "
                     "or a single printable file with one brief per page.", f"{len(rows)} wards")
    zbytes, all_briefs = bundle(key, issue_date, horizon, cities, policy, stock / 100, int(crews),
                                tuple(r[C.WARD_COL] for r in rows))
    stamp = pd.Timestamp(target).strftime("%Y-%m-%d")
    b1, b2 = st.columns(2)
    b1.download_button("Download all notices (.zip)", zbytes, f"moshari_dispatch_{stamp}.zip", "application/zip",
                       icon=":material/folder_zip:", width="stretch", key="dl_zip")
    b2.download_button("Download all briefs (one printable file)", all_briefs, f"moshari_briefs_{stamp}.html",
                       "text/html", icon=":material/print:", width="stretch", key="dl_all_briefs")
    st.caption("Everything here is built from fixed templates on this computer: no internet and no AI service, "
               "so it works offline. " + html.escape(f"Signed as {D.SENDER}."))
