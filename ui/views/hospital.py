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
    FALLBACK_BEDS_PER_CASE,
    beds_from_forecast,
    beds_to_clear,
    load_bed_capacity,
    plain_summary,
    route_overflow,
    with_surge,
)
from ui import state, theme

try:  # the allocation engine is a teammate's module; fall back to the fitted ratio without it
    from moshari.allocation import allocate, demand_ratios
except ImportError:  # pragma: no cover
    allocate = demand_ratios = None

RED = theme.TIER_COLORS["Critical"]
bed_ratio = demand_ratios().ratios["hospital_beds_required"] if demand_ratios else FALLBACK_BEDS_PER_CASE
AMBER = theme.TIER_COLORS["High"]
GREEN = theme.TIER_COLORS["Low"]
ALL = "All cities"

issue_date, horizon, cities = st.session_state["_controls"]
key = state.data_key()
policy = state.policy()
target = issue_date + pd.Timedelta(weeks=horizon)


@st.cache_data(show_spinner=False)
def bed_capacity() -> pd.Series:
    return load_bed_capacity()


@st.cache_data(show_spinner=False, max_entries=256)
def routed(key: str, issue_date: pd.Timestamp, horizon: int, cities: tuple[str, ...], policy: str,
           surge_pct: int):
    fc = state.forecast_all(key, issue_date, horizon, cities, policy)
    # Bed demand per ward from the allocation engine, the same numbers the
    # Resources and Dispatch pages use. Beds are routed as *required*: stock
    # scarcity doesn't apply to beds, ward capacity does.
    alloc = allocate(fc, state.service().wards) if allocate else beds_from_forecast(fc)
    return tuple(route_overflow(alloc, with_surge(bed_capacity(), surge_pct)))


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def _util_color(u: float) -> str:
    return RED if u > 1 else (AMBER if u > 0.85 else theme.ACCENT)


def _bar(u: float) -> str:
    """Utilisation bar; anything over 100% shows full and red."""
    pct = min(u, 1.0) * 100 if u == u else 0
    return (f'<div style="height:8px;border-radius:99px;background:{theme.LINE};margin:10px 0 8px;overflow:hidden">'
            f'<div style="width:{pct:.0f}%;height:100%;background:{_util_color(u)};border-radius:99px"></div></div>')


theme.header(
    "Hospital beds",
    f"Bed demand and overflow transfers for the week of {state.fmt_week(target)}",
    [("event", "Issued", state.fmt_week(issue_date)), ("schedule", "Horizon", f"{horizon} weeks")],
)

# --------------------------------------------------------------------------- controls
c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
surge = c1.slider(
    "Surge beds per ward", min_value=0, max_value=100, step=10, value=0, format="+%d%%", key="hosp_surge",
    help="What if wards open extra corridor or field beds? 0% is normal capacity. Extra beds are rounded down, "
         "so the plan never counts a bed that isn't there.",
)

try:
    transfers, wards, city_tbl = routed(key, issue_date, horizon, cities, policy, surge)
except (FileNotFoundError, ValueError) as exc:
    st.error(f"Hospital routing is unavailable: {exc}")
    st.stop()

city_names = list(city_tbl["city"])
focus = c2.selectbox("Show", [ALL, *city_names], key="hosp_city",
                     help="Narrow the transfers and ward lists to one city corporation.")

# --------------------------------------------------------------------------- headline
short_all = wards[wards["net_deficit"] > 0]
over_before = int((wards["beds_required"] > wards["bed_capacity"]).sum())
need_more = beds_to_clear(city_tbl)
theme.stats([
    ("local_hospital", "Beds available", f"{int(wards['bed_capacity'].sum()):,}",
     f"across {len(wards)} wards" + (f", including +{surge}% surge" if surge else ", normal capacity")),
    ("hotel", "Beds needed", f"{int(wards['beds_required'].sum()):,}",
     f"{_plural(over_before, 'ward')} over their own capacity"),
    ("swap_horiz", "Patients moved", f"{int(transfers['patients'].sum()):,}",
     f"in {_plural(len(transfers), 'transfer')}, always within the same city"),
    ("warning", "Still short",
     f"<span style='color:{RED if len(short_all) else theme.INK}'>{len(short_all)}</span><small> wards</small>",
     f"{need_more} more beds would cover everyone" if need_more else "every patient has a bed in their city"),
])

# Plain-language verdict, worst city first: the part an officer reads in five seconds.
lines = plain_summary(city_tbl)
if not lines:
    st.info("No wards match the current filters.")
    st.stop()
if need_more:
    tone, icon = RED, "error"
    lead = (f"<b>{_plural(len(short_all), 'ward')} will run out of beds.</b> Routing inside each city places "
            f"{int(transfers['patients'].sum())} patients, but {need_more} still need a bed. Try the surge slider "
            "to see how many extra beds would close the gap.")
elif len(transfers):
    tone, icon = AMBER, "swap_horiz"
    lead = (f"<b>Every patient can be placed</b> by moving {_plural(int(transfers['patients'].sum()), 'patient')} "
            "between wards of the same city.")
else:
    tone, icon = theme.ACCENT, "check_circle"
    lead = "<b>No ward needs more beds than it has this week.</b> Choose a later week or a longer horizon in " \
           "the sidebar to see a busier one."
bullets = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
st.html(
    f'<div style="border-left:4px solid {tone};background:{theme.BASE_HI};border-radius:12px;padding:14px 18px;'
    f'margin:4px 0 8px;color:{theme.INK}">'
    f'<div style="display:flex;gap:10px;align-items:flex-start">{theme.icon(icon)}<div>{lead}'
    f'<ul style="margin:8px 0 0 18px;padding:0;color:{theme.INK_2};font-size:14px;line-height:1.6">{bullets}</ul>'
    f'</div></div></div>'
)

# --------------------------------------------------------------------------- city cards
with st.container(key="card-cities"):
    theme.card_title("Beds by city", "Overflow can only move between wards of the same city corporation.",
                     f"{len(city_tbl)} cit{'y' if len(city_tbl) == 1 else 'ies'}")
    cards = []
    for r in city_tbl.itertuples():
        u = r.utilization
        dim = "" if focus in (ALL, r.city) else "opacity:.45;"
        head_col = RED if r.headroom < 0 else theme.INK
        status = (f'<b style="color:{RED}">{r.unplaced} without a bed</b>' if r.unplaced else
                  f"{_plural(int(r.patients_moved), 'patient')} moved" if r.patients_moved else "No transfers needed")
        cards.append(
            f'<div class="m-stat" style="{dim}"><div class="top"><span class="k">{html.escape(r.city)}</span></div>'
            f'<div class="v" style="color:{_util_color(u)}">{u:.0%}<small> used</small></div>{_bar(u)}'
            f'<div class="s">{r.total_required:,} needed of {r.total_capacity:,} beds<br>'
            f'Headroom <b style="color:{head_col}">{r.headroom:+,}</b><br>{status}</div></div>'
        )
    st.html('<div class="m-stats" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr))">'
            f'{"".join(cards)}</div>')

theme.gap()

# --------------------------------------------------------------------------- transfers and deficits
show_t = transfers if focus == ALL else transfers[transfers["city"] == focus]
show_w = wards if focus == ALL else wards[wards["city"] == focus]
short = show_w[show_w["net_deficit"] > 0].sort_values(["net_deficit", C.WARD_COL], ascending=[False, True])
where = "" if focus == ALL else f" in {focus}"

left, right = st.columns([7, 5])
with left:
    with st.container(key="card-transfers"):
        theme.card_title("Transfers", "Each overflow ward fills the least loaded ward first, then the nearest by "
                         "ward number.", _plural(len(show_t), "move"))
        if show_t.empty:
            msg = (f"No ward{where} needs more beds than it has." if short.empty else
                   f"No transfers are possible{where}: there are no spare beds left to move patients to.")
            st.html(f'<p class="m-note">{msg}</p>')
        else:
            items = "".join(
                f'<div class="m-row"><div class="n">{i}</div><div><div class="w">'
                f'{html.escape(ward_label(t.from_ward))} {theme.icon("arrow_forward")} '
                f'{html.escape(ward_label(t.to_ward))}</div><div class="c">{html.escape(t.city)}: move '
                f'{_plural(t.patients, "patient")}</div></div>'
                f'<div class="e">{t.patients}<small>patient{"" if t.patients == 1 else "s"}</small></div></div>'
                for i, t in enumerate(show_t.itertuples(), 1)
            )
            box = st.container(height=520) if len(show_t) > 7 else st.container()
            box.html(f'<div class="m-list">{items}</div>')
            plan = show_t.assign(from_ward=show_t["from_ward"].map(ward_label), to_ward=show_t["to_ward"].map(ward_label))
            st.download_button("Download transfer list (CSV)", plan.to_csv(index=False).encode("utf-8"),
                               file_name=f"moshari_transfers_{target:%Y-%m-%d}.csv", mime="text/csv",
                               icon=":material/download:", width="stretch")

with right:
    with st.container(key="card-deficit"):
        theme.card_title("Still short after routing", "These wards' cities have no spare beds left.",
                         _plural(len(short), "ward"))
        if short.empty:
            st.html(f'<p class="m-note">None{where}. Every patient has a bed within their own city.</p>')
        else:
            items = "".join(
                f'<div class="m-row"><div class="n" style="color:{RED}">!</div><div>'
                f'<div class="w" style="color:{RED}">{html.escape(ward_label(r.ward_id))}</div>'
                f'<div class="c">{html.escape(r.city)}: needs {r.beds_required}, has {r.bed_capacity}</div></div>'
                f'<div class="e" style="color:{RED}">{r.net_deficit}<small>bed{"" if r.net_deficit == 1 else "s"} '
                f'short</small></div></div>'
                for r in short.itertuples()
            )
            box = st.container(height=520) if len(short) > 7 else st.container()
            box.html(f'<div class="m-list">{items}</div>')

theme.gap()

# --------------------------------------------------------------------------- ward table
with st.container(key="card-wards"):
    theme.card_title("All wards", "Beds needed against capacity, before and after routing. Click a column to sort.",
                     _plural(len(show_w), "ward"))


    def _status(r) -> str:
        if r.net_deficit:
            return "Short"
        if r.sent:
            return "Sent"
        if r.received:
            return "Received"
        return "OK"

    view = pd.DataFrame({
        "Ward": show_w[C.WARD_COL].map(ward_label),
        "City": show_w["city"],
        "Status": [_status(r) for r in show_w.itertuples()],
        "Beds needed": show_w["beds_required"],
        "Capacity": show_w["bed_capacity"],
        "Sent": show_w["sent"],
        "Received": show_w["received"],
        "In use": (show_w["beds_in_use"] / show_w["bed_capacity"].where(show_w["bed_capacity"] > 0)).fillna(0) * 100,
        "Still short": show_w["net_deficit"],
    })
    styled = view.style.apply(
        lambda row: [f"color:{RED};font-weight:700" if row["Still short"] > 0 else "" for _ in row], axis=1
    )
    st.dataframe(
        styled, hide_index=True, width="stretch",
        column_config={
            "In use": st.column_config.ProgressColumn("In use", format="%.0f%%", min_value=0, max_value=100,
                                                      help="Share of the ward's beds in use after routing."),
            "Still short": st.column_config.NumberColumn(help="Patients with no bed left anywhere in the city."),
        },
    )
    st.download_button("Download ward summary (CSV)", show_w.to_csv(index=False).encode("utf-8"),
                       file_name=f"moshari_bed_summary_{target:%Y-%m-%d}.csv", mime="text/csv",
                       icon=":material/download:")
    with st.expander("Where do these numbers come from?"):
        st.markdown(
            f"- **Capacity** is an estimate. The dataset has no bed-capacity column, so each ward's normal capacity is "
            f"its {CAPACITY_QUANTILE:.0%} percentile weekly `hospital_beds_required` from 2016 to {CAPACITY_END[:4]}, "
            "rounded up (1 to 5 beds). That is what the ward handles in a bad but normal week.\n"
            f"- **Beds needed** are forecast cases × {bed_ratio:.3f} beds per case, fitted from the onsite data, "
            "rounded up. They come from the allocation engine, so they match the Resources and Dispatch pages.\n"
            "- **Routing** never crosses city corporations. The ward with the most overflow goes first and fills the "
            "least loaded ward with spare beds, then the nearest by ward number.\n"
            "- Everything runs on this computer, with no internet."
        )

theme.footer(state.service().bundle.metadata)
