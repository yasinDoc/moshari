"""Moshari (মশারি) — ward-level dengue early warning.

    streamlit run app.py
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT / "src", ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import streamlit as st  # noqa: E402

LOGO = ROOT / "assets" / "logo.svg"

st.set_page_config(
    page_title="Moshari dengue early warning",
    page_icon=str(LOGO),
    layout="wide",
    initial_sidebar_state="auto",
)

from ui import theme  # noqa: E402
from ui.state import controls  # noqa: E402

theme.inject_css()

logo_b64 = base64.b64encode(LOGO.read_bytes()).decode()
with st.sidebar:
    st.html(
        f"""
        <div class="m-brand">
          <img src="data:image/svg+xml;base64,{logo_b64}" alt="">
          <div><div class="name">Moshari</div><div class="bn">মশারি</div></div>
        </div>
        <p class="m-brand-tag">Dengue early warning for every ward in Dhaka, Chattogram, Gazipur and Narayanganj.</p>
        """
    )

pages = [
    st.Page("ui/views/ward_net.py", title="Ward risk net", default=True),
    st.Page("ui/views/ward_forecast.py", title="Ward forecast"),
    st.Page("ui/views/model_check.py", title="How accurate is it?"),
    st.Page("ui/views/data_source.py", title="Data source"),
]
nav = st.navigation(pages, position="top")
st.session_state["_controls"] = controls()

with st.sidebar:
    st.caption("Forecasts run locally from a saved model. No external API calls.")

nav.run()
