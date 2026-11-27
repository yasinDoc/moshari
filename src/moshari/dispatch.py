"""Dispatch notices (Phase 2, module 4): allocation + routing -> messages officers act on.

Three formats per ward, all from plain string templates (no LLM, no internet), so
they work offline and give the same text for the same inputs:

* :func:`sms` – one plain-text SMS that always fits a single 160-character GSM-7
  segment. Optional details are dropped or shortened in a fixed order until it fits,
  so the risk, the supplies and any deficit are never cut.
* :func:`whatsapp` – a short message with WhatsApp formatting (``*bold*``, line breaks).
* :func:`brief_html` – a printable one-page commissioner brief (A4, "Print / Save as PDF").
  :func:`briefs_html` puts several wards in one document, one page each.

Input is one row of the dispatch table built by :func:`dispatch_table`: the
allocation table (``allocate(...)``, see TASKS.md) with each ward's hospital
overflow transfers from ``route_overflow(...)`` merged in. Missing optional fields
(routing, crews, probabilities) are skipped rather than failing, so the templates
also work on a partial table.
"""

from __future__ import annotations

import html
import io
import math
import sys
import zipfile
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from . import config as C
from .data import corporation_of, ward_label
from .risk import TIERS

SENDER = "DGHS"          # signature at the end of every notice
SMS_LIMIT = 160          # one GSM-7 SMS segment
TIER_EMOJI = {"Low": "🟢", "Medium": "🟡", "High": "🟠", "Critical": "🔴"}

# (demand column, allocated column, long label, SMS label)
SUPPLIES = [
    ("saline_bags_needed", "saline_bags_allocated", "Saline bags", "saline"),
    ("diagnostic_kits_needed", "diagnostic_kits_allocated", "Test kits", "kits"),
    ("hospital_beds_required", "hospital_beds_allocated", "Hospital beds", "beds"),
]

# Fallback per-case demand ratios, fitted from the onsite data (see TASKS.md), used
# only by :func:`standin_allocation` while the allocation engine is not available.
STANDIN_RATIOS = {"saline_bags_needed": 2.39, "diagnostic_kits_needed": 1.16, "hospital_beds_required": 0.30}

# GSM 03.38: the basic set costs 1 septet per character, the extension set 2.
_GSM_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM_EXT = set("^{}\\[~]|€\f")


# --------------------------------------------------------------------------- small helpers
def _get(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    """``row[key]``, or ``default`` if it is missing or NaN."""
    try:
        v = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    if v is None:
        return default
    if isinstance(v, float) and math.isnan(v):
        return default
    return v


def _int(row: Mapping[str, Any], key: str, default: int = 0) -> int:
    v = _get(row, key)
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def _plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word if n == 1 else (many or word + 's')}"


def ward_code(ward_id: str) -> str:
    """'DNCC_Ward_12' -> 'DNCC-W12' (compact id for SMS)."""
    corp, _, rest = str(ward_id).partition("_")
    num = rest.rsplit("_", 1)[-1] if rest else ""
    return f"{corp}-W{num}" if num.isdigit() else str(ward_id)


def short_ward(ward_id: str, home_corp: str | None = None) -> str:
    """'DNCC_Ward_03' -> 'W03' inside the same corporation, else 'DNCC-W03'."""
    code = ward_code(ward_id)
    corp = corporation_of(str(ward_id))
    return code.split("-", 1)[1] if home_corp and corp == home_corp and "-" in code else code


def target_week(row: Mapping[str, Any]) -> pd.Timestamp | None:
    """The week the notice is about: ``target_date``, else ``date`` + ``horizon``, else ``date``."""
    t = _get(row, "target_date")
    if t is not None:
        return pd.Timestamp(t)
    d = _get(row, C.DATE_COL)
    if d is None:
        return None
    h = _get(row, "horizon")
    return pd.Timestamp(d) + pd.Timedelta(weeks=int(h)) if h is not None else pd.Timestamp(d)


def _cases_text(x: float, approx: str = "~") -> str:
    if x < 0.5:
        return "<1 case"
    n = int(round(x))
    return f"{approx}{_plural(n, 'case')}"


def gsm_length(text: str) -> int:
    """Length in GSM-7 septets (what the 160 limit counts). Non-GSM characters force
    UCS-2 encoding, where the limit drops to 70, so they count as 160 / 70 each."""
    n = 0.0
    for ch in text:
        if ch in _GSM_BASIC:
            n += 1
        elif ch in _GSM_EXT:
            n += 2
        else:
            n += SMS_LIMIT / 70
    return int(math.ceil(n - 1e-9))


def supply_lines(row: Mapping[str, Any]) -> list[dict]:
    """One dict per supply: label, needed, allocated, gap (only supplies present in ``row``)."""
    out = []
    for need_col, got_col, label, short in SUPPLIES:
        if _get(row, need_col) is None:
            continue
        need = _int(row, need_col)
        got = _int(row, got_col, need)
        out.append({"label": label, "short": short, "needed": need, "allocated": got,
                    "gap": max(need - got, 0)})
    return out


def _transfers(row: Mapping[str, Any], key: str) -> list[tuple[str, int]]:
    v = _get(row, key)
    if v is None or isinstance(v, (float, str)):
        return []
    return [(str(w), int(p)) for w, p in v if int(p) > 0]


def _crews(row: Mapping[str, Any]) -> tuple[int | None, int | None]:
    got = _get(row, "crews_assigned")
    need = _get(row, "crews_needed")
    return (None if got is None else int(got)), (None if need is None else int(need))


def actions(row: Mapping[str, Any]) -> list[str]:
    """Plain-language actions for this ward, most urgent first."""
    tier = str(_get(row, "tier", "Low"))
    out: list[str] = [f"{TIERS[tier].action}: {TIERS[tier].detail}" if tier in TIERS else "Routine surveillance."]
    for t, p in _transfers(row, "transfers_out"):
        out.append(f"Transfer {_plural(p, 'patient')} to {ward_label(t)} (beds confirmed there).")
    for f, p in _transfers(row, "transfers_in"):
        out.append(f"Prepare {_plural(p, 'bed')} for patients arriving from {ward_label(f)}.")
    unplaced = _int(row, "net_deficit")
    if unplaced:
        out.append(f"{_plural(unplaced, 'patient')} still {'has' if unplaced == 1 else 'have'} no bed in the city: "
                   "open surge beds or escalate to the city health office.")
    for s in supply_lines(row):
        if s["gap"]:
            out.append(f"Request {s['gap']} more {s['label'].lower()} from the regional store; "
                       f"ration the {s['allocated']} received for confirmed cases first.")
    got, need = _crews(row)
    if got is not None and need is not None and need > got:
        out.append(f"Ask the city corporation for {_plural(need - got, 'more spraying crew')}.")
    return out


def deficit_text(row: Mapping[str, Any]) -> str:
    """'Short 8 saline bags, 3 test kits; 1 more crew needed; 2 patients without a bed', or ''."""
    parts = []
    short = [f"{s['gap']} {s['label'].lower()}" for s in supply_lines(row) if s["gap"]]
    if short:
        parts.append("Short " + ", ".join(short))
    got, need = _crews(row)
    if got is not None and need is not None and need > got:
        parts.append(f"{_plural(need - got, 'more crew')} needed")
    unplaced = _int(row, "net_deficit")
    if unplaced:
        parts.append(f"{_plural(unplaced, 'patient')} without a bed")
    return "; ".join(parts)


def deficit_items(row: Mapping[str, Any]) -> list[str]:
    """Short names of everything this ward is short of (supplies, then crews, then beds)."""
    items = [s["short"] for s in supply_lines(row) if s["gap"]]
    got, need = _crews(row)
    if got is not None and need is not None and need > got:
        items.append("crews")
    if _int(row, "net_deficit") and "beds" not in items:
        items.append("beds")
    return items


# --------------------------------------------------------------------------- SMS
def sms(row: Mapping[str, Any], sender: str = SENDER, limit: int = SMS_LIMIT) -> str:
    """One SMS of at most ``limit`` GSM-7 characters.

    Example: ``MOSHARI DNCC-W12: HIGH risk, ~10 cases wk of 23 Jun. Saline 32/40,
    kits 9/12, beds 3/3. DEFICIT saline, kits. Crews: 2. -DGHS``
    """
    ward = str(_get(row, C.WARD_COL, "ward"))
    home = corporation_of(ward)
    tier = str(_get(row, "tier", "Low")).upper()
    week = target_week(row)
    cases = float(_get(row, "expected_cases", 0.0))
    supplies = supply_lines(row)
    deficits = deficit_items(row)
    got, need = _crews(row)
    outs = _transfers(row, "transfers_out")
    ins = _transfers(row, "transfers_in")
    unplaced = _int(row, "net_deficit")

    week_long = f" wk of {week:%d %b}" if week is not None else ""
    week_short = f" wk {week:%d %b}" if week is not None else ""

    # Each part: list of variants, longest first; "" means the part can be dropped.
    parts: dict[str, list[str]] = {
        "head": [f"MOSHARI {ward_code(ward)}: {tier} risk, {_cases_text(cases)}{week_long}.",
                 f"MOSHARI {ward_code(ward)}: {tier}, {_cases_text(cases)}{week_short}.",
                 f"{ward_code(ward)}: {tier}, {_cases_text(cases, '')}{week_short}."],
        "supplies": [
            " " + ", ".join(f"{s['short'].capitalize() if i == 0 else s['short']} {s['allocated']}/{s['needed']}"
                            for i, s in enumerate(supplies)) + "." if supplies else "",
            " " + ",".join(f"{s['short'][0].upper()}{s['allocated']}/{s['needed']}" for s in supplies) + "."
            if supplies else "",
        ],
        "deficit": [f" DEFICIT {', '.join(deficits)}." if deficits else " Fully supplied.",
                    f" SHORT {','.join(deficits)}." if deficits else " OK.",
                    f" SHORT {','.join(deficits)}." if deficits else ""],
        "crews": [f" Crews: {got}{f' of {need}' if need and need > got else ''}." if got is not None else "",
                  f" Crews {got}." if got is not None else "", ""],
        "beds": [
            " " + " ".join([*(f"Send {p} pt to {short_ward(t, home)}." if p == 1 else
                              f"Send {p} pts to {short_ward(t, home)}." for t, p in outs),
                            *([f"Receive {sum(p for _, p in ins)} pts."] if ins else []),
                            *([f"{unplaced} pts unplaced."] if unplaced else [])]).rstrip()
            if (outs or ins or unplaced) else "",
            (f" Transfer {sum(p for _, p in outs)} pts." if outs else "")
            + (f" Receive {sum(p for _, p in ins)} pts." if ins else "")
            + (f" {unplaced} unplaced." if unplaced else ""),
            (f" {unplaced} pts no bed." if unplaced else ""),
            "",
        ],
        "action": [f" {TIERS[_get(row, 'tier', 'Low')].action}." if _get(row, "tier") in TIERS else "", ""],
        "sign": [f" -{sender}" if sender else "", ""],
    }
    order = ["head", "supplies", "deficit", "crews", "beds", "action", "sign"]
    # Which part to shorten next when too long: least important first.
    shrink = ["action", "beds", "beds", "sign", "crews", "beds", "supplies", "deficit", "crews",
              "head", "deficit", "head"]
    level = dict.fromkeys(order, 0)

    def render() -> str:
        return "".join(parts[k][min(level[k], len(parts[k]) - 1)] for k in order).strip()

    text = render()
    for k in shrink:
        if gsm_length(text) <= limit:
            break
        if level[k] < len(parts[k]) - 1:
            level[k] += 1
            text = render()
    if gsm_length(text) > limit:  # last resort; unreachable for real ward ids
        while gsm_length(text) > limit - 1:
            text = text[:-1]
        text = text.rstrip() + "…" if gsm_length(text + "…") <= limit else text
    return text


# --------------------------------------------------------------------------- WhatsApp
def whatsapp(row: Mapping[str, Any], sender: str = SENDER) -> str:
    """A short WhatsApp message: risk, supplies (allocated / needed), crews, beds, actions."""
    ward = str(_get(row, C.WARD_COL, "ward"))
    tier = str(_get(row, "tier", "Low"))
    corp = corporation_of(ward)
    week = target_week(row)
    cases = float(_get(row, "expected_cases", 0.0))
    lo, hi = _get(row, "lower_80"), _get(row, "upper_80")
    p_crit = _get(row, "p_crit")

    lines = [f"{TIER_EMOJI.get(tier, '')} *MOSHARI dispatch: {ward_label(ward)}*".strip()]
    sub = C.CITY_CORPORATIONS.get(corp, str(_get(row, C.CITY_COL, "")))
    if week is not None:
        sub += f" · week of {week:%d %b %Y}"
    lines.append(f"_{sub}_")
    lines.append("")

    risk = f"*Risk:* {tier.upper()}, {_cases_text(cases)} expected"
    if lo is not None and hi is not None:
        risk += f" (likely {float(lo):.0f} to {float(hi):.0f})"
    lines.append(risk)
    if p_crit is not None and float(p_crit) >= 0.05:
        lines.append(f"*Outbreak chance:* {float(p_crit):.0%}")

    supplies = supply_lines(row)
    if supplies:
        lines.append("")
        lines.append("*Supplies* (allocated / needed)")
        for s in supplies:
            flag = f"  ⚠️ short {s['gap']}" if s["gap"] else "  ✅"
            lines.append(f"• {s['label']}: {s['allocated']} / {s['needed']}{flag}")

    got, need = _crews(row)
    if got is not None:
        crew = f"*Spraying crews:* {got} assigned"
        if need is not None and need > got:
            crew += f" (needs {need}) ⚠️"
        lines.append("")
        lines.append(crew)

    outs, ins, unplaced = _transfers(row, "transfers_out"), _transfers(row, "transfers_in"), _int(row, "net_deficit")
    if outs or ins or unplaced:
        lines.append("")
        lines.append("*Hospital overflow:*")
        lines += [f"• Send {_plural(p, 'patient')} to {ward_label(t)}" for t, p in outs]
        lines += [f"• Receive {_plural(p, 'patient')} from {ward_label(f)}" for f, p in ins]
        if unplaced:
            lines.append(f"• ⚠️ {_plural(unplaced, 'patient')} without a bed in the city")

    gap = deficit_text(row)
    lines.append("")
    if gap:
        lines.append(f"⚠️ *DEFICIT:* {gap}")
        lines.append("")
    lines.append("*Do now:*")
    lines += [f"{i}. {a}" for i, a in enumerate(actions(row)[:4], 1)]
    if sender:
        lines.append("")
        lines.append(f"— Moshari / {sender}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- commissioner brief
_BRIEF_CSS = """
:root { --ink:#1d2433; --muted:#5d6678; --line:#d9dee8; --accent:#2f6f8f; --bad:#8F1D30; --ok:#256E4A; }
* { box-sizing:border-box; }
body { margin:0; background:#eef1f6; color:var(--ink);
  font:14px/1.45 -apple-system, "Segoe UI", Roboto, "Noto Sans Bengali", Arial, sans-serif; }
.bar { position:sticky; top:0; display:flex; justify-content:space-between; align-items:center; gap:12px;
  padding:10px 16px; background:#fff; border-bottom:1px solid var(--line); z-index:2; }
.bar b { font-size:14px; }
.bar button { font:inherit; font-weight:700; padding:8px 18px; border:0; border-radius:8px; cursor:pointer;
  background:var(--accent); color:#fff; }
.bar button:focus-visible { outline:3px solid #f4cc55; outline-offset:2px; }
.page { width:210mm; min-height:297mm; margin:16px auto; padding:16mm 16mm 14mm; background:#fff;
  box-shadow:0 2px 12px rgba(20,30,50,.12); display:flex; flex-direction:column; }
header { display:flex; justify-content:space-between; align-items:flex-start; gap:16px;
  border-bottom:3px solid var(--tier); padding-bottom:10px; }
header .k { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.08em; font-weight:700; }
header h1 { margin:2px 0 2px; font-size:24px; }
header .sub { color:var(--muted); }
.tier { padding:6px 14px; border-radius:999px; font-weight:800; font-size:15px; white-space:nowrap;
  background:var(--tier); color:var(--tier-ink); }
.kpis { display:grid; grid-template-columns:repeat(4, 1fr); gap:10px; margin:14px 0 4px; }
.kpi { border:1px solid var(--line); border-radius:10px; padding:8px 10px; }
.kpi .l { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; font-weight:700; }
.kpi .v { font-size:20px; font-weight:800; }
.kpi .s { color:var(--muted); font-size:12px; }
h2 { font-size:13px; text-transform:uppercase; letter-spacing:.06em; color:var(--accent); margin:16px 0 6px; }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); }
th { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
td.n, th.n { text-align:right; font-variant-numeric:tabular-nums; }
.gap { color:var(--bad); font-weight:800; }
.okc { color:var(--ok); font-weight:700; }
.alert { margin:10px 0 0; padding:8px 12px; border-left:4px solid var(--bad); background:#fbeef0; border-radius:4px; }
.fine { margin:10px 0 0; padding:8px 12px; border-left:4px solid var(--ok); background:#eef7f1; border-radius:4px; }
ol { margin:4px 0 0; padding-left:20px; } ol li { margin:3px 0; }
ul.plain { margin:4px 0 0; padding-left:18px; }
footer { margin-top:auto; padding-top:10px; border-top:1px solid var(--line); color:var(--muted); font-size:11px;
  display:flex; justify-content:space-between; gap:12px; }
.sig { margin-top:18px; display:flex; gap:40px; color:var(--muted); font-size:12px; }
.sig div { flex:1; border-top:1px solid var(--ink); padding-top:4px; }
@page { size:A4; margin:0; }
@media print {
  body { background:#fff; }
  .bar { display:none; }
  .page { margin:0; box-shadow:none; page-break-after:always; break-after:page; }
  .page:last-child { page-break-after:auto; break-after:auto; }
  * { -webkit-print-color-adjust:exact; print-color-adjust:exact; }
}
@media screen and (max-width: 820px) {
  .page { width:auto; min-height:0; margin:8px; padding:18px; }
  .kpis { grid-template-columns:repeat(2, 1fr); }
}
"""


def _gap_cell(gap: int) -> str:
    return f'<span class="gap">-{gap:,}</span>' if gap else '<span class="okc">none</span>'


def _brief_page(row: Mapping[str, Any], sender: str) -> str:
    e = html.escape
    ward = str(_get(row, C.WARD_COL, "ward"))
    tier = str(_get(row, "tier", "Low"))
    t = TIERS.get(tier, TIERS["Low"])
    corp = corporation_of(ward)
    week = target_week(row)
    issued = _get(row, C.DATE_COL)
    cases = float(_get(row, "expected_cases", 0.0))
    lo, hi, p_crit = _get(row, "lower_80"), _get(row, "upper_80"), _get(row, "p_crit")
    rank = _get(row, "priority_rank")
    got, need = _crews(row)

    kpis = [
        ("Expected cases", f"{cases:.0f}" if cases >= 0.5 else "&lt;1",
         f"likely {float(lo):.0f} to {float(hi):.0f}" if lo is not None and hi is not None else ""),
        ("Outbreak chance", f"{float(p_crit):.0%}" if p_crit is not None else "n/a", "chance of Critical level"),
        ("Spraying crews", f"{got}" if got is not None else "n/a",
         (f"needs {need}" if need is not None and need > got else "assigned") if got is not None else ""),
        ("Priority", f"#{int(rank)}" if rank is not None else "n/a", "in the region this week"),
    ]
    kpi_html = "".join(f'<div class="kpi"><div class="l">{e(l)}</div><div class="v">{v}</div>'
                       f'<div class="s">{e(s)}</div></div>' for l, v, s in kpis)

    supplies = supply_lines(row)
    rows_html = "".join(
        f"<tr><td>{e(s['label'])}</td><td class=n>{s['needed']:,}</td><td class=n>{s['allocated']:,}</td>"
        f"<td class=n>{_gap_cell(s['gap'])}</td>"
        f"<td class=n>{(s['allocated'] / s['needed'] if s['needed'] else 1):.0%}</td></tr>"
        for s in supplies)
    supply_html = (
        '<table><thead><tr><th>Supply</th><th class=n>Required</th><th class=n>Allocated</th>'
        f'<th class=n>Gap</th><th class=n>Filled</th></tr></thead><tbody>{rows_html}</tbody></table>'
        if supplies else "<p>No supply data.</p>")

    gap = deficit_text(row)
    if gap:
        status = f'<div class="alert"><b>Deficit:</b> {e(gap)}.</div>'
    else:
        status = '<div class="fine"><b>Fully supplied</b> for the planned caseload.</div>'

    outs, ins, unplaced = _transfers(row, "transfers_out"), _transfers(row, "transfers_in"), _int(row, "net_deficit")
    cap = _get(row, "bed_capacity")
    beds = []
    if cap is not None:
        beds.append(f"<li>Normal bed capacity: <b>{int(cap)}</b>; required this week: "
                    f"<b>{_int(row, 'hospital_beds_required')}</b>.</li>")
    beds += [f"<li>Send <b>{_plural(p, 'patient')}</b> to {e(ward_label(w))}.</li>" for w, p in outs]
    beds += [f"<li>Receive <b>{_plural(p, 'patient')}</b> from {e(ward_label(w))}.</li>" for w, p in ins]
    if unplaced:
        beds.append(f'<li class="gap">{_plural(unplaced, "patient")} without a bed anywhere in the city.</li>')
    if not (outs or ins or unplaced):
        beds.append("<li>No transfers needed: the ward's own beds cover the forecast.</li>")
    beds_html = f'<ul class="plain">{"".join(beds)}</ul>'

    acts = "".join(f"<li>{e(a)}</li>" for a in actions(row))
    when = f"Week of {week:%d %B %Y}" if week is not None else ""
    issued_txt = f"Forecast issued {pd.Timestamp(issued):%d %b %Y}" if issued is not None else ""
    city = C.CITY_CORPORATIONS.get(corp, str(_get(row, C.CITY_COL, "")))

    return f"""<section class="page" style="--tier:{t.color};--tier-ink:{'#fff' if tier in ('High', 'Critical') else '#1d2433'}">
<header><div><div class="k">Commissioner brief · dengue response</div><h1>{e(ward_label(ward))}</h1>
<div class="sub">{e(city)} · {e(when)}</div></div>
<span class="tier">{e(tier)} risk</span></header>
<div class="kpis">{kpi_html}</div>
<h2>Supplies</h2>{supply_html}{status}
<h2>Hospital beds and overflow</h2>{beds_html}
<h2>Actions</h2><ol>{acts}</ol>
<div class="sig"><div>Ward health officer</div><div>City corporation commissioner</div></div>
<footer><span>Moshari early warning · {e(issued_txt)}</span><span>Prepared offline for {e(sender)}. Forecasts are estimates; confirm with ward surveillance.</span></footer>
</section>"""


def briefs_html(rows: Iterable[Mapping[str, Any]], sender: str = SENDER, title: str | None = None) -> str:
    """One printable HTML document with a page per ward and a Print / Save as PDF button."""
    rows = list(rows)
    pages = "".join(_brief_page(r, sender) for r in rows)
    n = len(rows)
    label = title or (ward_label(str(_get(rows[0], C.WARD_COL, ""))) if n == 1 else f"{n} wards")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Moshari brief: {html.escape(label)}</title><style>{_BRIEF_CSS}</style></head><body>"
        f'<div class="bar"><b>Commissioner brief · {html.escape(label)}</b>'
        '<button type="button" onclick="window.print()">Print / Save as PDF</button></div>'
        f"{pages}</body></html>"
    )


def brief_html(row: Mapping[str, Any], sender: str = SENDER) -> str:
    """A printable one-page commissioner brief for one ward."""
    return briefs_html([row], sender)


# --------------------------------------------------------------------------- building the table
def standin_allocation(fc: pd.DataFrame, ratios: Mapping[str, float] = STANDIN_RATIOS,
                       cases_per_crew: float = 5.0) -> pd.DataFrame:
    """Allocation-shaped table with *full* supply, for when the allocation engine is absent.

    Demand uses the onsite per-case ratios, rounded up; High and Critical wards get one
    crew per ``cases_per_crew`` expected cases. Nothing is scarce, so no deficits.
    """
    df = fc.copy()
    cases = df["expected_cases"].astype(float).clip(lower=0)
    for need_col, got_col, _, _ in SUPPLIES:
        df[need_col] = np.ceil(cases * ratios[need_col] - 1e-9).astype(int)
        df[got_col] = df[need_col]
    crew = df["tier_idx"] >= 2
    df["crews_needed"] = np.where(crew, np.maximum(np.ceil(cases / cases_per_crew), 1), 0).astype(int)
    df["crews_assigned"] = df["crews_needed"]
    df["priority_score"] = (df["tier_idx"] * 100 + cases).round(2)
    df = df.sort_values(["priority_score", C.WARD_COL], ascending=[False, True]).reset_index(drop=True)
    df["priority_rank"] = np.arange(1, len(df) + 1)
    df["deficit_flag"] = False
    df["deficit_note"] = "Fully supplied"
    return df


def dispatch_table(alloc: pd.DataFrame, routing: Any = None) -> pd.DataFrame:
    """The allocation table with each ward's routing merged in, one row per ward.

    ``routing`` is ``route_overflow(...)``'s result (or a ``(transfers, ward_summary,
    city_summary)`` tuple), or None. Adds ``transfers_out`` / ``transfers_in`` (lists of
    ``(ward_id, patients)``), ``bed_capacity`` and ``net_deficit`` where available.
    """
    df = alloc.copy()
    df["transfers_out"] = [[] for _ in range(len(df))]
    df["transfers_in"] = [[] for _ in range(len(df))]
    if routing is None:
        return df
    transfers, ward_summary = tuple(routing)[:2]
    if transfers is not None and len(transfers):
        outs = transfers.groupby("from_ward")[["to_ward", "patients"]].apply(
            lambda g: list(zip(g["to_ward"], g["patients"].astype(int))))
        ins = transfers.groupby("to_ward")[["from_ward", "patients"]].apply(
            lambda g: list(zip(g["from_ward"], g["patients"].astype(int))))
        df["transfers_out"] = [outs.get(w, []) for w in df[C.WARD_COL]]
        df["transfers_in"] = [ins.get(w, []) for w in df[C.WARD_COL]]
    if ward_summary is not None and len(ward_summary):
        ws = ward_summary.set_index(C.WARD_COL)
        for col in ("bed_capacity", "net_deficit"):
            if col in ws:
                df[col] = df[C.WARD_COL].map(ws[col])
    return df


def select_rows(table: pd.DataFrame, mode: str = "high", wards: Iterable[str] | None = None) -> pd.DataFrame:
    """Rows to dispatch: ``"high"`` (High and Critical), ``"deficit"`` (any shortfall), ``"all"``,
    or ``"pick"`` (the given ``wards``). Keeps the table's priority order."""
    if mode == "high":
        mask = table["tier_idx"] >= 2
    elif mode == "deficit":
        mask = pd.Series([bool(deficit_items(r)) for r in table.to_dict("records")], index=table.index)
    elif mode == "pick":
        mask = table[C.WARD_COL].isin(list(wards or []))
    else:
        mask = pd.Series(True, index=table.index)
    return table[mask]


LANGUAGES = {"en": "English", "bn": "বাংলা"}


def templates(lang: str = "en"):
    """The module with ``sms``, ``whatsapp``, ``brief_html`` and ``briefs_html`` for ``lang``."""
    if lang == "bn":
        from . import dispatch_bn

        return dispatch_bn
    if lang != "en":
        raise ValueError(f"unknown language {lang!r}; use one of {sorted(LANGUAGES)}")
    return sys.modules[__name__]


def export_zip(rows: Iterable[Mapping[str, Any]], sender: str = SENDER, lang: str = "en") -> bytes:
    """A zip with ``sms/<ward>.txt``, ``whatsapp/<ward>.txt``, ``briefs/<ward>.html`` and
    ``briefs/all_briefs.html`` (the same layout as the ``exports/`` folder), in ``lang``."""
    rows = list(rows)
    t = templates(lang)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r in rows:
            w = str(_get(r, C.WARD_COL, "ward"))
            z.writestr(f"sms/{w}.txt", t.sms(r, sender) + "\n")
            z.writestr(f"whatsapp/{w}.txt", t.whatsapp(r, sender) + "\n")
            z.writestr(f"briefs/{w}.html", t.brief_html(r, sender))
        if rows:
            z.writestr("briefs/all_briefs.html", t.briefs_html(rows, sender))
    return buf.getvalue()
