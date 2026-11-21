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

theme.header("Data", state.data_name(),
             [("model_training", "Model trained through", meta["trained_through"])])
theme.stats([
    ("inventory_2", "Source", "Uploaded" if uploaded else "Bundled", "weekly ward file"),
    ("map", "Wards", f"{raw[C.WARD_COL].nunique()}", f"in {raw[C.CITY_COL].nunique()} city corporations"),
    ("date_range", "Weeks", f"{raw[C.DATE_COL].nunique()}", f"since {raw[C.DATE_COL].min():%Y}"),
    ("update", "Latest week", raw[C.DATE_COL].max().strftime("%d %b %Y"), "newest week a forecast can use"),
])


def reset_selection() -> None:
    for k in ("issue_date", "ward"):
        st.session_state.pop(k, None)


left, right = st.columns([3, 2])
with left:
    with st.container(key="card-upload"):
        theme.card_title("Forecast from a newer file",
                         "Upload a CSV with the same columns. It's checked before anything is forecast.")
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
                if st.button("Use this file", type="primary", icon=":material/check:"):
                    state.use_upload(payload, up.name)
                    reset_selection()
                    st.rerun()
        if uploaded and st.button("Back to the bundled dataset", icon=":material/undo:"):
            state.use_bundled()
            reset_selection()
            st.rerun()

with right:
    with st.container(key="card-checks"):
        theme.card_title("What gets checked")
        checks = [
            ("view_column", "Columns", "All 12 required columns are present and readable"),
            ("rule", "Ranges", "Rain, temperature, humidity and ward scores are physically plausible"),
            ("timeline", "Continuity", "One row per ward per week, no duplicates or gaps, 9+ weeks of history"),
        ]
        st.html('<div class="m-list">' + "".join(
            f'<div class="m-row"><div class="n">{theme.icon(i)}</div><div><div class="w">{t}</div>'
            f'<div class="c">{d}</div></div><div></div></div>' for i, t, d in checks) + "</div>")

theme.gap()
with st.expander("Column reference", icon=":material/table_view:"):
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
    st.dataframe(schema, hide_index=True, width="stretch")

theme.footer(meta)
