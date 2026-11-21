"""Reusable HTML components shared across pages."""

from __future__ import annotations

import html
from urllib.parse import urlencode

import pandas as pd

from moshari import config as C
from moshari.data import ward_label, corporation_of
from moshari.risk import TIERS
from ui import theme

CORP_ORDER = ["DNCC", "DSCC", "CCC", "GCC", "NCC"]


def _tip(r: pd.Series, early: bool, linked: bool) -> str:
    tier = r["tier"]
    actual = ("" if pd.isna(r.get("actual")) else
              f'<span class="tr"><span>Reported (replay)</span><b>{r["actual"]:.0f}</b></span>')
    alert = '<span class="ta">Early alert: upper range reaches High</span>' if early else ""
    cta = '<span class="tc">Click to open the ward forecast</span>' if linked else ""
    probs = ""
    if "p_high" in r and not pd.isna(r.get("p_high")):
        probs = (f'<span class="tr"><span>Chance of High</span><b>{r["p_high"]:.0%}</b></span>'
                 f'<span class="tr"><span>Chance of Critical</span><b>{r["p_crit"]:.0%}</b></span>')
    watch = ('<span class="ta">Critical watch: outbreak-level cases are likely enough to prepare</span>'
             if bool(r.get("crit_watch", False)) and tier != "Critical" else "")
    return (
        f'<span class="tip" role="tooltip"><span class="th">{html.escape(ward_label(r[C.WARD_COL]))}'
        f'{theme.badge(tier)}</span>'
        f'<span class="tr"><span>Expected cases</span><b>{r["expected_cases"]:.1f}</b></span>'
        f'<span class="tr"><span>80% range</span><b>{r["lower_80"]:.1f} to {r["upper_80"]:.1f}</b></span>'
        f'{probs}{actual}<span class="tx">{html.escape(TIERS[tier].action)}</span>{alert}{watch}{cta}</span>'
    )


def _cell(r: pd.Series, link: dict | None) -> str:
    tier = r["tier"]
    early = bool(r.get("alert", False)) and r["tier_idx"] < 2
    label = (f"{ward_label(r[C.WARD_COL])}: {tier} risk, {r['expected_cases']:.1f} expected cases, "
             f"80% range {r['lower_80']:.1f} to {r['upper_80']:.1f}" + (", early alert" if early else ""))
    num = r[C.WARD_COL].rsplit("_", 1)[-1]
    cw = bool(r.get("crit_watch", False)) and r["tier_idx"] < 3
    cls = f'm-cell t{r["tier_idx"]}{" up" if early else ""}{" cw" if cw else ""}'
    style = f'background:{theme.TIER_COLORS[tier]};color:{theme.TIER_TEXT[tier]}'
    inner = (f'<span class="w">W{num}</span><span class="v">{r["expected_cases"]:.1f}</span>'
             f'{_tip(r, early, link is not None)}')
    if link is None:
        return f'<div class="{cls}" style="{style}" tabindex="0" aria-label="{html.escape(label)}">{inner}</div>'
    href = "ward_forecast?" + urlencode({**link, "ward": r[C.WARD_COL]})
    return (f'<a class="{cls}" style="{style}" href="{html.escape(href)}" target="_self" '
            f'aria-label="{html.escape(label)}. Open ward forecast.">{inner}</a>')


def ward_net(fc: pd.DataFrame, thresholds: list[float], early_label: str | None = None,
             link: dict | None = None) -> str:
    """All wards as tiles in inset trays, one tray per city corporation, plus a legend.

    ``link`` holds the query parameters (issue week, horizon, policy…) that make each
    tile a link to that ward's forecast with the same settings.
    """
    fc = fc.assign(corp=fc[C.WARD_COL].map(corporation_of))
    blocks = []
    for corp in CORP_ORDER:
        sub = fc[fc["corp"] == corp].sort_values(C.WARD_COL)
        if sub.empty:
            continue
        hi = int((sub["tier_idx"] >= 2).sum())
        blocks.append(
            f'<div class="m-corp"><div class="t">{C.CITY_CORPORATIONS[corp]}</div>'
            f'<div class="s">{hi} of {len(sub)} wards high or above</div>'
            f'<div class="m-tray">{"".join(_cell(r, link) for _, r in sub.iterrows())}</div></div>'
        )
    t = thresholds
    bounds = {"Low": f"under {t[0]:g}", "Medium": f"{t[0]:g} to {t[1]:g}", "High": f"{t[1]:g} to {t[2]:g}",
              "Critical": f"{t[2]:g}+"}
    legend = "".join(f'<span><span class="m-dot" style="background:{theme.TIER_COLORS[n]}"></span>'
                     f'<b>{n}</b>&nbsp; {bounds[n]} cases</span>' for n in C.TIER_NAMES)
    if early_label:
        legend += (f'<span><span class="m-dot" style="border-radius:50%;background:#fff;box-shadow:0 0 0 2px '
                   f'{theme.TIER_COLORS["Critical"]}"></span>{early_label}</span>')
    if "crit_watch" in fc and fc["crit_watch"].any():
        legend += ('<span><span class="m-dot" style="background:transparent;box-shadow:inset 0 0 0 2px '
                   f'{theme.TIER_COLORS["Critical"]}"></span>Critical watch</span>')
    if link is not None:
        legend += '<span class="hint">Click a ward to open its forecast</span>'
    return f'<div class="m-net">{"".join(blocks)}</div><div class="m-legend" style="margin-top:24px">{legend}</div>'
