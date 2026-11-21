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
from ui.state import settings  # noqa: E402

theme.inject_css()

PAGES = [
    st.Page("ui/views/ward_net.py", title="Ward overview", icon=":material/grid_view:", default=True),
    st.Page("ui/views/ward_forecast.py", title="Ward forecast", icon=":material/monitoring:"),
    st.Page("ui/views/model_check.py", title="Model accuracy", icon=":material/verified:"),
    st.Page("ui/views/data_source.py", title="Data", icon=":material/database:"),
]
nav = st.navigation(PAGES, position="hidden")

logo_b64 = base64.b64encode(LOGO.read_bytes()).decode()
with st.sidebar:
    st.html(
        f"""<div class="m-brand">
              <div class="mark"><img src="data:image/svg+xml;base64,{logo_b64}" alt=""></div>
              <div><div class="name">Moshari</div><div class="bn">মশারি</div></div>
            </div>"""
    )
    for page in PAGES:
        key = "nav-current" if page.title == nav.title else f"nav-{page.url_path or 'home'}"
        with st.container(key=key):
            st.page_link(page, label=page.title, icon=page.icon)
    st.html('<div class="m-side-label">Forecast settings</div>')
    st.session_state["_controls"] = settings()
    st.html('<p class="m-foot">Runs locally from a saved model.<br>No external API calls.</p>')

nav.run()
