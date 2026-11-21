"""Reusable HTML components shared across pages."""

from __future__ import annotations

import html

import pandas as pd

from moshari import config as C
from moshari.data import corporation_of, ward_label
from ui import theme

CORP_ORDER = ["DNCC", "DSCC", "CCC", "GCC", "NCC"]


def _cell(r: pd.Series) -> str:
    tier = r["tier"]
    early = bool(r.get("alert", False)) and r["tier_idx"] < 2
    tip = (f"{ward_label(r[C.WARD_COL])}: {tier}, {r['expected_cases']:.1f} expected cases "
           f"(80% range {r['lower_80']:.1f} to {r['upper_80']:.1f})" + (". Early alert" if early else ""))
    num = r[C.WARD_COL].rsplit("_", 1)[-1]
    return (f'<div class="m-cell{" up" if early else ""}" title="{html.escape(tip)}" aria-label="{html.escape(tip)}" '
            f'style="background:{theme.TIER_COLORS[tier]};color:{theme.TIER_TEXT[tier]}">'
            f'<span class="w">W{num}</span><span class="v">{r["expected_cases"]:.1f}</span></div>')


def ward_net(fc: pd.DataFrame, thresholds: list[float], early_label: str | None = None) -> str:
    """All wards as tiles in inset trays, one tray per city corporation, plus a legend."""
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
            f'<div class="m-tray">{"".join(_cell(r) for _, r in sub.iterrows())}</div></div>'
        )
    t = thresholds
    bounds = {"Low": f"under {t[0]:g}", "Medium": f"{t[0]:g} to {t[1]:g}", "High": f"{t[1]:g} to {t[2]:g}",
              "Critical": f"{t[2]:g}+"}
    legend = "".join(f'<span><span class="m-dot" style="background:{theme.TIER_COLORS[n]}"></span>'
                     f'<b>{n}</b>&nbsp; {bounds[n]} cases</span>' for n in C.TIER_NAMES)
    if early_label:
        legend += (f'<span><span class="m-dot" style="border-radius:50%;background:#fff;box-shadow:0 0 0 2px '
                   f'{theme.TIER_COLORS["Critical"]}"></span>{early_label}</span>')
    return f'<div class="m-net">{"".join(blocks)}</div><div class="m-legend" style="margin-top:24px">{legend}</div>'
