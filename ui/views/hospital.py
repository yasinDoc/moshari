"""Hospital beds: overflow routing between wards of the same city corporation."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from moshari import config as C
from moshari.data import ward_label
from moshari.routing import (
    CAPACITY_END,
    CAPACITY_QUANTILE,
    beds_from_forecast,
    load_bed_capacity,
    route_overflow,
)
from ui import state, theme

RED = theme.TIER_COLORS["Critical"]

issue_date, horizon, cities = st.session_state["_controls"]
key = state.data_key()
policy = state.policy()
target = issue_date + pd.Timedelta(weeks=horizon)


@st.cache_data(show_spinner=False)
def bed_capacity() -> pd.Series:
    return load_bed_capacity()


@st.cache_data(show_spinner=False, max_entries=128)
def routed(key: str, issue_date: pd.Timestamp, horizon: int, cities: tuple[str, ...], policy: str):
    fc = state.forecast_all(key, issue_date, horizon, cities, policy)
    # Bed demand per ward. When Yasin's allocation engine is merged, pass its
    # `allocate(...)` table here instead: route_overflow only needs
    # ward_id, city and hospital_beds_required.
    alloc = beds_from_forecast(fc)
    return tuple(route_overflow(alloc, bed_capacity()))


theme.header(
    "Hospital beds",
    f"Bed demand and overflow transfers for the week of {state.fmt_week(target)}",
    [("event", "Issued", state.fmt_week(issue_date)), ("schedule", "Horizon", f"{horizon} weeks")],
)

try:
    transfers, wards, city_tbl = routed(key, issue_date, horizon, cities, policy)
except (FileNotFoundError, ValueError) as exc:
    st.error(f"Hospital routing is unavailable: {exc}")
    st.stop()

short = wards[wards["net_deficit"] > 0].sort_values("net_deficit", ascending=False)
over_before = int((wards["beds_required"] > wards["bed_capacity"]).sum())
theme.stats([
    ("local_hospital", "Beds available", f"{int(wards['bed_capacity'].sum()):,}",
     f"normal capacity of {len(wards)} wards"),
    ("hotel", "Beds needed", f"{int(wards['beds_required'].sum()):,}",
     f"{over_before} wards over their own capacity"),
    ("swap_horiz", "Patients moved", f"{int(transfers['patients'].sum()):,}",
     f"in {len(transfers)} transfers, always within the same city"),
    ("warning", "Still short",
     f"<span style='color:{RED if len(short) else theme.INK}'>{len(short)}</span><small> wards</small>",
     f"{int(short['net_deficit'].sum())} patients without a bed in their city" if len(short)
     else "every patient has a bed in their city"),
])

# --------------------------------------------------------------------------- city cards
with st.container(key="card-cities"):
    theme.card_title("Beds by city", "Overflow can only move between wards of the same city corporation.",
                     f"{len(city_tbl)} cities")
    cards = []
    for r in city_tbl.itertuples():
        util = r.utilization
        color = RED if util > 1 else (theme.TIER_COLORS["High"] if util > 0.85 else theme.INK)
        head = f"{r.headroom:+,} beds" if r.headroom else "0 beds"
        cards.append(
            f'<div class="m-stat"><div class="top"><span class="k">{html.escape(r.city)}</span></div>'
            f'<div class="v" style="color:{color}">{util:.0%}<small> used</small></div>'
            f'<div class="s">{r.total_required:,} needed of {r.total_capacity:,} beds<br>'
            f'Headroom <b style="color:{RED if r.headroom < 0 else theme.INK}">{head}</b><br>'
            f"{r.patients_moved:,} patient{'' if r.patients_moved == 1 else 's'} moved</div></div>"
        )
    st.html('<div class="m-stats" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr))">'
            f'{"".join(cards)}</div>')

theme.gap()

left, right = st.columns([7, 5])
with left:
    with st.container(key="card-transfers"):
        theme.card_title("Transfers", "Overflow goes to the least loaded ward first, then the nearest by ward number.",
                         f"{len(transfers)} moves")
        if transfers.empty:
            msg = ("No ward needs more beds than it has." if short.empty else
                   "No transfers are possible: every city with overflow is already full.")
            st.html(f'<p class="m-note">{msg}</p>')
        else:
            items = "".join(
                f'<div class="m-row"><div class="n">{i}</div><div><div class="w">Move {t.patients} '
                f'patient{"s" if t.patients != 1 else ""} from {html.escape(ward_label(t.from_ward))} to '
                f'{html.escape(ward_label(t.to_ward))}</div><div class="c">{html.escape(t.city)}</div></div>'
                f'<div class="e">{t.patients}</div></div>'
                for i, t in enumerate(transfers.itertuples(), 1)
            )
            st.html(f'<div class="m-list">{items}</div>')

with right:
    with st.container(key="card-deficit"):
        theme.card_title("Still in deficit after routing", "Wards whose city has no spare beds left.",
                         f"{len(short)} wards")
        if short.empty:
            st.html('<p class="m-note">None. Every patient has a bed within their own city.</p>')
        else:
            items = "".join(
                f'<div class="m-row"><div class="n" style="color:{RED}">!</div><div>'
                f'<div class="w" style="color:{RED}">{html.escape(ward_label(r.ward_id))}</div>'
                f'<div class="c">{html.escape(r.city)}, needs {r.beds_required} of {r.bed_capacity} beds</div></div>'
                f'<div class="e" style="color:{RED}">{r.net_deficit}<small>beds short</small></div></div>'
                for r in short.itertuples()
            )
            st.html(f'<div class="m-list">{items}</div>')

theme.gap()

with st.container(key="card-wards"):
    theme.card_title("All wards", "Required beds against capacity, before and after routing.", f"{len(wards)} wards")
    view = wards.assign(ward=wards[C.WARD_COL].map(ward_label))[
        ["ward", "city", "beds_required", "bed_capacity", "sent", "received", "beds_in_use", "net_deficit"]
    ].rename(columns={"ward": "Ward", "city": "City", "beds_required": "Beds needed", "bed_capacity": "Capacity",
                      "sent": "Sent", "received": "Received", "beds_in_use": "Beds in use",
                      "net_deficit": "Still short"})
    styled = view.style.apply(
        lambda row: [f"color:{RED};font-weight:700" if row["Still short"] > 0 else "" for _ in row], axis=1
    )
    st.dataframe(styled, hide_index=True, width="stretch")
    st.html(
        f'<p class="m-note">Bed capacity is an assumption: the dataset has no capacity column, so each ward\'s '
        f'capacity is its {CAPACITY_QUANTILE:.0%} percentile weekly <code>hospital_beds_required</code> '
        f'through {CAPACITY_END[:4]}, rounded up (1 to 5 beds). Beds needed are forecast cases × 0.3, the '
        'ratio in the onsite data.</p>'
    )

theme.footer(state.service().bundle.metadata)
