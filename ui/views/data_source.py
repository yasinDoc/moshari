"""Data: what's loaded, and forecasting from a newer weekly file."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from moshari import config as C
from moshari.data import DataValidationError, load_dataset
from ui import state, theme

svc = state.service()
raw = svc.raw
meta = svc.bundle.metadata
uploaded = "upload" in state.data_key()

theme.header("Data", state.data_name(), [("Model trained through", meta["trained_through"])])
theme.stats([
    ("Source", "Uploaded" if uploaded else "Bundled", "weekly ward file"),
    ("Wards", f"{raw[C.WARD_COL].nunique()}", f"in {raw[C.CITY_COL].nunique()} city corporations"),
    ("Weeks", f"{raw[C.DATE_COL].nunique()}", f"from {raw[C.DATE_COL].min():%Y}"),
    ("Latest week", raw[C.DATE_COL].max().strftime("%d %b %Y"), "newest forecast can be issued here"),
])


def reset_selection() -> None:
    for k in ("issue_date", "ward"):
        st.session_state.pop(k, None)


left, right = st.columns([6, 5], gap="large")
with left:
    with st.container(key="card-upload"):
        theme.card_title("Forecast from a newer file",
                         "Upload a CSV with the same columns. It is checked before anything is forecast.")
        up = st.file_uploader("Weekly ward CSV", type=["csv"], label_visibility="collapsed")
        if up is not None:
            payload = up.getvalue()
            try:
                df = load_dataset(BytesIO(payload))
            except DataValidationError as e:
                st.error(f"This file can't be used yet. {e}")
            else:
                st.success(f"{len(df):,} rows across {df[C.WARD_COL].nunique()} wards passed every check, "
                           f"{df[C.DATE_COL].min():%d %b %Y} to {df[C.DATE_COL].max():%d %b %Y}.")
                unknown = sorted(set(df[C.CITY_COL]) - set(svc.bundle.city_categories))
                if unknown:
                    st.warning(f"New cities for the model: {', '.join(unknown)}. "
                               "Their forecasts rely on weather and ward features only.")
                if st.button("Use this file", type="primary"):
                    state.use_upload(payload, up.name)
                    reset_selection()
                    st.rerun()
        if uploaded and st.button("Back to the bundled dataset"):
            state.use_bundled()
            reset_selection()
            st.rerun()

with right:
    with st.container(key="card-checks"):
        theme.card_title("What gets checked")
        st.html(
            """<div class="m-list">
              <div class="m-row" style="grid-template-columns:1fr"><div><div class="w">Columns</div>
                <div class="c">All 12 required columns are present and readable</div></div></div>
              <div class="m-row" style="grid-template-columns:1fr"><div><div class="w">Ranges</div>
                <div class="c">Rain, temperature, humidity and ward scores are physically plausible</div></div></div>
              <div class="m-row" style="grid-template-columns:1fr"><div><div class="w">Continuity</div>
                <div class="c">One row per ward per week, no duplicates or gaps, 9+ weeks of history</div></div></div>
            </div>"""
        )

st.html('<div style="height:1.4rem"></div>')
with st.expander("Column reference"):
    schema = pd.DataFrame(
        [
            ("date", "Monday of the week, YYYY-MM-DD", "consecutive weeks per ward"),
            ("city", "City corporation name", "text"),
            ("ward_id", "Ward identifier, e.g. DNCC_Ward_07", "text"),
            *[(c, "Ward characteristic", f"{lo:g} to {hi:g}") for c, (lo, hi) in C.VALID_RANGES.items() if c in C.STATIC_COLS],
            *[(c, "Weekly weather", f"{lo:g} to {hi:g}") for c, (lo, hi) in C.VALID_RANGES.items() if c in C.WEATHER_COLS],
            ("dengue_cases", "Cases reported that week", "0 or more"),
        ],
        columns=["Column", "Meaning", "Accepted values"],
    )
    st.dataframe(schema, hide_index=True, use_container_width=True)
