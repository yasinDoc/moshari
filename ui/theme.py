"""Moshari design system: refined neumorphism on a vanilla base.

One material. Surfaces are extruded from it with a soft paired shadow and a
hairline highlight for definition; inputs and trays are pressed into it.
Risk tiers are the only saturated colours on screen.

Scale (px): spacing 4 · 8 · 12 · 16 · 24 · 32 · 48
            type    12 · 13 · 14 · 16 · 18 · 24 · 30
            radius  10 · 14 · 20
"""

from __future__ import annotations

from string import Template

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from moshari.risk import TIERS

# --------------------------------------------------------------------------- tokens
BASE = "#EDE9E1"        # vanilla-grey material
BASE_HI = "#F6F2EA"     # lifted vanilla for pressed/active states
LIGHT = "rgba(255,255,255,0.92)"
SHADE = "rgba(163,150,124,0.30)"
INK = "#1F2630"
INK_2 = "#4A525C"
MUTED = "#80848A"
LINE = "rgba(110,100,80,0.12)"
ACCENT = "#0E7369"
ACCENT_SOFT = "rgba(14,115,105,0.10)"
RAIN = "#7AA3C6"

TIER_COLORS = {name: t.color for name, t in TIERS.items()}
TIER_TEXT = {"Low": "#FFFFFF", "Medium": "#3B2F00", "High": "#FFFFFF", "Critical": "#FFFFFF"}

FONT = "Manrope, 'Segoe UI', system-ui, -apple-system, sans-serif"
FONT_BN = "'Hind Siliguri', 'Noto Sans Bengali', Vrinda, sans-serif"
ICON_FONT = "'Material Symbols Rounded'"

_CSS = Template(r"""
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Hind+Siliguri:wght@600;700&display=swap');

:root{
  --base:$BASE; --base-hi:$BASE_HI; --light:$LIGHT; --shade:$SHADE;
  --ink:$INK; --ink-2:$INK_2; --muted:$MUTED; --line:$LINE; --accent:$ACCENT; --accent-soft:$ACCENT_SOFT;
  --edge: inset 0 1px 0 rgba(255,255,255,.75);
  --raise: 10px 10px 24px var(--shade), -10px -10px 24px var(--light), var(--edge);
  --raise-sm: 5px 5px 12px var(--shade), -5px -5px 12px var(--light), var(--edge);
  --raise-xs: 3px 3px 7px var(--shade), -3px -3px 7px var(--light);
  --press: inset 5px 5px 11px var(--shade), inset -5px -5px 11px var(--light);
  --press-sm: inset 2px 2px 6px var(--shade), inset -2px -2px 6px var(--light);
  --r-lg:20px; --r-md:14px; --r-sm:10px;
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px; --s7:48px;
}

/* ================================================================ canvas */
html, body, .stApp, p, label, li, td, th, input, textarea, button, select { font-family:$FONT; }
html { -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; }
.stApp, [data-testid="stAppViewContainer"] { background:var(--base) !important; color:var(--ink); }
[data-testid="stHeader"] { background:transparent !important; }
[data-testid="stMainBlockContainer"], .block-container { padding:48px 48px 64px !important; max-width:1400px; }
h1,h2,h3,h4,h5 { font-family:$FONT !important; color:var(--ink) !important; letter-spacing:-0.02em; }
p, li { color:var(--ink-2); }
[data-testid="stIconMaterial"] { font-family:$ICON_FONT !important; }
.mi { font-family:$ICON_FONT; font-weight:normal; font-style:normal; line-height:1; letter-spacing:normal;
  text-transform:none; white-space:nowrap; font-feature-settings:'liga'; -webkit-font-smoothing:antialiased; }
:focus-visible { outline:2px solid var(--accent) !important; outline-offset:3px; }
[data-testid="stDecoration"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"], [data-testid="stStatusWidget"] { display:none !important; }
[data-testid="stVerticalBlock"] { gap:var(--s4); }
[data-testid="stElementContainer"]:has(> .stHtml:empty) { display:none; }
::selection { background:var(--accent-soft); }

/* equal-height cards in a row */
[data-testid="stHorizontalBlock"] { align-items:stretch !important; gap:var(--s5) !important; }
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { align-self:stretch !important; display:flex; flex-direction:column; }
[data-testid="stColumn"] > [data-testid="stVerticalBlock"] { flex:1 1 auto; }
[data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]:has(> [class*="st-key-card"]) { flex:1 1 auto; display:flex; flex-direction:column; }
[data-testid="stColumn"] [data-testid="stLayoutWrapper"] > [class*="st-key-card"] { flex:1 1 auto; }

/* ================================================================ sidebar */
[data-testid="stSidebar"] { background:var(--base) !important; border:none !important; min-width:272px !important;
  max-width:272px !important; box-shadow: 6px 0 24px -12px var(--shade); }
[data-testid="stSidebar"] > div:first-child { background:var(--base); }
[data-testid="stSidebarContent"] { padding:0 4px; }
[data-testid="stSidebarHeader"] { height:24px; padding:0; }
[data-testid="stSidebarUserContent"] { padding-top:0 !important; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap:var(--s2); }

.m-brand { display:flex; align-items:center; gap:var(--s3); padding:0 var(--s1) var(--s5); }
.m-brand .mark { width:44px; height:44px; border-radius:var(--r-md); background:var(--base); box-shadow:var(--raise-sm);
  display:grid; place-items:center; flex:none; }
.m-brand .mark img { width:28px; height:28px; }
.m-brand .name { font-weight:800; font-size:18px; line-height:1.1; color:var(--ink); letter-spacing:-0.02em; }
.m-brand .bn { font-family:$FONT_BN; font-weight:700; font-size:14px; color:var(--accent); line-height:1.25; }
.m-side-label { font-size:12px; font-weight:700; color:var(--muted); margin:var(--s5) var(--s2) var(--s2); }

[data-testid="stSidebar"] [data-testid="stPageLink"] { margin:0; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] { height:40px; padding:0 var(--s3); border-radius:var(--r-sm);
  background:transparent; box-shadow:none; transition:background .15s ease, box-shadow .15s ease; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover { background:var(--base-hi); box-shadow:var(--raise-xs); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p { font-weight:600; font-size:14px; color:var(--ink-2); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"] { color:var(--muted); font-size:20px; }
[data-testid="stSidebar"] .st-key-nav-current [data-testid="stPageLink-NavLink"] { background:var(--base); box-shadow:var(--press-sm); }
[data-testid="stSidebar"] .st-key-nav-current [data-testid="stPageLink-NavLink"] p,
[data-testid="stSidebar"] .st-key-nav-current [data-testid="stIconMaterial"] { color:var(--accent) !important; font-weight:700; }

.st-key-settings { background:var(--base); border-radius:var(--r-md); box-shadow:var(--press); padding:var(--s4) var(--s4) var(--s3); }
.st-key-settings [data-testid="stVerticalBlock"] { gap:var(--s4) !important; }
.m-status { margin-top:var(--s5); padding:var(--s3) var(--s4); border-radius:var(--r-md); box-shadow:var(--raise-sm); background:var(--base); }
.m-status .r { display:flex; align-items:center; gap:var(--s2); font-size:13px; font-weight:700; color:var(--ink); }
.m-status .r .live { width:8px; height:8px; border-radius:50%; background:#2FA36B; box-shadow:0 0 0 3px rgba(47,163,107,.18); }
.m-status dl { margin:var(--s2) 0 0; display:grid; grid-template-columns:auto 1fr; gap:3px var(--s3); font-size:12px; }
.m-status dt { color:var(--muted); } .m-status dd { margin:0; color:var(--ink-2); font-weight:600; text-align:right; }

/* ================================================================ page header */
.m-head { display:flex; justify-content:space-between; align-items:flex-end; gap:var(--s4); flex-wrap:wrap; margin:0 0 var(--s5); }
.m-head h1 { font-size:30px; font-weight:800; margin:0; padding:0; line-height:1.15; }
.m-head p { margin:6px 0 0; color:var(--muted); font-size:15px; font-weight:500; }
.m-chips { display:flex; gap:var(--s2); flex-wrap:wrap; }
.m-chip { display:inline-flex; align-items:center; gap:6px; height:34px; padding:0 14px; border-radius:999px;
  background:var(--base); box-shadow:var(--raise-xs); font-size:13px; font-weight:600; color:var(--ink-2); white-space:nowrap; }
.m-chip .mi { font-size:16px; color:var(--muted); }
.m-chip b { color:var(--ink); font-weight:700; }

/* ================================================================ stat tiles */
.m-stats { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:var(--s5); margin:0 0 var(--s6); }
.m-stat { background:var(--base); border-radius:var(--r-lg); box-shadow:var(--raise); padding:20px 22px; min-height:128px;
  display:flex; flex-direction:column; }
.m-stat .top { display:flex; justify-content:space-between; align-items:center; gap:var(--s2); }
.m-stat .k { font-size:13px; color:var(--muted); font-weight:600; }
.m-stat .ic { width:34px; height:34px; border-radius:var(--r-sm); box-shadow:var(--press-sm); display:grid; place-items:center; flex:none; }
.m-stat .ic .mi { font-size:18px; color:var(--accent); }
.m-stat .v { font-size:30px; font-weight:800; line-height:1.1; margin-top:auto; padding-top:var(--s3); color:var(--ink);
  letter-spacing:-0.02em; font-variant-numeric:tabular-nums; }
.m-stat .v small { font-size:15px; color:var(--muted); font-weight:600; }
.m-stat .s { font-size:13px; color:var(--muted); margin-top:4px; }

/* ================================================================ cards */
[class*="st-key-card"] { background:var(--base); border-radius:var(--r-lg); box-shadow:var(--raise); padding:24px 26px 22px; }
[class*="st-key-card"] > [data-testid="stVerticalBlock"] { gap:var(--s4); }
.m-ct { display:flex; justify-content:space-between; align-items:flex-start; gap:var(--s3); }
.m-ct h3 { font-size:18px; font-weight:700; margin:0; padding:0; line-height:1.3; }
.m-ct p { color:var(--muted); font-size:14px; margin:4px 0 0; line-height:1.5; }
.m-ct .aside { font-size:13px; color:var(--muted); font-weight:600; white-space:nowrap; padding-top:3px; }
.m-gap { height:var(--s6); }
.m-note { color:var(--muted); font-size:13px; line-height:1.55; margin:0; }
.m-dot { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:6px; vertical-align:-1px; }
.m-badge { display:inline-flex; align-items:center; height:22px; border-radius:999px; padding:0 10px; font-size:12px;
  font-weight:700; letter-spacing:.01em; vertical-align:2px; }
[class*="st-key-tray"] { background:var(--base); border-radius:var(--r-md); box-shadow:var(--press); padding:var(--s4) var(--s5); }

/* ================================================================ ward net */
.m-net { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:var(--s5) var(--s6); }
.m-corp .t { font-weight:700; font-size:15px; color:var(--ink); }
.m-corp .s { color:var(--muted); font-size:13px; margin:2px 0 var(--s3); }
.m-tray { background:var(--base); border-radius:var(--r-md); box-shadow:var(--press); padding:10px;
  display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:8px; }
.m-cell { border-radius:var(--r-sm); height:52px; display:flex; flex-direction:column; justify-content:center; align-items:center;
  box-shadow:var(--raise-xs); position:relative; cursor:default; transition:transform .12s ease; }
.m-cell:hover { transform:translateY(-1px); }
.m-cell .w { font-size:11px; font-weight:700; opacity:.82; line-height:1; }
.m-cell .v { font-size:16px; font-weight:800; line-height:1.15; margin-top:3px; font-variant-numeric:tabular-nums; }
.m-cell.up::after { content:""; position:absolute; top:5px; right:5px; width:6px; height:6px; border-radius:50%;
  background:#fff; box-shadow:0 0 0 2px $CRIT; }
.m-legend { display:flex; flex-wrap:wrap; gap:var(--s2) var(--s5); font-size:13px; color:var(--ink-2); padding-top:var(--s4);
  border-top:1px solid var(--line); }

/* ================================================================ lists */
.m-list { display:flex; flex-direction:column; gap:10px; }
.m-row { display:grid; grid-template-columns:28px 1fr auto; align-items:center; gap:var(--s3); min-height:60px; padding:10px 16px;
  border-radius:var(--r-md); background:var(--base); box-shadow:var(--raise-sm); }
.m-row .n { width:28px; height:28px; border-radius:8px; box-shadow:var(--press-sm); display:grid; place-items:center;
  font-weight:800; color:var(--muted); font-size:13px; }
.m-row .w { font-weight:700; font-size:15px; color:var(--ink); display:flex; align-items:center; gap:var(--s2); }
.m-row .c { font-size:13px; color:var(--muted); margin-top:2px; }
.m-row .e { text-align:right; font-weight:800; font-size:18px; color:var(--ink); font-variant-numeric:tabular-nums; }
.m-row .e small { display:block; font-weight:500; font-size:12px; color:var(--muted); }

/* ================================================================ forecast */
.m-hero .k { color:var(--muted); font-size:14px; font-weight:600; }
.m-hero .tier { font-size:44px; font-weight:800; line-height:1.05; margin:var(--s2) 0 var(--s3); letter-spacing:-0.03em; }
.m-hero .num { font-size:16px; line-height:1.6; color:var(--ink-2); }
.m-hero .num b { color:var(--ink); font-size:18px; }
.m-act { margin-top:var(--s5); padding:var(--s4) 18px; border-radius:var(--r-md); box-shadow:var(--press); background:var(--base); }
.m-act .h { display:flex; align-items:center; gap:var(--s2); font-size:15px; font-weight:700; color:var(--ink); margin-bottom:4px; }
.m-act .h .mi { font-size:18px; color:var(--accent); }
.m-act .b { color:var(--ink-2); font-size:14px; line-height:1.6; }
.m-act .b b { color:var(--ink); font-weight:700; }
.m-steps { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:var(--s4); }
.m-step { background:var(--base); border-radius:var(--r-md); box-shadow:var(--raise-sm); padding:var(--s4) 18px; }
.m-step.on { box-shadow:var(--press); }
.m-step .h { font-size:13px; color:var(--muted); font-weight:600; }
.m-step .c { font-size:28px; font-weight:800; line-height:1.15; margin:6px 0 2px; font-variant-numeric:tabular-nums; letter-spacing:-0.02em; }
.m-step .r { font-size:13px; color:var(--muted); }
.m-prof { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:var(--s4); }
.m-prof > div { padding:10px 14px; border-radius:var(--r-md); box-shadow:var(--press-sm); }
.m-prof .k { font-size:12px; color:var(--muted); font-weight:600; }
.m-prof .v { font-size:17px; font-weight:800; color:var(--ink); font-variant-numeric:tabular-nums; }

/* ================================================================ widgets */
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label { font-size:13px !important; font-weight:600 !important; color:var(--ink-2) !important; }
[data-testid="stTooltipIcon"] { display:none !important; }
[data-baseweb="select"] > div { min-height:42px; background:var(--base) !important; border:none !important; border-radius:var(--r-sm) !important;
  box-shadow:var(--press-sm) !important; font-size:14px; }
[data-baseweb="select"] svg { color:var(--muted); }
[data-testid="stFileUploaderDropzone"] { background:var(--base) !important; border:1.5px dashed rgba(110,100,80,.28) !important;
  border-radius:var(--r-md) !important; box-shadow:var(--press-sm) !important; padding:var(--s5) !important; }
[data-baseweb="tag"] { background:var(--base-hi) !important; box-shadow:var(--raise-xs); border-radius:8px !important; color:var(--ink) !important; }
[data-baseweb="popover"] [role="listbox"], [data-baseweb="menu"] { background:var(--base-hi) !important; border-radius:var(--r-sm) !important;
  box-shadow:var(--raise) !important; }
[data-testid="stSlider"] { padding:0 6px; }
[data-testid="stSlider"] [role="slider"] { background:var(--base-hi) !important; box-shadow:var(--raise-xs) !important;
  width:18px !important; height:18px !important; border:4px solid var(--accent) !important; }
[data-testid="stSliderThumbValue"] { color:var(--ink) !important; font-weight:700; font-size:13px !important; font-family:$FONT !important; }
[data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] { color:var(--muted) !important; font-size:12px !important; }
[data-testid="stButtonGroup"] button { flex:1; min-height:38px; background:var(--base) !important; border:none !important;
  border-radius:var(--r-sm) !important; box-shadow:var(--raise-xs) !important; color:var(--ink-2) !important; font-weight:700; font-size:14px; }
[data-testid="stButtonGroup"] button[aria-checked="true"] { box-shadow:var(--press-sm) !important; color:var(--accent) !important; }
.stButton button, [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"] {
  min-height:42px; padding:0 20px; background:var(--base) !important; border:none !important; border-radius:var(--r-sm) !important;
  box-shadow:var(--raise-sm) !important; color:var(--ink) !important; font-weight:700; font-size:14px; }
.stButton button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primary"] {
  background:var(--accent) !important; color:#fff !important;
  box-shadow:4px 4px 12px rgba(14,115,105,.32), -4px -4px 10px var(--light) !important; }
.stButton button[data-testid="stBaseButton-primary"] p, .stButton button[data-testid="stBaseButton-primary"] span { color:#fff !important; }
.stButton button[data-testid="stBaseButton-primary"]:hover { background:#0B655C !important; }
.stButton button:active { box-shadow:var(--press-sm) !important; }
[role="tablist"] { gap:4px; background:var(--base); border:none !important; border-radius:12px; box-shadow:var(--press-sm);
  padding:4px; width:fit-content; margin-bottom:var(--s2); }
[role="tablist"]::after, [role="tablist"]::before { display:none !important; }
[data-testid="stTab"] { border:none !important; border-radius:9px !important; height:34px; padding:0 16px !important; background:transparent; }
[data-testid="stTab"][aria-selected="true"] { background:var(--base-hi) !important; box-shadow:var(--raise-xs); }
[data-testid="stTab"] p { font-weight:600; font-size:14px; color:var(--muted); }
[data-testid="stTab"][aria-selected="true"] p { color:var(--ink); }
[data-testid="stTab"] > div + div { display:none !important; }
[data-testid="stExpander"] details { border:none !important; border-radius:var(--r-md) !important; box-shadow:var(--raise-sm); background:var(--base); }
[data-testid="stExpander"] summary p { font-weight:700; font-size:14px; }
[data-testid="stAlert"] { border-radius:var(--r-md); }
[data-testid="stDataFrame"] { border-radius:var(--r-sm); overflow:hidden; }
[data-testid="stCaptionContainer"] p { font-size:13px; color:var(--muted); }

/* footer */
.m-foot { margin-top:var(--s7); padding-top:var(--s4); border-top:1px solid var(--line); display:flex; justify-content:space-between;
  flex-wrap:wrap; gap:var(--s2); font-size:12px; color:var(--muted); }

/* ================================================================ responsive */
@media (max-width: 1200px) {
  .m-net { grid-template-columns:repeat(2, minmax(0,1fr)); }
  .m-stats { grid-template-columns:repeat(2, minmax(0,1fr)); }
}
@media (max-width: 720px) {
  [data-testid="stMainBlockContainer"], .block-container { padding:20px 16px 48px !important; }
  .m-head h1 { font-size:24px; }
  .m-head p { font-size:14px; }
  .m-net { grid-template-columns:1fr; }
  .m-stats { gap:var(--s3); margin-bottom:var(--s5); }
  .m-stat { padding:14px 16px; min-height:0; }
  .m-stat .ic { display:none; }
  .m-stat .v { font-size:22px; }
  .m-stat .s { display:none; }
  .m-steps, .m-prof { grid-template-columns:1fr; }
  .m-hero .tier { font-size:34px; }
  [class*="st-key-card"] { padding:18px 16px; }
  [data-testid="stHorizontalBlock"] { gap:var(--s4) !important; }
}
@media (prefers-reduced-motion: reduce) { * { transition:none !important; } }
""")


def inject_css() -> None:
    css = _CSS.substitute(
        BASE=BASE, BASE_HI=BASE_HI, LIGHT=LIGHT, SHADE=SHADE, INK=INK, INK_2=INK_2, MUTED=MUTED, LINE=LINE,
        ACCENT=ACCENT, ACCENT_SOFT=ACCENT_SOFT, FONT=FONT, FONT_BN=FONT_BN, ICON_FONT=ICON_FONT,
        CRIT=TIER_COLORS["Critical"],
    )
    st.html(f"<style>{css}</style>")


# --------------------------------------------------------------------------- html helpers
def icon(name: str) -> str:
    return f'<span class="mi">{name}</span>'


def badge(tier: str, text: str | None = None) -> str:
    return (f'<span class="m-badge" style="background:{TIER_COLORS[tier]};color:{TIER_TEXT[tier]}">'
            f'{text or tier}</span>')


def header(title: str, subtitle: str, chips: list[tuple[str, str, str]] | None = None) -> None:
    """chips: (icon, label, value)."""
    chip_html = "".join(f'<span class="m-chip">{icon(i)}{k} <b>{v}</b></span>' for i, k, v in (chips or []))
    st.html(f'<div class="m-head"><div><h1>{title}</h1><p>{subtitle}</p></div>'
            f'<div class="m-chips">{chip_html}</div></div>')


def stats(items: list[tuple[str, str, str, str]]) -> None:
    """items: (icon, label, value, small print). Value may contain HTML."""
    tiles = "".join(
        f'<div class="m-stat"><div class="top"><span class="k">{k}</span><span class="ic">{icon(i)}</span></div>'
        f'<div class="v">{v}</div><div class="s">{s}</div></div>'
        for i, k, v, s in items
    )
    st.html(f'<div class="m-stats">{tiles}</div>')


def card_title(title: str, sub: str = "", aside: str = "") -> None:
    st.html(f'<div class="m-ct"><div><h3>{title}</h3>{f"<p>{sub}</p>" if sub else ""}</div>'
            f'{f"<span class=aside>{aside}</span>" if aside else ""}</div>')


def gap() -> None:
    st.html('<div class="m-gap"></div>')


def footer(meta: dict) -> None:
    st.html(f'<div class="m-foot"><span>Moshari 1.0, ward-level dengue early warning</span>'
            f'<span>Model trained through {meta.get("trained_through", "unknown")}, '
            f'LightGBM {meta.get("lightgbm_version", "")}</span></div>')


# --------------------------------------------------------------------------- plotly
def _template() -> go.layout.Template:
    t = go.layout.Template()
    axis = dict(showgrid=False, linecolor=LINE, ticks="", zeroline=False, tickfont=dict(color=MUTED, size=12),
                title=dict(font=dict(color=MUTED, size=12)))
    t.layout = go.Layout(
        font=dict(family=FONT, color=INK_2, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=[ACCENT, RAIN, TIER_COLORS["High"], MUTED, TIER_COLORS["Medium"], TIER_COLORS["Critical"]],
        xaxis=axis,
        yaxis={**axis, "showgrid": True, "gridcolor": LINE, "linecolor": "rgba(0,0,0,0)"},
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=LINE, font=dict(color=INK, family=FONT, size=13)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)",
                    font=dict(size=12, color=INK_2), itemsizing="constant"),
        margin=dict(l=0, r=0, t=32, b=0),
        bargap=0.35,
    )
    return t


pio.templates["moshari"] = _template()
pio.templates.default = "plotly_white+moshari"
PLOT_CONFIG = {"displayModeBar": False}


def plot(fig: go.Figure, height: int) -> None:
    fig.update_layout(height=height)
    st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, theme=None)
