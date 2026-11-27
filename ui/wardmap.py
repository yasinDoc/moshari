"""Ward map: the forecast's risk tiers drawn on real ward outlines, as inline SVG.

The outlines come from ``data/geo/ward_map.json``, built once by ``scripts/build_ward_map.py``
from geoBoundaries (Bangladesh Bureau of Statistics and OCHA ROAP, CC BY 3.0 IGO). Nothing is
downloaded at runtime and no map tiles are used, so the map works offline.

The dataset has no ward locations, so placement is illustrative: each dataset ward is drawn on
the real ward with the same number in its city (see the build script for the exact rule).
"""

from __future__ import annotations

import html
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

from moshari import config as C
from moshari.data import ward_label
from ui import theme
from ui.i18n import num, t, tr

MAP_PATH = Path(__file__).resolve().parents[1] / "data" / "geo" / "ward_map.json"
CONTEXT_FILL = "#DED8CC"          # real wards that are not in the dataset
NO_DATA_FILL = "#CFC8BB"          # dataset wards not in the current forecast (city filter)
PANEL_CITIES = {"dhaka": ("Dhaka North", "Dhaka South"), "ctg": ("Chattogram",),
                "gcc": ("Gazipur",), "ncc": ("Narayanganj",)}
LABEL_SIZE, DOT_R = 30, 58        # in panel units (panels are 1000 wide)
NOTE = ("Ward positions are illustrative: the dataset has no locations, so each ward is drawn on the "
        "real ward with the same number in its city. Gazipur and Narayanganj have no ward outlines in "
        "the source, so their wards are dots inside the city. Boundaries: geoBoundaries (Bangladesh "
        "Bureau of Statistics, OCHA ROAP, 2015), CC BY 3.0 IGO.")


@lru_cache(maxsize=1)
def load_map(path: Path = MAP_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _title(r) -> str:
    return t("{ward}: {tier} risk, {cases:.1f} expected cases (80% range {lo:.1f} to {hi:.1f})",
             ward=tr(ward_label(r.ward_id)), tier=tr(r.tier), cases=r.expected_cases, lo=r.lower_80, hi=r.upper_80)


def _wrap(el: str, ward_id: str, link: dict | None, title: str) -> str:
    if link is None:
        return el
    # ward first, so the link reads ward_forecast?ward=<id>&<settings>
    href = "ward_forecast?" + urlencode({"ward": ward_id, **{k: v for k, v in link.items() if k != "ward"}})
    return (f'<a href="{html.escape(href)}" target="_self" aria-label="{html.escape(title)}. '
            f'{t("Open ward forecast.")}">{el}</a>')


def _label(x: float, y: float, text: str, color: str) -> str:
    return (f'<text x="{x}" y="{y}" font-size="{LABEL_SIZE}" fill="{color}" text-anchor="middle" '
            f'dominant-baseline="central" class="wl">{text}</text>')


def _panel(p: dict, rows: dict, link: dict | None) -> tuple[str, int, int]:
    """One city panel as an SVG string, plus (wards high or above, wards shown)."""
    parts = []
    if p["context"]:
        fill = CONTEXT_FILL if p["wards"] else "#E3DDD1"
        parts.append(f'<path d="{p["context"]}" fill="{fill}" class="ctx"/>')
    labels, high, shown = [], 0, 0
    shapes = [(s["ward_id"], "path", s) for s in p["wards"]] + [(s["ward_id"], "dot", s) for s in p["dots"]]
    for ward_id, kind, s in shapes:
        num_ = ward_id.rsplit("_", 1)[-1]
        r = rows.get(ward_id)
        if kind == "path":
            x, y = s["label"]
        else:
            x, y = s["xy"]
        if r is None:                                  # filtered out in the sidebar: no data, no link
            shape = (f'<path d="{s["d"]}" fill="{NO_DATA_FILL}" class="nd"/>' if kind == "path" else
                     f'<circle cx="{x}" cy="{y}" r="{DOT_R}" fill="{NO_DATA_FILL}" class="nd"/>')
            parts.append(shape)
            continue
        shown += 1
        high += int(r.tier_idx >= 2)
        title = _title(r)
        fill = theme.TIER_COLORS[r.tier]
        attrs = f'data-ward="{ward_id}" fill="{fill}" class="w t{int(r.tier_idx)}"'
        el = (f'<path d="{s["d"]}" {attrs}><title>{html.escape(title)}</title></path>' if kind == "path" else
              f'<circle cx="{x}" cy="{y}" r="{DOT_R}" {attrs}><title>{html.escape(title)}</title></circle>')
        parts.append(_wrap(el, ward_id, link, title))
        labels.append(_label(x, y, num(int(num_)), theme.TIER_TEXT[r.tier]))
    aria = t("{city} ward risk map", city=tr(p["title"]))
    svg = (f'<svg viewBox="0 0 {p["width"]} {p["height"]}" role="img" aria-label="{html.escape(aria)}" '
           f'preserveAspectRatio="xMidYMid meet">{"".join(parts)}{"".join(labels)}</svg>')
    return svg, high, shown


CSS = """
<style>
.m-map{display:flex;gap:18px;align-items:flex-end;flex-wrap:wrap}
.m-map .pn{display:flex;flex-direction:column;gap:6px;min-width:150px}
.m-map .pn .t{font-weight:700;color:var(--ink);font-size:14px}
.m-map .pn .s{color:var(--muted);font-size:12px}
.m-map svg{width:100%;height:auto;display:block}
.m-map .ctx{stroke:#fff;stroke-width:2}
.m-map .nd{stroke:#fff;stroke-width:3}
.m-map .w{stroke:#fff;stroke-width:3;transition:filter .15s}
.m-map a:hover .w,.m-map a:focus .w{stroke:var(--ink);stroke-width:7;filter:brightness(1.05)}
.m-map a:focus{outline:none}
.m-map .wl{font-family:inherit;font-weight:700;pointer-events:none}
.m-map .dim{opacity:.45}
</style>
"""


def ward_map_html(fc: pd.DataFrame, link: dict | None = None, thresholds: list[float] | None = None) -> str:
    """The ward map for one forecast week.

    ``fc``: forecast rows with ward_id, tier, tier_idx, expected_cases, lower_80 and upper_80.
    ``link``: query parameters (issue week, horizon, policy...) that make each ward a link to its
    forecast with the same settings; None draws the map without links.
    """
    m = load_map()
    rows = {r.ward_id: r for r in fc.itertuples(index=False)}
    blocks = []
    for p in m["panels"]:
        svg, high, shown = _panel(p, rows, link)
        total = len(p["wards"]) + len(p["dots"])
        sub = (t("{high} of {shown} wards high or above", high=high, shown=shown) if shown
               else t("Not selected in the sidebar"))
        ratio = p["width"] / p["height"]                 # equal heights: width follows the shape
        blocks.append(f'<div class="pn{"" if shown else " dim"}" style="flex:{ratio:.3f} 1 0">'
                      f'<div class="t">{html.escape(tr(p["title"]))}</div><div class="s">{sub}'
                      f'{"" if shown == total or not shown else t(" ({n} filtered out)", n=total - shown)}</div>{svg}</div>')
    if thresholds:
        bounds = tier_bounds(thresholds)
    else:
        bounds = {n: "" for n in C.TIER_NAMES}
    legend = "".join(f'<span><span class="m-dot" style="background:{theme.TIER_COLORS[n]}"></span><b>{tr(n)}</b>'
                     f'{"&nbsp; " + t("{range} cases", range=bounds[n]) if bounds[n] else ""}</span>'
                     for n in C.TIER_NAMES)
    legend += (f'<span><span class="m-dot" style="background:{CONTEXT_FILL}"></span>{t("Other wards (not in the dataset)")}'
               f'</span>')
    if link is not None:
        legend += f'<span class="hint">{t("Click a ward to open its forecast")}</span>'
    return (f'{CSS}<div class="m-map">{"".join(blocks)}</div>'
            f'<div class="m-legend" style="margin-top:20px">{legend}</div>'
            f'<div class="m-note" style="margin-top:12px">{html.escape(t(NOTE))}</div>')


def tier_bounds(t_: list[float]) -> dict[str, str]:
    """Case ranges of the four tiers for legends: ``under 2``, ``2 to 5``, ``5 to 9``, ``9+``."""
    return {"Low": t("under {a:g}", a=t_[0]), "Medium": t("{a:g} to {b:g}", a=t_[0], b=t_[1]),
            "High": t("{a:g} to {b:g}", a=t_[1], b=t_[2]), "Critical": t("{a:g}+", a=t_[2])}
