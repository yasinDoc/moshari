"""Data source: see what's loaded, or run Moshari on a newer weekly file."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from moshari import config as C
from moshari.data import DataValidationError, load_dataset
from ui import state

svc = state.service()
raw = svc.raw
meta = svc.bundle.metadata

st.html('<p class="m-lede">Forecasts use the weekly ward file below. Upload a newer one with the same '
        'columns to forecast from the latest week.</p>')

c1, c2, c3, c4 = st.columns(4)
c1.metric("Source", "Uploaded" if "upload" in state.data_key() else "Bundled")
c2.metric("Wards", f"{raw[C.WARD_COL].nunique()}")
c3.metric("Weeks", f"{raw[C.DATE_COL].nunique()}")
c4.metric("Latest week", raw[C.DATE_COL].max().strftime("%d %b %Y"))
st.caption(f"{state.data_name()}. Model trained through {meta['trained_through']} "
           f"on {meta['data_rows']:,} rows with LightGBM {meta['lightgbm_version']}.")

st.subheader("Upload a weekly file")
up = st.file_uploader("CSV with one row per ward per week", type=["csv"])
if up is not None:
    payload = up.getvalue()
    try:
        df = load_dataset(BytesIO(payload))
    except DataValidationError as e:
        st.error(f"This file can't be used yet. {e}")
    else:
        st.success(f"{len(df):,} rows across {df[C.WARD_COL].nunique()} wards passed validation, "
                   f"{df[C.DATE_COL].min():%d %b %Y} to {df[C.DATE_COL].max():%d %b %Y}.")
        unknown = sorted(set(df[C.CITY_COL]) - set(svc.bundle.city_categories))
        if unknown:
            st.warning(f"The model has not seen these cities before: {', '.join(unknown)}. "
                       "Their forecasts rely on weather and ward features only.")
        if st.button("Forecast from this file", type="primary"):
            state.use_upload(payload, up.name)
            for k in ("issue_date", "ward"):
                st.session_state.pop(k, None)
            st.rerun()

if "upload" in state.data_key() and st.button("Switch back to the bundled dataset"):
    state.use_bundled()
    for k in ("issue_date", "ward"):
        st.session_state.pop(k, None)
    st.rerun()

st.subheader("Expected columns")
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
st.caption("Files are checked for missing columns, unreadable values, implausible ranges, duplicate rows and "
           "gaps between weeks before anything is forecast. Each ward needs at least 9 weeks of history.")
