"""Moshari design system: soft neumorphism on a vanilla base.

Every surface is cut from the same vanilla-grey material. Cards are extruded
from it with a pair of shadows (light from the top-left, shade to the
bottom-right); inputs and trays are pressed into it. Risk tiers are the only
saturated colours on screen, so they always read as signal.
"""

from __future__ import annotations

from string import Template

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from moshari.risk import TIERS

# --------------------------------------------------------------------------- tokens
BASE = "#ECE8DF"        # vanilla-grey material everything is cut from
BASE_HI = "#F7F3EA"     # slightly lifted vanilla, used for pressed-in highlights
LIGHT = "#FFFFFF"       # top-left light
SHADE = "rgba(170,158,134,0.42)"  # bottom-right shade
INK = "#262E38"
MUTED = "#7B7F84"
LINE = "rgba(120,110,90,0.14)"
ACCENT = "#11756D"      # lagoon teal: interactive elements only
RAIN = "#6C9BC2"

TIER_COLORS = {name: t.color for name, t in TIERS.items()}
TIER_TEXT = {"Low": "#FFFFFF", "Medium": "#3A2E00", "High": "#FFFFFF", "Critical": "#FFFFFF"}

FONT = "Manrope, 'Segoe UI', system-ui, -apple-system, sans-serif"
FONT_BN = "'Hind Siliguri', 'Noto Sans Bengali', Vrinda, sans-serif"

_CSS = Template(r"""
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Hind+Siliguri:wght@600;700&display=swap');

:root{
  --base:$BASE; --base-hi:$BASE_HI; --light:$LIGHT; --shade:$SHADE; --ink:$INK; --muted:$MUTED;
  --line:$LINE; --accent:$ACCENT;
  --raise: 7px 7px 16px var(--shade), -7px -7px 16px var(--light);
  --raise-sm: 4px 4px 9px var(--shade), -4px -4px 9px var(--light);
  --press: inset 4px 4px 9px var(--shade), inset -4px -4px 9px var(--light);
  --press-sm: inset 2px 2px 5px var(--shade), inset -2px -2px 5px var(--light);
  --r-lg: 22px; --r-md: 16px; --r-sm: 12px;
}

/* ------------------------------------------------------------ canvas */
html, body, .stApp, p, label, li, td, th, input, textarea, button, select { font-family:$FONT; }
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { background:var(--base) !important; color:var(--ink); }
[data-testid="stHeader"] { background:transparent !important; }
[data-testid="stMainBlockContainer"], .block-container { padding:3.4rem 2.4rem 4rem !important; max-width:1280px; }
h1,h2,h3,h4,h5 { font-family:$FONT !important; color:var(--ink) !important; letter-spacing:-0.02em; }
p, li { color:var(--ink); }
[data-testid="stIconMaterial"] { font-family:'Material Symbols Rounded' !important; }
:focus-visible { outline:2px solid var(--accent) !important; outline-offset:3px; }
[data-testid="stDecoration"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"] { display:none; }

/* ------------------------------------------------------------ sidebar */
[data-testid="stSidebar"] { background:var(--base) !important; border:none !important;
  box-shadow: 8px 0 22px -10px var(--shade); }
[data-testid="stSidebar"] > div:first-child { background:var(--base); }
[data-testid="stSidebarContent"] { padding-top:.4rem; }
[data-testid="stSidebarHeader"] { height:2.2rem; padding:0; }
.m-brand { display:flex; align-items:center; gap:.8rem; padding:.2rem .2rem 1.4rem; }
.m-brand .mark { width:52px; height:52px; border-radius:16px; background:var(--base); box-shadow:var(--raise-sm);
  display:grid; place-items:center; }
.m-brand .mark img { width:36px; height:36px; }
.m-brand .name { font-weight:800; font-size:1.3rem; line-height:1; color:var(--ink); }
.m-brand .bn { font-family:$FONT_BN; font-weight:700; font-size:1rem; color:var(--accent); line-height:1.3; }
.m-side-label { font-size:.78rem; font-weight:700; color:var(--muted); margin:1.3rem .3rem .55rem; letter-spacing:.02em; }

/* page links: raised pills, current page pressed in */
[data-testid="stSidebar"] [data-testid="stPageLink"] { margin-bottom:.55rem; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {
  background:var(--base); border-radius:var(--r-sm); box-shadow:var(--raise-sm); padding:.62rem .9rem;
  transition: box-shadow .18s ease; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover { box-shadow:var(--press-sm); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p { font-weight:600; font-size:.95rem; color:var(--ink); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] span[data-testid="stIconMaterial"] { color:var(--muted); }
[data-testid="stSidebar"] .st-key-nav-current [data-testid="stPageLink-NavLink"] {
  box-shadow:var(--press); background:var(--base-hi); }
[data-testid="stSidebar"] .st-key-nav-current [data-testid="stPageLink-NavLink"] p,
[data-testid="stSidebar"] .st-key-nav-current span[data-testid="stIconMaterial"] { color:var(--accent); }

.st-key-settings { background:var(--base); border-radius:var(--r-md); box-shadow:var(--press);
  padding:1rem .95rem .6rem; }
.m-foot { font-size:.78rem; color:var(--muted); line-height:1.5; margin:1.2rem .3rem 0; }

/* ------------------------------------------------------------ cards */
[class*="st-key-card"] { background:var(--base); border-radius:var(--r-lg); box-shadow:var(--raise);
  padding:1.35rem 1.5rem 1.2rem; }
[class*="st-key-card"] h3 { font-size:1.08rem; font-weight:700; margin:0 0 .15rem; padding:0; }
.m-sub { color:var(--muted); font-size:.85rem; margin:0 0 .9rem; line-height:1.45; }
[class*="st-key-tray"] { background:var(--base); border-radius:var(--r-md); box-shadow:var(--press); padding:1rem; }

/* page header */
.m-head { display:flex; justify-content:space-between; align-items:flex-end; gap:1rem; flex-wrap:wrap; margin-bottom:1.5rem; }
.m-head h1 { font-size:1.75rem; font-weight:800; margin:0; padding:0; line-height:1.15; }
.m-head p { margin:.3rem 0 0; color:var(--muted); font-size:.92rem; }
.m-chips { display:flex; gap:.6rem; flex-wrap:wrap; }
.m-chip { background:var(--base); box-shadow:var(--raise-sm); border-radius:999px; padding:.42rem .9rem;
  font-size:.84rem; font-weight:600; color:var(--ink); white-space:nowrap; }
.m-chip b { color:var(--accent); font-weight:700; }

/* stat tiles */
.m-stats { display:grid; grid-template-columns:repeat(auto-fit, minmax(190px,1fr)); gap:1.3rem; margin-bottom:1.6rem; }
.m-stat { background:var(--base); border-radius:var(--r-lg); box-shadow:var(--raise); padding:1.05rem 1.25rem; }
.m-stat .k { font-size:.82rem; color:var(--muted); font-weight:600; }
.m-stat .v { font-size:1.9rem; font-weight:800; line-height:1.15; margin-top:.25rem; color:var(--ink); }
.m-stat .s { font-size:.8rem; color:var(--muted); margin-top:.1rem; }
.m-dot { display:inline-block; width:.6rem; height:.6rem; border-radius:50%; margin-right:.4rem; vertical-align:1px; }

/* tier badge */
.m-badge { display:inline-block; border-radius:999px; padding:.22rem .75rem; font-size:.8rem; font-weight:700; }

/* ------------------------------------------------------------ ward net */
.m-net { display:grid; grid-template-columns:repeat(auto-fit, minmax(250px,1fr)); gap:1.4rem 1.6rem; }
.m-corp .t { font-weight:700; font-size:.95rem; }
.m-corp .s { color:var(--muted); font-size:.8rem; margin:.1rem 0 .65rem; }
.m-tray { background:var(--base); border-radius:var(--r-md); box-shadow:var(--press); padding:.6rem;
  display:grid; grid-template-columns:repeat(5,1fr); gap:.5rem; }
.m-cell { border-radius:10px; padding:.42rem .3rem .38rem; text-align:center; box-shadow:var(--raise-sm); position:relative; }
.m-cell .w { font-size:.68rem; font-weight:600; opacity:.85; }
.m-cell .v { font-size:1.02rem; font-weight:800; line-height:1.15; }
.m-cell.up::after { content:""; position:absolute; top:5px; right:5px; width:6px; height:6px; border-radius:50%;
  background:#fff; box-shadow:0 0 0 2px $CRIT; }
.m-legend { display:flex; flex-wrap:wrap; gap:.5rem 1.3rem; font-size:.8rem; color:var(--muted); margin-top:1.1rem; }

/* dispatch list */
.m-list { display:flex; flex-direction:column; gap:.6rem; }
.m-row { display:grid; grid-template-columns:1.6rem 1fr auto; align-items:center; gap:.8rem; padding:.62rem .8rem;
  border-radius:var(--r-sm); background:var(--base); box-shadow:var(--raise-sm); }
.m-row .n { font-weight:800; color:var(--muted); font-size:.85rem; text-align:center; }
.m-row .w { font-weight:700; font-size:.92rem; }
.m-row .c { font-size:.78rem; color:var(--muted); }
.m-row .e { text-align:right; font-weight:800; font-size:1.05rem; }
.m-row .e small { display:block; font-weight:500; font-size:.72rem; color:var(--muted); }

/* forecast hero */
.m-hero .k { color:var(--muted); font-size:.88rem; font-weight:600; }
.m-hero .tier { font-size:2.6rem; font-weight:800; line-height:1.05; margin:.35rem 0 .5rem; }
.m-hero .num { font-size:1rem; line-height:1.55; }
.m-act { margin-top:1.1rem; padding:.9rem 1rem; border-radius:var(--r-md); box-shadow:var(--press); background:var(--base); }
.m-act b { display:block; font-size:.95rem; margin-bottom:.2rem; }
.m-act span { color:var(--muted); font-size:.87rem; line-height:1.5; }
.m-steps { display:grid; grid-template-columns:repeat(3,1fr); gap:1rem; }
.m-step { background:var(--base); border-radius:var(--r-md); box-shadow:var(--raise-sm); padding:.85rem .95rem; }
.m-step.on { box-shadow:var(--press); background:var(--base-hi); }
.m-step .h { font-size:.78rem; color:var(--muted); font-weight:600; }
.m-step .c { font-size:1.6rem; font-weight:800; line-height:1.2; margin:.15rem 0; }
.m-step .r { font-size:.76rem; color:var(--muted); }
.m-act .m-why { display:block; font-size:.9rem; line-height:1.65; color:var(--ink); }
.m-act .m-why b { display:inline; font-size:inherit; margin:0; font-weight:700; }

/* ------------------------------------------------------------ widgets */
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label { font-size:.82rem !important; font-weight:600 !important; color:var(--muted) !important; }
[data-baseweb="select"] > div, [data-baseweb="input"], [data-testid="stFileUploaderDropzone"] {
  background:var(--base) !important; border:none !important; border-radius:var(--r-sm) !important; box-shadow:var(--press-sm) !important; }
[data-baseweb="tag"] { background:var(--base-hi) !important; box-shadow:var(--raise-sm); border-radius:8px !important; color:var(--ink) !important; }
[data-baseweb="popover"] ul, [data-baseweb="menu"] { background:var(--base-hi) !important; border-radius:var(--r-sm) !important; }
[data-testid="stSlider"] [role="slider"] { background:var(--base) !important; box-shadow:var(--raise-sm) !important;
  width:20px !important; height:20px !important; border:2px solid var(--accent) !important; }
[data-testid="stSliderThumbValue"] { color:var(--accent) !important; font-weight:700; font-family:$FONT !important; }
[data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] { color:var(--muted) !important; }
[data-testid="stButtonGroup"] { gap:.5rem; }
[data-testid="stButtonGroup"] button { background:var(--base) !important; border:none !important; border-radius:var(--r-sm) !important;
  box-shadow:var(--raise-sm) !important; color:var(--ink) !important; font-weight:600; min-height:2.3rem; }
[data-testid="stButtonGroup"] button[kind*="Active"], [data-testid="stButtonGroup"] button[aria-checked="true"] {
  box-shadow:var(--press-sm) !important; color:var(--accent) !important; background:var(--base-hi) !important; }
.stButton button, [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"] {
  background:var(--base) !important; border:none !important; border-radius:var(--r-sm) !important; box-shadow:var(--raise-sm) !important;
  color:var(--ink) !important; font-weight:700; }
[data-testid="stBaseButton-primary"] { color:var(--accent) !important; }
.stButton button:active { box-shadow:var(--press-sm) !important; }
[role="tablist"] { gap:.45rem; background:var(--base); border:none !important; border-radius:var(--r-sm);
  box-shadow:var(--press-sm); padding:.32rem; width:fit-content; margin-bottom:1rem; }
[role="tablist"]::after, [role="tablist"]::before, [data-testid="stTab"]::after, [data-testid="stTab"]::before { display:none !important; }
[data-testid="stTab"] { border:none !important; border-radius:10px !important; padding:.42rem 1rem !important; background:transparent; }
[data-testid="stTab"][aria-selected="true"] { background:var(--base) !important; box-shadow:var(--raise-sm); }
[data-testid="stTab"] p { font-weight:600; font-size:.88rem; }
[data-testid="stTab"] > div + div, [data-testid="stTab"] > div[style*="position"] { display:none !important; }
[data-testid="stTab"][aria-selected="true"] p { color:var(--accent); }
[data-testid="stExpander"] details { border:none !important; border-radius:var(--r-md) !important; box-shadow:var(--raise-sm); background:var(--base); }
[data-testid="stAlert"] { border-radius:var(--r-md); box-shadow:var(--press-sm); }
[data-testid="stDataFrame"] { border-radius:var(--r-sm); overflow:hidden; box-shadow:var(--press-sm); }

/* ------------------------------------------------------------ small screens */
@media (max-width: 720px) {
  [data-testid="stMainBlockContainer"], .block-container { padding:1.2rem 1rem 3rem !important; }
  .m-head h1 { font-size:1.4rem; }
  .m-steps { grid-template-columns:1fr; }
  .m-stats { grid-template-columns:repeat(2, minmax(0,1fr)); gap:.8rem; }
  .m-stat { padding:.8rem .9rem; }
  .m-stat .v { font-size:1.35rem; }
  .m-stat .s { display:none; }
  [class*="st-key-card"] { padding:1.1rem 1rem; }
}
@media (prefers-reduced-motion: reduce) { * { transition:none !important; } }
""")


def inject_css() -> None:
    css = _CSS.substitute(
        BASE=BASE, BASE_HI=BASE_HI, LIGHT=LIGHT, SHADE=SHADE, INK=INK, MUTED=MUTED, LINE=LINE,
        ACCENT=ACCENT, FONT=FONT, FONT_BN=FONT_BN, CRIT=TIER_COLORS["Critical"],
    )
    st.html(f"<style>{css}</style>")


# --------------------------------------------------------------------------- html helpers
def badge(tier: str, text: str | None = None) -> str:
    return (f'<span class="m-badge" style="background:{TIER_COLORS[tier]};color:{TIER_TEXT[tier]}">'
            f'{text or tier}</span>')


def header(title: str, subtitle: str, chips: list[tuple[str, str]] | None = None) -> None:
    chip_html = "".join(f'<span class="m-chip">{k} <b>{v}</b></span>' for k, v in (chips or []))
    st.html(f'<div class="m-head"><div><h1>{title}</h1><p>{subtitle}</p></div>'
            f'<div class="m-chips">{chip_html}</div></div>')


def stats(items: list[tuple[str, str, str]]) -> None:
    """items: (label, value, small print). Value may contain HTML."""
    tiles = "".join(f'<div class="m-stat"><div class="k">{k}</div><div class="v">{v}</div>'
                    f'<div class="s">{s}</div></div>' for k, v, s in items)
    st.html(f'<div class="m-stats">{tiles}</div>')


def card_title(title: str, sub: str = "") -> None:
    st.html(f"<h3>{title}</h3>" + (f'<p class="m-sub">{sub}</p>' if sub else ""))


# --------------------------------------------------------------------------- plotly
def _template() -> go.layout.Template:
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family=FONT, color=INK, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=[ACCENT, RAIN, TIER_COLORS["High"], MUTED, TIER_COLORS["Medium"], TIER_COLORS["Critical"]],
        xaxis=dict(showgrid=False, linecolor=LINE, ticks="", zeroline=False, tickfont=dict(color=MUTED, size=12)),
        yaxis=dict(gridcolor=LINE, zeroline=False, linecolor="rgba(0,0,0,0)", tickfont=dict(color=MUTED, size=12)),
        hoverlabel=dict(bgcolor=BASE_HI, bordercolor=LINE, font=dict(color=INK, family=FONT)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=12, color=MUTED)),
        margin=dict(l=4, r=4, t=28, b=4),
        bargap=0.35,
    )
    return t


pio.templates["moshari"] = _template()
pio.templates.default = "plotly_white+moshari"
PLOT_CONFIG = {"displayModeBar": False}
