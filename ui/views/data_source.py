"""Data: what's loaded, and forecasting from a newer weekly file."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from moshari import config as C
from moshari.data import DataValidationError, load_dataset
from ui import i18n, state, theme

T, tr, num, BN = i18n.t, i18n.tr, i18n.num, i18n.is_bn()

# Bangla versions of moshari.data's validation messages (same order as the checks there).
_BN_ERRORS = [
    (r"Missing required column\(s\): (.+)", "দরকারি কলাম নেই: {0}"),
    (r"Some rows have an unreadable `date`.*", "কিছু সারিতে `date` পড়া যাচ্ছে না (বছর-মাস-দিন আকারে দরকার)।"),
    (r"Non-numeric or empty values in: (.+)", "সংখ্যা নয় বা খালি মান আছে: {0}"),
    (r"`(\w+)` has (\d+) value\(s\) outside the plausible range \[(.+), (.+)\]\.",
     "`{0}`-এ {1}টি মান সম্ভাব্য সীমার [{2}, {3}] বাইরে।"),
    (r"(\d+) duplicate \(ward_id, date\) rows found\.", "{0}টি সারি একই (ward_id, date) নিয়ে দুবার আছে।"),
    (r"Each ward must have consecutive weekly rows.*",
     "পেছনের সপ্তাহের বৈশিষ্ট্য ঠিক রাখতে প্রতিটি ওয়ার্ডের সারি টানা প্রতি সপ্তাহে (৭ দিন পরপর) থাকতে হবে।"),
]


def _error_text(msg: str) -> str:
    """A validation message in the page language; column names stay as the file must spell them."""
    if not BN:
        return msg
    import re

    for pattern, bangla in _BN_ERRORS:
        m = re.fullmatch(pattern, msg)
        if m:
            return bangla.format(*(i18n.digits(g) for g in m.groups()))
    return T("The file did not pass the checks.")

svc = state.service()
raw = svc.raw
meta = svc.bundle.metadata
uploaded = "upload" in state.data_key()

theme.header(T("Data"), state.data_name(),
             [("model_training", T("Model trained through"), tr(meta["trained_through"]))])
theme.stats([
    ("inventory_2", T("Source"), T("Uploaded" if uploaded else "Bundled"), T("weekly ward file")),
    ("map", T("Wards"), num(raw[C.WARD_COL].nunique()), T("in {n} city corporations", n=raw[C.CITY_COL].nunique())),
    ("date_range", T("Weeks"), num(raw[C.DATE_COL].nunique()), T("since {year}", year=raw[C.DATE_COL].min().year)),
    ("update", T("Latest week"), i18n.week(raw[C.DATE_COL].max()), T("newest week a forecast can use")),
])


def reset_selection() -> None:
    for k in ("issue_date", "ward"):
        st.session_state.pop(k, None)


left, right = st.columns([3, 2])
with left:
    with st.container(key="card-upload"):
        theme.card_title(T("Forecast from a newer file"),
                         T("Upload a CSV with the same columns. It's checked before anything is forecast."))
        up = st.file_uploader(T("Weekly ward CSV"), type=["csv"], label_visibility="collapsed")
        if up is not None:
            payload = up.getvalue()
            try:
                df = load_dataset(BytesIO(payload))
            except DataValidationError as e:
                st.error(T("This file can't be used yet. {reason}", reason=_error_text(str(e))))
            else:
                st.success(T("{rows:,} rows across {wards} wards passed every check, {start} to {end}.",
                             rows=len(df), wards=df[C.WARD_COL].nunique(), start=i18n.week(df[C.DATE_COL].min()),
                             end=i18n.week(df[C.DATE_COL].max())))
                unknown = sorted(set(df[C.CITY_COL]) - set(svc.bundle.city_categories))
                if unknown:
                    st.warning(T("New cities for the model: {cities}. Their forecasts rely on weather and ward "
                                 "features only.", cities=", ".join(unknown)))
                if st.button(T("Use this file"), type="primary", icon=":material/check:"):
                    state.use_upload(payload, up.name)
                    reset_selection()
                    st.rerun()
        if uploaded and st.button(T("Back to the bundled dataset"), icon=":material/undo:"):
            state.use_bundled()
            reset_selection()
            st.rerun()

with right:
    with st.container(key="card-checks"):
        theme.card_title(T("What gets checked"))
        checks = [
            ("view_column", "Columns", "All 12 required columns are present and readable"),
            ("rule", "Ranges", "Rain, temperature, humidity and ward scores are physically plausible"),
            ("timeline", "Continuity", "One row per ward per week, no duplicates or gaps, 9+ weeks of history"),
        ]
        st.html('<div class="m-list">' + "".join(
            f'<div class="m-row"><div class="n">{theme.icon(i)}</div><div><div class="w">{T(t)}</div>'
            f'<div class="c">{T(d)}</div></div><div></div></div>' for i, t, d in checks) + "</div>")

theme.gap()
with st.expander(T("Column reference"), icon=":material/table_view:"):
    schema = pd.DataFrame(
        [
            ("date", "Monday of the week, YYYY-MM-DD", "consecutive weeks per ward"),
            ("city", "City corporation name", "text"),
            ("ward_id", "Ward identifier, e.g. DNCC_Ward_07", "text"),
            *[(c, "Ward characteristic", T("{a:g} to {b:g}", a=lo, b=hi)) for c, (lo, hi) in C.VALID_RANGES.items() if c in C.STATIC_COLS],
            *[(c, "Weekly weather", T("{a:g} to {b:g}", a=lo, b=hi)) for c, (lo, hi) in C.VALID_RANGES.items() if c in C.WEATHER_COLS],
            ("dengue_cases", "Cases reported that week", "0 or more"),
        ],
        columns=["Column", "Meaning", "Accepted values"],
    )
    if BN:
        # "date" and "city" are the only column names without an underscore; they read as English words,
        # so the Bangla table names them in Bangla, and their Bangla meanings say the file keeps the English name.
        schema["Column"] = schema["Column"].map(lambda c: T(c) if "_" not in c else c)
    schema, schema_cfg = i18n.frame(schema)
    st.dataframe(schema, hide_index=True, width="stretch", column_config=schema_cfg)

theme.footer(meta)
