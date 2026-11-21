"""Moshari visual identity: tokens, CSS and the Plotly template.

The identity is built on the mosquito net (মশারি): cotton-net white, a fine
mesh drawn in grey-green, monsoon-indigo ink and lagoon teal. Risk tiers are
the only saturated colours on screen, so they always read as signal.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from moshari import config as C
from moshari.risk import TIERS

NET = "#F3F6F4"       # page: cotton-net white
PAPER = "#FFFFFF"     # raised surfaces
MESH = "#D5DED9"      # hairlines and the net itself
INK = "#14213D"       # monsoon indigo text
SLATE = "#5B6B79"     # secondary text
LAGOON = "#0F6E6A"    # primary / interactive
RAIN = "#5E8FB8"      # rainfall in charts

TIER_COLORS = {name: t.color for name, t in TIERS.items()}
TIER_ORDER = list(C.TIER_NAMES)

FONT_BODY = "'Instrument Sans', system-ui, -apple-system, 'Segoe UI', sans-serif"
FONT_DISPLAY = "'Bricolage Grotesque', 'Instrument Sans', system-ui, sans-serif"
FONT_BANGLA = "'Hind Siliguri', 'Noto Sans Bengali', 'Vrinda', sans-serif"

_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&family=Instrument+Sans:wght@400;500;600;700&family=Hind+Siliguri:wght@600;700&display=swap');

:root {{
  --net: {NET}; --paper: {PAPER}; --mesh: {MESH}; --ink: {INK}; --slate: {SLATE}; --lagoon: {LAGOON};
}}
html, body, .stApp, .stMarkdown, p, label, button, input, textarea, select, li, td, th {{
  font-family: {FONT_BODY};
  font-variant-numeric: tabular-nums;
}}
[data-testid="stIconMaterial"], .material-symbols-rounded {{ font-family: 'Material Symbols Rounded' !important; }}
.stApp {{
  background-color: var(--net);
  /* the net: a barely-there diagonal mesh across the whole canvas */
  background-image:
    repeating-linear-gradient(45deg, rgba(20,33,61,0.028) 0 1px, transparent 1px 14px),
    repeating-linear-gradient(-45deg, rgba(20,33,61,0.028) 0 1px, transparent 1px 14px);
}}
h1, h2, h3, h4 {{ font-family: {FONT_DISPLAY} !important; color: var(--ink); letter-spacing: -0.01em; }}
h1 {{ font-weight: 800 !important; }}
h2, h3 {{ font-weight: 700 !important; }}
.block-container, [data-testid="stMainBlockContainer"] {{ padding-top: 4.6rem !important; max-width: 1240px; }}
[data-testid="stSidebar"] {{ background: var(--paper); border-right: 1px solid var(--mesh); }}
[data-testid="stSidebar"] .block-container {{ padding-top: 1rem; }}
[data-testid="stHeader"] {{ background: rgba(243,246,244,0.94); backdrop-filter: blur(6px); border-bottom: 1px solid var(--mesh); }}
a {{ color: var(--lagoon); }}
:focus-visible {{ outline: 2px solid var(--lagoon) !important; outline-offset: 2px; }}

/* ---- brand block ---- */
.m-brand {{ display:flex; align-items:center; gap:.7rem; margin:.2rem 0 .4rem; }}
.m-brand img {{ width:46px; height:46px; }}
.m-brand .name {{ font-family:{FONT_DISPLAY}; font-weight:800; font-size:1.45rem; color:var(--ink); line-height:1; }}
.m-brand .bn {{ font-family:{FONT_BANGLA}; font-weight:700; color:var(--lagoon); font-size:1.05rem; line-height:1.2; }}
.m-brand-tag {{ color:var(--slate); font-size:.86rem; line-height:1.4; margin:0 0 .6rem; }}

/* ---- page heading ---- */
.m-kicker {{ color:var(--slate); font-size:.95rem; margin:0 0 .25rem; }}
.m-lede {{ font-family:{FONT_DISPLAY}; font-weight:600; font-size:clamp(1.35rem, 2.4vw, 1.9rem);
          line-height:1.25; color:var(--ink); max-width:46ch; margin:.1rem 0 1.1rem; }}
.m-lede b {{ font-weight:800; }}
.m-note {{ color:var(--slate); font-size:.88rem; line-height:1.5; max-width:72ch; }}

/* ---- tier pill ---- */
.m-pill {{ display:inline-flex; align-items:center; gap:.4rem; padding:.16rem .6rem .16rem .5rem;
          border-radius:999px; font-weight:600; font-size:.86rem; line-height:1.4; }}
.m-pill::before {{ content:""; width:.55rem; height:.55rem; border-radius:50%; background:currentColor; }}

/* ---- the ward net ---- */
.m-net {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap:1.4rem 1.6rem; margin:.4rem 0 .6rem; }}
.m-corp h4 {{ font-size:1rem; margin:0 0 .1rem; }}
.m-corp p {{ margin:0 0 .5rem; color:var(--slate); font-size:.82rem; }}
.m-mesh {{ display:grid; grid-template-columns:repeat(5, 1fr); gap:2px; background:var(--mesh);
          border:2px solid var(--mesh); border-radius:6px; overflow:hidden; }}
.m-cell {{ aspect-ratio: 1 / 0.82; display:flex; flex-direction:column; justify-content:space-between;
          padding:.32rem .4rem; background:var(--paper); color:var(--ink); position:relative; }}
.m-cell .w {{ font-size:.72rem; color:inherit; opacity:.8; }}
.m-cell .v {{ font-family:{FONT_DISPLAY}; font-weight:700; font-size:1.12rem; line-height:1; }}
.m-cell.t3 {{ color:#fff; }}
.m-cell.up::after {{ content:""; position:absolute; top:.35rem; right:.35rem; width:.42rem; height:.42rem;
          border-radius:50%; border:1.5px solid {TIERS['Critical'].color}; background:#fff; }}
.m-legend {{ display:flex; flex-wrap:wrap; gap:.4rem 1.1rem; align-items:center; color:var(--slate); font-size:.84rem; margin:.2rem 0 1rem; }}
.m-legend span.sw {{ display:inline-block; width:.85rem; height:.85rem; border-radius:3px; vertical-align:-2px; margin-right:.35rem; }}

/* ---- forecast hero ---- */
.m-hero {{ background:var(--paper); border:1px solid var(--mesh); border-radius:14px; padding:1.2rem 1.4rem; }}
.m-hero .tier {{ font-family:{FONT_DISPLAY}; font-weight:800; font-size:clamp(2.2rem, 5vw, 3.4rem); line-height:1; margin:.15rem 0 .5rem; }}
.m-hero .num {{ font-size:1.05rem; color:var(--ink); }}
.m-hero .act {{ margin-top:.8rem; padding-top:.8rem; border-top:1px dashed var(--mesh); }}
.m-hero .act strong {{ display:block; font-size:.98rem; margin-bottom:.15rem; }}
.m-hero .act span {{ color:var(--slate); font-size:.92rem; line-height:1.5; }}
.m-step {{ border-left:3px solid var(--mesh); padding:.1rem 0 .1rem .8rem; }}
.m-step .h {{ color:var(--slate); font-size:.84rem; }}
.m-step .c {{ font-family:{FONT_DISPLAY}; font-weight:700; font-size:1.5rem; line-height:1.15; }}
.m-step .r {{ color:var(--slate); font-size:.82rem; }}

@media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; animation:none !important; }} }}
"""


def inject_css() -> None:
    st.html(f"<style>{_CSS}</style>")


def pill(tier: str, text: str | None = None) -> str:
    t = TIERS[tier]
    return f'<span class="m-pill" style="color:{t.color};background:{t.soft}">{text or tier}</span>'


def _template() -> go.layout.Template:
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family=FONT_BODY.replace("'", ""), color=INK, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=[LAGOON, RAIN, TIER_COLORS["High"], SLATE, TIER_COLORS["Medium"], TIER_COLORS["Critical"]],
        xaxis=dict(gridcolor=MESH, linecolor=MESH, zerolinecolor=MESH, ticks="outside", tickcolor=MESH),
        yaxis=dict(gridcolor=MESH, linecolor=MESH, zerolinecolor=MESH),
        hoverlabel=dict(bgcolor=PAPER, bordercolor=MESH, font=dict(color=INK, family=FONT_BODY.replace("'", ""))),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=8, r=8, t=36, b=8),
        title=dict(font=dict(family=FONT_DISPLAY.replace("'", ""), size=16, color=INK), x=0, xanchor="left"),
    )
    return t


pio.templates["moshari"] = _template()
pio.templates.default = "plotly_white+moshari"
