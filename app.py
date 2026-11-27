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

# Faster cold start: the dashboard only runs inference, but importing LightGBM also
# imports scikit-learn (~4 s) for wrappers Moshari never uses here. Marking it
# unavailable in this process makes LightGBM skip it. Training and tests run in
# their own processes and are unaffected.
sys.modules.setdefault("sklearn", None)

import streamlit as st  # noqa: E402

LOGO = ROOT / "assets" / "logo.svg"

st.set_page_config(
    page_title="Moshari dengue early warning",
    page_icon=str(LOGO),
    layout="wide",
    initial_sidebar_state="auto",
)

from ui import i18n, state, theme  # noqa: E402

state.apply_lang_param()
theme.inject_css(i18n.lang())
T = i18n.t

PAGES = [
    # operations workflow: see risk -> allocate supplies -> place patients -> deploy crews -> notify
    st.Page("ui/views/ward_net.py", title="Overview", icon=":material/space_dashboard:", default=True),
    st.Page("ui/views/ward_map.py", title="Ward map", icon=":material/map:"),
    st.Page("ui/views/resources.py", title="Resources", icon=":material/inventory_2:"),
    st.Page("ui/views/hospital.py", title="Hospital beds", icon=":material/local_hospital:"),
    st.Page("ui/views/simulator.py", title="Simulator", icon=":material/science:"),
    st.Page("ui/views/dispatch.py", title="Dispatch", icon=":material/campaign:"),
    st.Page("ui/views/briefing.py", title="Weekly briefing", icon=":material/summarize:"),
    # forecasting and evidence
    st.Page("ui/views/live.py", title="Live outlook", icon=":material/cloud:"),
    st.Page("ui/views/ward_forecast.py", title="Ward forecast", icon=":material/monitoring:"),
    st.Page("ui/views/model_check.py", title="Model accuracy", icon=":material/verified:"),
    st.Page("ui/views/data_source.py", title="Data", icon=":material/database:"),
]
nav = st.navigation(PAGES, position="hidden")

logo_b64 = base64.b64encode(LOGO.read_bytes()).decode()
with st.sidebar:
    state.language_switch()
    st.html(
        f"""<div class="m-brand">
              <div class="mark"><img src="data:image/svg+xml;base64,{logo_b64}" alt=""></div>
              <div><div class="name">Moshari</div><div class="bn">মশারি</div></div>
            </div>"""
    )
    for page in PAGES:
        key = "nav-current" if page.title == nav.title else f"nav-{page.url_path or 'home'}"
        with st.container(key=key):
            st.page_link(page, label=T(page.title), icon=page.icon)

    st.html(f'<div class="m-side-label">{T("Forecast settings")}</div>')
    st.session_state["_controls"] = state.settings()

    svc = state.service()
    meta = svc.bundle.metadata
    st.html(
        f"""<div class="m-status">
              <div class="r"><span class="live"></span>{T("Model ready (offline)" if state.is_offline() else "Model ready")}</div>
              <dl>
                <dt>{T("Trained through")}</dt><dd>{i18n.tr(meta.get('trained_through', 'unknown'))}</dd>
                <dt>{T("Data to")}</dt><dd>{i18n.week(svc.raw['date'].max())}</dd>
                <dt>{T("Wards")}</dt><dd>{i18n.num(len(svc.wards))}</dd>
                <dt>{T("Mode")}</dt><dd>{T("Offline" if state.is_offline() else "Online")}</dd>
                <dt>{T("Needs internet")}</dt><dd>{T("No")}</dd>
              </dl>
            </div>"""
    )

nav.run()
