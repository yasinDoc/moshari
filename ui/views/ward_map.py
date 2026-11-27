"""Ward map: every dataset ward coloured by its risk tier, drawn on real ward outlines."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import state, theme
from ui.wardmap import ward_map_html

issue_date, horizon, cities = st.session_state["_controls"]
svc = state.service()
key = state.data_key()
policy = state.policy()
fc = state.forecast_all(key, issue_date, horizon, cities, policy)
target = issue_date + pd.Timedelta(weeks=horizon)

theme.header(
    "Ward map",
    f"Dengue risk by ward for the week of {state.fmt_week(target)}",
    [("event", "Issued", state.fmt_week(issue_date)), ("schedule", "Horizon", f"{horizon} weeks")],
)

with st.container(key="card-map"):
    theme.card_title("Risk on the map",
                     "Each coloured shape is a dataset ward, coloured by its risk tier that week. "
                     "Hover for expected cases, click to open its forecast.",
                     f"{len(fc)} wards")
    # st.markdown, not st.html: st.html's sanitiser strips inline <svg> in the browser.
    st.markdown(ward_map_html(fc, link=state.link_params(issue_date, horizon, cities),
                              thresholds=svc.bundle.tier_thresholds), unsafe_allow_html=True)
    st.html('<p class="m-note">How to read this: darker red means more expected cases. Start with the '
            'Critical and High wards; grey shapes are real wards that the dataset does not cover.</p>')

theme.footer(svc.bundle.metadata)
