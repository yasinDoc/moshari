"""Reusable HTML components shared across pages."""

from __future__ import annotations

import html
from urllib.parse import urlencode

import pandas as pd

from moshari import config as C
from moshari.data import corporation_of
from moshari.risk import TIERS
from ui import theme
from ui.i18n import num, t, tr, ward
from ui.wardmap import tier_bounds

CORP_ORDER = ["DNCC", "DSCC", "CCC", "GCC", "NCC"]


def _tip(r: pd.Series, early: bool, linked: bool) -> str:
    tier = r["tier"]
    actual = ("" if pd.isna(r.get("actual")) else
              f'<span class="tr"><span>{t("Reported (replay)")}</span><b>{num(r["actual"], ".0f")}</b></span>')
    alert = f'<span class="ta">{t("Early alert: upper range reaches High")}</span>' if early else ""
    cta = f'<span class="tc">{t("Click to open the ward forecast")}</span>' if linked else ""
    probs = ""
    if "p_high" in r and not pd.isna(r.get("p_high")):
        probs = (f'<span class="tr"><span>{t("Chance of High")}</span><b>{num(r["p_high"], ".0%")}</b></span>'
                 f'<span class="tr"><span>{t("Chance of Critical")}</span><b>{num(r["p_crit"], ".0%")}</b></span>')
    watch = (f'<span class="ta">{t("Critical watch: outbreak-level cases are likely enough to prepare")}</span>'
             if bool(r.get("crit_watch", False)) and tier != "Critical" else "")
    return (
        f'<span class="tip" role="tooltip"><span class="th">{html.escape(ward(r[C.WARD_COL]))}'
        f'{theme.badge(tier)}</span>'
        f'<span class="tr"><span>{t("Expected cases")}</span><b>{num(r["expected_cases"], ".1f")}</b></span>'
        f'<span class="tr"><span>{t("80% range")}</span><b>{t("{lo:.1f} to {hi:.1f}", lo=r["lower_80"], hi=r["upper_80"])}</b></span>'
        f'{probs}{actual}<span class="tx">{html.escape(t(TIERS[tier].action))}</span>{alert}{watch}{cta}</span>'
    )


def _cell(r: pd.Series, link: dict | None) -> str:
    tier = r["tier"]
    early = bool(r.get("alert", False)) and r["tier_idx"] < 2
    label = (t("{ward}: {tier} risk, {cases:.1f} expected cases, 80% range {lo:.1f} to {hi:.1f}",
               ward=ward(r[C.WARD_COL]), tier=tr(tier), cases=r["expected_cases"], lo=r["lower_80"], hi=r["upper_80"])
             + (t(", early alert") if early else ""))
    num_ = r[C.WARD_COL].rsplit("_", 1)[-1]
    cw = bool(r.get("crit_watch", False)) and r["tier_idx"] < 3
    cls = f'm-cell t{r["tier_idx"]}{" up" if early else ""}{" cw" if cw else ""}'
    style = f'background:{theme.TIER_COLORS[tier]};color:{theme.TIER_TEXT[tier]}'
    inner = (f'<span class="w">W{tr(num_)}</span><span class="v">{num(r["expected_cases"], ".1f")}</span>'
             f'{_tip(r, early, link is not None)}')
    if link is None:
        return f'<div class="{cls}" style="{style}" tabindex="0" aria-label="{html.escape(label)}">{inner}</div>'
    href = "ward_forecast?" + urlencode({**link, "ward": r[C.WARD_COL]})
    return (f'<a class="{cls}" style="{style}" href="{html.escape(href)}" target="_self" '
            f'aria-label="{html.escape(label)}. {t("Open ward forecast.")}">{inner}</a>')


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
            f'<div class="m-corp"><div class="t">{tr(C.CITY_CORPORATIONS[corp])}</div>'
            f'<div class="s">{t("{high} of {shown} wards high or above", high=hi, shown=len(sub))}</div>'
            f'<div class="m-tray">{"".join(_cell(r, link) for _, r in sub.iterrows())}</div></div>'
        )


    bounds = tier_bounds(thresholds)
    legend = "".join(f'<span><span class="m-dot" style="background:{theme.TIER_COLORS[n]}"></span>'
                     f'<b>{tr(n)}</b>&nbsp; {t("{range} cases", range=bounds[n])}</span>' for n in C.TIER_NAMES)
    if early_label:
        legend += (f'<span><span class="m-dot" style="border-radius:50%;background:#fff;box-shadow:0 0 0 2px '
                   f'{theme.TIER_COLORS["Critical"]}"></span>{early_label}</span>')
    if "crit_watch" in fc and fc["crit_watch"].any():
        legend += ('<span><span class="m-dot" style="background:transparent;box-shadow:inset 0 0 0 2px '
                   f'{theme.TIER_COLORS["Critical"]}"></span>{t("Critical watch")}</span>')
    if link is not None:
        legend += f'<span class="hint">{t("Click a ward to open its forecast")}</span>'
    return f'<div class="m-net">{"".join(blocks)}</div><div class="m-legend" style="margin-top:24px">{legend}</div>'
