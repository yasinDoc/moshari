"""Language of the current session, and Bangla versions of finished Plotly figures.

Every page calls ``t("English text", **args)``; the language comes from the sidebar switch
(``st.session_state["lang"]``, ``"en"`` or ``"bn"``). English output is exactly what the code
wrote before. In Bangla, :func:`localize_figure` rewrites a figure just before it is drawn:
category labels, names and titles through the catalog, and every number or date the browser
would draw (axis ticks, hover labels, bar text) pre-formatted as Bangla text, so no Latin
digit reaches the screen.
"""

from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from moshari import i18n as core

LANGS = core.LANGS
MISSING = core.MISSING
digits = core.digits


def lang() -> str:
    return core.norm(st.session_state.get("lang", "en"))


def is_bn() -> bool:
    return lang() == "bn"


def t(text: str, lang: str | None = None, **kw: Any) -> str:
    return core.t(text, lang or globals()["lang"](), **kw)


def num(x: Any, spec: str = "", lang: str | None = None) -> str:
    return core.num(x, spec, lang or globals()["lang"]())


def week(d, lang: str | None = None) -> str:
    return core.week(d, lang or globals()["lang"]())


def short(d, lang: str | None = None) -> str:
    return core.short(d, lang or globals()["lang"]())


def month(d, lang: str | None = None) -> str:
    return core.month(d, lang or globals()["lang"]())


def ward(ward_id: str, lang: str | None = None) -> str:
    return core.ward(ward_id, lang or globals()["lang"]())


def tier(name: str, lang: str | None = None) -> str:
    return core.tier(name, lang or globals()["lang"]())


def tr(text: Any, lang: str | None = None) -> str:
    return core.tr(text, lang or globals()["lang"]())


def date_fmt(d, fmt: str, lang: str | None = None) -> str:
    return core.date_fmt(d, fmt, lang or globals()["lang"]())


# --------------------------------------------------------------------------- Plotly in Bangla
_FIELD = re.compile(r"%\{([^}|:]+)(?:\|([^}]*)|:([^}]*))?\}")
_EXTRA = re.compile(r"<extra>.*?</extra>", re.S)


def _plain(v: Any) -> Any:
    if isinstance(v, np.generic):
        return v.item()
    return v


def _seq(v: Any) -> list | None:
    if v is None:
        return None
    if isinstance(v, (str, bytes)):
        return None
    if isinstance(v, np.ndarray):
        return [_seq(x) if isinstance(x, np.ndarray) else _plain(x) for x in v]
    if isinstance(v, (list, tuple, pd.Index, pd.Series)):
        return [_seq(x) if isinstance(x, (list, tuple, np.ndarray)) else _plain(x) for x in list(v)]
    return None


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool)


def _is_date(v: Any) -> bool:
    if isinstance(v, (pd.Timestamp, np.datetime64)) or hasattr(v, "strftime"):
        return True
    if isinstance(v, str) and re.match(r"^\d{4}-\d\d-\d\d", v):
        return True
    return False


def _d3(v: Any, spec: str) -> str:
    """A d3-format spec (``.1f``, ``,.0f``, ``.0%``, ``d``) as Python formatting, Bangla digits."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if not _is_num(v):
        return core.tr(v, "bn")
    v = float(v)
    spec = spec.strip()
    if spec in ("", None):
        s = f"{int(round(v))}" if abs(v - round(v)) < 1e-9 else f"{v:.4g}"
    elif spec.endswith("d"):
        s = format(int(round(v)), spec[:-1] + "d")
    elif spec.endswith("s"):
        s = f"{v:,.3g}"
    else:
        try:
            s = format(v, spec)
        except ValueError:
            s = f"{v:g}"
    return core.digits(s.replace("-", "−") if s.startswith("-") else s)


def _value(field: str, point: dict, trace_name: str) -> Any:
    field = field.strip()
    if field in ("fullData.name", "data.name"):
        return trace_name
    m = re.match(r"^(\w+)(?:\[(\d+)\])?$", field)
    if not m:
        return ""
    key, idx = m.group(1), m.group(2)
    v = point.get(key)
    if idx is not None and isinstance(v, (list, tuple)):
        v = v[int(idx)] if int(idx) < len(v) else ""
    return v


def _render(template: str, point: dict, trace_name: str) -> str:
    def sub(m: re.Match) -> str:
        v = _value(m.group(1), point, trace_name)
        date_spec, num_spec = m.group(2), m.group(3)
        if date_spec is not None and _is_date(v):
            return core.date_fmt(v, date_spec, "bn")
        if num_spec is not None or _is_num(v):
            return _d3(v, num_spec or "")
        if _is_date(v):
            return core.date_fmt(v, "%d %b %Y", "bn")
        return core.tr(v, "bn") if v not in (None, "") else ""
    return _FIELD.sub(sub, template)


def _points(trace) -> tuple[list, bool]:
    """Every hover point of a trace as a dict, and whether the trace is 2-D (heatmap)."""
    t = trace.type
    x, y = _seq(trace.x), _seq(trace.y)
    cd = _seq(getattr(trace, "customdata", None))
    text = getattr(trace, "text", None)
    text = _seq(text) if _seq(text) is not None else text
    if t == "heatmap":
        z = _seq(trace.z) or []
        rows = []
        for i, zrow in enumerate(z):
            row = []
            for j, zv in enumerate(zrow or []):
                p = {"z": zv, "x": x[j] if x and j < len(x) else j, "y": y[i] if y and i < len(y) else i}
                if cd is not None:
                    p["customdata"] = cd[i][j]
                if isinstance(text, list):
                    p["text"] = text[i][j]
                row.append(p)
            rows.append(row)
        return rows, True
    n = max(len(x or []), len(y or []))
    pts = []
    for i in range(n):
        p = {"x": x[i] if x and i < len(x) else None, "y": y[i] if y and i < len(y) else None}
        if cd is not None and i < len(cd):
            p["customdata"] = cd[i]
        if isinstance(text, list) and i < len(text):
            p["text"] = text[i]
        elif text is not None and not isinstance(text, list):
            p["text"] = text
        pts.append(p)
    return pts, False


def _map_2d(pts, two_d: bool, fn):
    return [[fn(p) for p in row] for row in pts] if two_d else [fn(p) for p in pts]


def _nice_step(span: float, target: int = 5) -> float:
    if span <= 0:
        return 1.0
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def _axis_values(fig, axis_name: str) -> list:
    letter = axis_name[0]
    ref = letter + axis_name[5:]  # xaxis2 -> x2
    out = []
    stacked = getattr(fig.layout, "barmode", None) in ("stack", "relative")
    stacks: dict = {}
    for tr_ in fig.data:
        if (getattr(tr_, letter + "axis", None) or letter) != ref:
            continue
        vals = _seq(getattr(tr_, letter, None))
        if tr_.type == "heatmap" or vals is None:
            if vals:
                out += vals
            continue
        if tr_.type == "bar":
            other = _seq(getattr(tr_, "y" if letter == "x" else "x", None)) or []
            horizontal = getattr(tr_, "orientation", None) == "h"
            value_axis = (letter == "x") == bool(horizontal)
            if value_axis:
                out.append(0)
            if stacked and value_axis:
                for k, v in zip(other, vals):
                    if _is_num(v):
                        stacks[str(k)] = stacks.get(str(k), 0) + float(v)
                continue
        out += [v for v in vals if v is not None]
    out += list(stacks.values())
    return out


def _ticks_numeric(vals: list, ax) -> tuple[list, list]:
    nums = [float(v) for v in vals if _is_num(v) and not (isinstance(v, float) and math.isnan(v))]
    rng = list(ax.range) if ax.range is not None else None
    lo, hi = (min(nums), max(nums)) if nums else (0.0, 1.0)
    if rng and all(_is_num(r) for r in rng):
        lo, hi = min(rng), max(rng)
    if hi == lo:
        hi = lo + 1
    step = float(ax.dtick) if _is_num(ax.dtick) else _nice_step(hi - lo)
    start = math.floor(lo / step) * step
    vals_out, v = [], start
    while v <= hi + step * 1e-9 and len(vals_out) < 40:
        vals_out.append(round(v, 10))
        v += step
    spec = ax.tickformat or ""
    if not spec:
        spec = ",.0f" if step >= 1 else f".{max(0, -int(math.floor(math.log10(step))))}f"
    suffix = ax.ticksuffix or ""
    prefix = ax.tickprefix or ""
    text = [prefix + _d3(x, spec) + suffix for x in vals_out]
    return vals_out, text


def _ticks_dates(vals: list, ax) -> tuple[list, list]:
    ds = pd.to_datetime(pd.Series([v for v in vals if v is not None]), errors="coerce").dropna()
    if ds.empty:
        return [], []
    lo, hi = ds.min(), ds.max()
    rng = ax.range
    if rng is not None:
        try:
            lo, hi = pd.Timestamp(rng[0]), pd.Timestamp(rng[1])
        except (TypeError, ValueError):
            pass
    span = (hi - lo).days
    fmt = ax.tickformat or ("%b %Y" if span > 400 else "%d %b")
    if span > 75:
        months = pd.date_range(lo.normalize().replace(day=1), hi, freq="MS")
        months = months[months >= lo - pd.Timedelta(days=1)] if len(months) else months
        k = max(1, math.ceil(len(months) / 8))
        ticks = list(months[::k])
    else:
        k = max(1, math.ceil(span / 7 / 7))
        ticks = list(pd.date_range(lo, hi, freq=f"{7 * k}D"))
    return [d.strftime("%Y-%m-%d") for d in ticks], [core.date_fmt(d, fmt, "bn") for d in ticks]


def _translate_seq(v: list) -> list:
    return [core.tr(x, "bn") if isinstance(x, str) else x for x in v]


def localize_figure(fig) -> None:
    """Rewrite a finished figure in place for Bangla mode. Does nothing in English."""
    if not is_bn():
        return
    L = fig.layout
    # titles and annotations
    if L.title and L.title.text:
        L.title.text = core.tr(L.title.text, "bn")
    if L.legend and L.legend.title and L.legend.title.text:
        L.legend.title.text = core.tr(L.legend.title.text, "bn")
    for a in L.annotations or ():
        if a.text:
            a.text = core.tr(a.text, "bn")
    for s in L.shapes or ():
        if getattr(s, "label", None) and s.label.text:
            s.label.text = core.tr(s.label.text, "bn")
    # hover / text, rendered per point with the original (English) values
    for tr_ in fig.data:
        name = tr_.name or ""
        hoverinfo = getattr(tr_, "hoverinfo", None)
        template = getattr(tr_, "hovertemplate", None)
        pts, two_d = _points(tr_)
        if hoverinfo not in ("skip", "none") or template:
            if isinstance(template, (list, tuple)):
                template = template[0] if template else None
            if template:
                body = _EXTRA.sub("", template)
                extra = _EXTRA.search(template)
                extra_txt = extra.group(0)[7:-8] if extra else None
                bn_body = core.t(body, "bn")
                bn_extra = core.t(extra_txt, "bn") if extra_txt else ""
            else:
                bn_body = ("%{fullData.name}<br>" if name else "") + "%{x}: %{y}" if tr_.type != "heatmap" \
                    else "%{x}, %{y}: %{z}"
                bn_extra = ""
            bn_name = core.tr(name, "bn") if name else ""

            def render(p, _b=bn_body, _e=bn_extra, _n=bn_name):
                s = _render(_b, p, _n)
                return s + ("<br>" + _render(_e, p, _n) if _e else "")
            tr_.hovertext = _map_2d(pts, two_d, render)
            tr_.hovertemplate = "%{hovertext}<extra></extra>"
        texttemplate = getattr(tr_, "texttemplate", None)
        text = getattr(tr_, "text", None)
        if texttemplate:
            bn_tt = core.t(texttemplate, "bn")
            tr_.text = _map_2d(pts, two_d, lambda p, _t=bn_tt: _render(_t, p, ""))
            tr_.texttemplate = "%{text}"
        elif text is not None:
            seq = _seq(text)
            if seq is None:
                tr_.text = core.tr(text, "bn") if isinstance(text, str) else _d3(text, "")
            else:
                def fix(v):
                    if isinstance(v, list):
                        return [fix(x) for x in v]
                    return _d3(v, "") if _is_num(v) else core.tr(v, "bn") if isinstance(v, str) else v
                tr_.text = fix(seq)
        if name:
            tr_.name = core.tr(name, "bn")
        if getattr(tr_, "legendgrouptitle", None) and tr_.legendgrouptitle.text:
            tr_.legendgrouptitle.text = core.tr(tr_.legendgrouptitle.text, "bn")
    # axes: categories through the catalog, numbers and dates as Bangla tick text
    axis_names = {k for k in L.to_plotly_json() if re.match(r"^[xy]axis\d*$", k)}
    for tr_ in fig.data:
        for letter in ("x", "y"):
            ref = getattr(tr_, letter + "axis", None) or letter
            axis_names.add(letter + "axis" + ref[1:])
    for name in sorted(axis_names):
        ax = L[name]
        if ax.title and ax.title.text:
            ax.title.text = core.tr(ax.title.text, "bn")
        if ax.visible is False or ax.showticklabels is False:
            continue
        vals = _axis_values(fig, name)
        if ax.tickmode == "array" and ax.ticktext is not None:
            ax.ticktext = [core.tr(x, "bn") for x in ax.ticktext]
            continue
        strings = [v for v in vals if isinstance(v, str)]
        if (ax.type == "category" or (strings and len(strings) == len([v for v in vals if v is not None])
                                       and not any(_is_date(s) for s in strings[:3]))):
            letter = name[0]
            ref = letter + name[5:]
            for tr_ in fig.data:
                if (getattr(tr_, letter + "axis", None) or letter) == ref:
                    seq = _seq(getattr(tr_, letter, None))
                    if seq is not None:
                        setattr(tr_, letter, _translate_seq(seq))
            continue
        if any(_is_date(v) for v in vals[:5]) and not any(_is_num(v) for v in vals[:5]):
            tickvals, ticktext = _ticks_dates(vals, ax)
        else:
            tickvals, ticktext = _ticks_numeric(vals, ax)
        ax.tickmode, ax.tickvals, ax.ticktext = "array", tickvals, ticktext
        ax.ticksuffix = None
        ax.tickprefix = None


def bound(fn):
    """``fn(value, lang)`` with today's language fixed, for widget ``format_func``s (Streamlit may
    call them later, outside this script run)."""
    lng = lang()
    return lambda v: fn(v, lng)


# --------------------------------------------------------------------------- tables in Bangla
def _cell_text(v: Any, spec: str | None) -> Any:
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT:
        return ""
    if isinstance(v, (bool, np.bool_)):
        return core.t("Yes" if v else "No", "bn")
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        return core.week(v, "bn")
    if _is_num(v):
        v = _plain(v)
        if callable(spec):
            return core.digits(spec(v))
        if spec is None:
            spec = "d" if float(v).is_integer() and isinstance(v, int) else ".2f"
        return core.digits(format(v, spec))
    if isinstance(v, str):
        return core.tr(v, "bn")
    return v


def frame(df: pd.DataFrame, column_config: dict | None = None,
          formats: dict | None = None) -> tuple[pd.DataFrame, dict | None]:
    """``(df, column_config)`` for ``st.dataframe`` in the current language.

    English returns both unchanged. Bangla returns the same rows and columns with the headers
    through the catalog and every cell as Bangla text (numbers formatted with ``formats[col]``,
    a Python format spec or a function of the value), so the browser never draws a Latin digit. Column help texts are
    kept, translated, on plain text columns.
    """
    if not is_bn():
        return df, column_config
    formats = formats or {}
    out = pd.DataFrame(index=df.index)
    cfg: dict = {}
    for c in df.columns:
        label = core.tr(c, "bn")
        out[label] = [_cell_text(v, formats.get(c)) for v in df[c]]
        old = (column_config or {}).get(c)
        if old is not None:
            old = dict(old)
            keep = {k: old[k] for k in ("width", "pinned") if old.get(k) is not None}
            if old.get("help"):
                keep["help"] = core.t(old["help"], "bn")
            cfg[label] = st.column_config.TextColumn(label, **keep)
    return out, cfg or None


def deficit_note(r) -> str:
    """Allocation status of one ward (``moshari.allocation.allocate`` row) in the current language."""
    if not is_bn():
        return r["deficit_note"]
    names = (("saline_bags_needed", "saline_bags_allocated", "স্যালাইন ব্যাগ"),
             ("diagnostic_kits_needed", "diagnostic_kits_allocated", "টেস্ট কিট"),
             ("hospital_beds_required", "hospital_beds_allocated", "শয্যা"))
    short = [f"{core.digits(int(r[n] - r[a]))}টি {label}" for n, a, label in names if r[a] < r[n]]
    gap = int(r["crews_needed"] - r["crews_assigned"])
    parts = ([f"ঘাটতি: {', '.join(short)}"] if short else []) + (
        [f"আরও {core.digits(gap)}টি দল দরকার"] if gap > 0 else [])
    return "; ".join(parts) if parts else "পুরো সরবরাহ পাওয়া গেছে"
