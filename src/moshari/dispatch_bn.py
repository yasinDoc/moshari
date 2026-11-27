"""Bangla (বাংলা) dispatch notices: the same SMS, WhatsApp message and brief as
:mod:`moshari.dispatch`, written for ward officers who work in Bangla.

Same inputs, same rules, same offline fixed templates; only the language changes:

* numbers and dates use Bangla digits and month names (``২৩ জুন``);
* ward codes in the SMS stay in Latin letters (``DNCC-W12``) so they match the IDs
  every system uses, while ward names elsewhere read ``DNCC ওয়ার্ড ১২``;
* Bangla is not in the GSM-7 alphabet, so an SMS goes out as Unicode (UCS-2): 70
  characters in a single SMS, or 67 per part when it is split. The Bangla SMS is held
  to at most **two parts** (134 characters), shortening optional details in the same
  fixed order as the English one, so the risk, the supplies and any deficit are never cut.

The English module is left untouched, so its tested output (and ``exports/``) is unchanged.
"""

from __future__ import annotations

import html
import math
from typing import Any, Iterable, Mapping

import pandas as pd

from . import config as C
from .data import corporation_of, ward_label
from .dispatch import (
    _BRIEF_CSS,
    _GSM_BASIC,
    _GSM_EXT,
    SENDER,
    SMS_LIMIT,
    TIER_EMOJI,
    _crews,
    _get,
    _int,
    _transfers,
    deficit_items,
    supply_lines,
    target_week,
    ward_code,
)
from .risk import TIERS

UCS2_SINGLE = 70          # one Unicode SMS
UCS2_PART = 67            # each part of a split Unicode SMS (3 units go to the join header)
GSM_PART = 153
BN_SMS_PARTS = 2
BN_SMS_LIMIT = BN_SMS_PARTS * UCS2_PART   # 134 characters

_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
MONTHS = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর",
          "অক্টোবর", "নভেম্বর", "ডিসেম্বর"]
TIER_BN = {"Low": "নিম্ন", "Medium": "মাঝারি", "High": "উচ্চ", "Critical": "সংকটজনক"}
ACTION_BN = {
    "Low": ("নিয়মিত নজরদারি",
            "সাপ্তাহিক লার্ভা জরিপ ও এলাকাভিত্তিক পরিচ্ছন্নতা প্রচারণা নির্ধারিত সময়ে চালিয়ে যান।"),
    "Medium": ("উৎস নির্মূল",
               "নালা ও জমে থাকা পানির পাত্র পরিষ্কার করুন; পরিচিত প্রজননস্থলে লার্ভিসাইড প্রয়োগের সময়সূচি করুন।"),
    "High": ("লক্ষ্যভিত্তিক মশা নিয়ন্ত্রণ",
             "এই সপ্তাহেই লার্ভিসাইড ও ফগিং দল পাঠান; ওয়ার্ড স্বাস্থ্যকর্মীদের অবহিত করুন; কাছের হাসপাতালগুলোকে জানান।"),
    "Critical": ("প্রাদুর্ভাব মোকাবিলা",
                 "৪৮ ঘণ্টার মধ্যে মশা নিয়ন্ত্রণ, বাড়ি বাড়ি উৎস নির্মূল; স্যালাইন, শয্যা ও NS1 টেস্ট কিট আগেভাগে মজুত করুন।"),
}
CITY_BN = {
    "CCC": "চট্টগ্রাম সিটি কর্পোরেশন",
    "DNCC": "ঢাকা উত্তর সিটি কর্পোরেশন",
    "DSCC": "ঢাকা দক্ষিণ সিটি কর্পোরেশন",
    "GCC": "গাজীপুর সিটি কর্পোরেশন",
    "NCC": "নারায়ণগঞ্জ সিটি কর্পোরেশন",
}
# English supply label -> (long Bangla label, short Bangla label used in the SMS)
SUPPLY_BN = {"Saline bags": ("স্যালাইন ব্যাগ", "স্যালাইন"), "Test kits": ("টেস্ট কিট", "কিট"),
             "Hospital beds": ("হাসপাতাল শয্যা", "শয্যা")}
ITEM_BN = {"saline": "স্যালাইন", "kits": "কিট", "beds": "শয্যা", "crews": "দল"}


# --------------------------------------------------------------------------- formatting
def bn(x: Any) -> str:
    """Any number or text with its digits in Bangla: ``23`` -> ``২৩``."""
    return str(x).translate(_DIGITS)


def bn_date(d, year: bool = False) -> str:
    d = pd.Timestamp(d)
    return f"{bn(f'{d.day:02d}')} {MONTHS[d.month - 1]}" + (f" {bn(d.year)}" if year else "")


def bn_pct(x: float) -> str:
    return f"{bn(round(float(x) * 100))}%"


def ward_label_bn(ward_id: str) -> str:
    """'DNCC_Ward_12' -> 'DNCC ওয়ার্ড ১২'."""
    corp, _, rest = str(ward_id).partition("_")
    num = rest.rsplit("_", 1)[-1] if rest else ""
    return f"{corp} ওয়ার্ড {bn(num)}" if num.isdigit() else ward_label(str(ward_id))


def _short_ward_bn(ward_id: str, home: str | None) -> str:
    code = ward_code(ward_id)
    same = home and corporation_of(str(ward_id)) == home and "-" in code
    return code.split("-", 1)[1] if same else code


def _people(n: int) -> str:
    return f"{bn(n)} জন রোগী"


def _cases_bn(x: float, approx: str = "~") -> str:
    return "১ জনের কম রোগী" if x < 0.5 else f"{approx}{_people(int(round(x)))}"


def _tier(row: Mapping[str, Any]) -> str:
    t = str(_get(row, "tier", "Low"))
    return t if t in TIERS else "Low"


def _supplies_bn(row: Mapping[str, Any]) -> list[dict]:
    out = []
    for s in supply_lines(row):
        long, short = SUPPLY_BN.get(s["label"], (s["label"], s["short"]))
        out.append({**s, "long_bn": long, "short_bn": short})
    return out


def sms_parts(text: str) -> tuple[str, int, int]:
    """``(encoding, characters, parts)`` as an SMS gateway counts them.

    GSM-7 text: 160 in one SMS, 153 per part. Anything else (Bangla) goes as UCS-2:
    70 in one SMS, 67 per part.
    """
    septets = _gsm_exact(text)
    if septets >= 0:
        return "GSM-7", septets, 1 if septets <= SMS_LIMIT else math.ceil(septets / GSM_PART)
    n = len(text.encode("utf-16-le")) // 2
    return "Unicode", n, 1 if n <= UCS2_SINGLE else math.ceil(n / UCS2_PART)


def _gsm_exact(text: str) -> int:
    """GSM-7 septets, or -1 if any character needs Unicode."""
    total = 0
    for ch in text:
        if ch in _GSM_BASIC:
            total += 1
        elif ch in _GSM_EXT:
            total += 2
        else:
            return -1
    return total


# --------------------------------------------------------------------------- shared text
def actions_bn(row: Mapping[str, Any]) -> list[str]:
    """Plain-language actions in Bangla, most urgent first (mirrors ``dispatch.actions``)."""
    act, detail = ACTION_BN[_tier(row)]
    out = [f"{act}: {detail}"]
    for t, p in _transfers(row, "transfers_out"):
        out.append(f"{_people(p)}কে {ward_label_bn(t)}-এ স্থানান্তর করুন (সেখানে শয্যা নিশ্চিত)।")
    for f, p in _transfers(row, "transfers_in"):
        out.append(f"{ward_label_bn(f)} থেকে আসা রোগীদের জন্য {bn(p)}টি শয্যা প্রস্তুত রাখুন।")
    unplaced = _int(row, "net_deficit")
    if unplaced:
        out.append(f"শহরে {_people(unplaced)}র জন্য কোনো শয্যা নেই: সার্জ শয্যা চালু করুন বা সিটি স্বাস্থ্য দপ্তরকে জানান।")
    for s in _supplies_bn(row):
        if s["gap"]:
            ration = (f"; প্রাপ্ত {bn(s['allocated'])}টি আগে নিশ্চিত রোগীদের জন্য ব্যবহার করুন"
                      if s["allocated"] else "")
            out.append(f"আঞ্চলিক ভান্ডার থেকে আরও {bn(s['gap'])}টি {s['long_bn']} চেয়ে নিন{ration}।")
    got, need = _crews(row)
    if got is not None and need is not None and need > got:
        out.append(f"সিটি কর্পোরেশনের কাছে আরও {bn(need - got)}টি স্প্রে দল চান।")
    return out


def deficit_text_bn(row: Mapping[str, Any]) -> str:
    """'৮টি স্যালাইন ব্যাগ কম; আরও ১টি দল প্রয়োজন; ২ জন রোগীর শয্যা নেই', or ''."""
    parts = []
    short = [f"{bn(s['gap'])}টি {s['long_bn']}" for s in _supplies_bn(row) if s["gap"]]
    if short:
        parts.append(", ".join(short) + " কম")
    got, need = _crews(row)
    if got is not None and need is not None and need > got:
        parts.append(f"আরও {bn(need - got)}টি দল প্রয়োজন")
    unplaced = _int(row, "net_deficit")
    if unplaced:
        parts.append(f"{_people(unplaced)}র শয্যা নেই")
    return "; ".join(parts)


# --------------------------------------------------------------------------- SMS
def sms(row: Mapping[str, Any], sender: str = SENDER, limit: int = BN_SMS_LIMIT) -> str:
    """A Bangla SMS of at most ``limit`` Unicode characters (two SMS parts by default).

    Example: ``মশারি DNCC-W12: উচ্চ ঝুঁকি, ~১০ জন রোগী (২৩ জুনের সপ্তাহ)। স্যালাইন ৩২/৪০,
    কিট ৯/১২, শয্যা ৩/৩। ঘাটতি: স্যালাইন, কিট। দল: ২। -DGHS``
    """
    ward = str(_get(row, C.WARD_COL, "ward"))
    home = corporation_of(ward)
    tier = _tier(row)
    tname = TIER_BN[tier]
    week = target_week(row)
    cases = float(_get(row, "expected_cases", 0.0))
    n = bn(int(round(cases))) if cases >= 0.5 else "<১"
    supplies = _supplies_bn(row)
    deficits = [ITEM_BN.get(d, d) for d in deficit_items(row)]
    got, need = _crews(row)
    outs, ins = _transfers(row, "transfers_out"), _transfers(row, "transfers_in")
    unplaced = _int(row, "net_deficit")
    code = ward_code(ward)
    wk_long = f" (সপ্তাহ {bn_date(week)})" if week is not None else ""
    wk_short = f", {bn_date(week)}" if week is not None else ""

    parts: dict[str, list[str]] = {
        "head": [f"মশারি {code}: {tname} ঝুঁকি, {_cases_bn(cases)}{wk_long}।",
                 f"মশারি {code}: {tname}, ~{n} রোগী{wk_short}।",
                 f"{code}: {tname}, {n} রোগী{wk_short}।"],
        "supplies": [
            " " + ", ".join(f"{s['short_bn']} {bn(s['allocated'])}/{bn(s['needed'])}" for s in supplies) + "।"
            if supplies else "",
            " " + ",".join(f"{s['short_bn']}{bn(s['allocated'])}/{bn(s['needed'])}" for s in supplies) + "।"
            if supplies else "",
        ],
        "deficit": [f" ঘাটতি: {', '.join(deficits)}।" if deficits else " সম্পূর্ণ সরবরাহ।",
                    f" ঘাটতি {','.join(deficits)}।" if deficits else " ঠিক আছে।",
                    f" ঘাটতি {','.join(deficits)}।" if deficits else ""],
        "crews": [f" দল: {bn(got)}{f'/{bn(need)}' if need and need > got else ''}।" if got is not None else "",
                  f" দল {bn(got)}।" if got is not None else "", ""],
        "beds": [
            " " + " ".join([*(f"{bn(p)} রোগী {_short_ward_bn(t, home)}-এ পাঠান।" for t, p in outs),
                            *([f"{bn(sum(p for _, p in ins))} রোগী আসবে।"] if ins else []),
                            *([f"{bn(unplaced)} রোগীর শয্যা নেই।"] if unplaced else [])]).rstrip()
            if (outs or ins or unplaced) else "",
            " " + " ".join([*(f"{bn(p)} রোগী→{_short_ward_bn(t, home)}।" for t, p in outs),
                            *([f"{bn(sum(p for _, p in ins))} আসবে।"] if ins else []),
                            *([f"{bn(unplaced)} শয্যাহীন।"] if unplaced else [])]).rstrip()
            if (outs or ins or unplaced) else "",
            (f" {bn(sum(p for _, p in outs))} রোগী স্থানান্তর।" if outs else "")
            + (f" {bn(sum(p for _, p in ins))} রোগী আসবে।" if ins else "")
            + (f" {bn(unplaced)} শয্যাহীন।" if unplaced else ""),
            (f" {bn(unplaced)} শয্যাহীন।" if unplaced else ""),
            "",
        ],
        "action": [f" {ACTION_BN[tier][0]}।", ""],
        "sign": [f" -{sender}" if sender else "", ""],
    }
    order = ["head", "supplies", "deficit", "crews", "beds", "action", "sign"]
    # Bangla words are longer, so compact the wording before dropping any instruction:
    # patient transfers survive longer here than in the English SMS.
    shrink = ["action", "head", "sign", "supplies", "crews", "deficit", "beds", "head", "beds", "crews",
              "deficit", "beds", "beds"]
    level = dict.fromkeys(order, 0)

    def render() -> str:
        return "".join(parts[k][min(level[k], len(parts[k]) - 1)] for k in order).strip()

    def size(t: str) -> int:
        return sms_parts(t)[1]

    text = render()
    for k in shrink:
        if size(text) <= limit:
            break
        if level[k] < len(parts[k]) - 1:
            level[k] += 1
            text = render()
    if size(text) > limit:  # last resort; unreachable for real ward ids
        text = text[: limit - 1].rstrip() + "…"
    return text


# --------------------------------------------------------------------------- WhatsApp
def whatsapp(row: Mapping[str, Any], sender: str = SENDER) -> str:
    """The WhatsApp message in Bangla: risk, supplies, crews, overflow, actions."""
    ward = str(_get(row, C.WARD_COL, "ward"))
    tier = _tier(row)
    corp = corporation_of(ward)
    week = target_week(row)
    cases = float(_get(row, "expected_cases", 0.0))
    lo, hi = _get(row, "lower_80"), _get(row, "upper_80")
    p_crit = _get(row, "p_crit")

    lines = [f"{TIER_EMOJI.get(tier, '')} *মশারি নির্দেশনা: {ward_label_bn(ward)}*".strip()]
    sub = CITY_BN.get(corp, str(_get(row, C.CITY_COL, "")))
    if week is not None:
        sub += f" · সপ্তাহ শুরু {bn_date(week, year=True)}"
    lines += [f"_{sub}_", ""]

    risk = f"*ঝুঁকি:* {TIER_BN[tier]}, প্রত্যাশিত {_cases_bn(cases)}"
    if lo is not None and hi is not None:
        risk += f" (সম্ভাব্য {bn(f'{float(lo):.0f}')} থেকে {bn(f'{float(hi):.0f}')})"
    lines.append(risk)
    if p_crit is not None and float(p_crit) >= 0.05:
        lines.append(f"*প্রাদুর্ভাবের সম্ভাবনা:* {bn_pct(p_crit)}")

    supplies = _supplies_bn(row)
    if supplies:
        lines += ["", "*সরবরাহ* (বরাদ্দ / প্রয়োজন)"]
        for s in supplies:
            flag = f"  ⚠️ {bn(s['gap'])}টি কম" if s["gap"] else "  ✅"
            lines.append(f"• {s['long_bn']}: {bn(s['allocated'])} / {bn(s['needed'])}{flag}")

    got, need = _crews(row)
    if got is not None:
        crew = f"*স্প্রে দল:* {bn(got)}টি নিযুক্ত"
        if need is not None and need > got:
            crew += f" (প্রয়োজন {bn(need)}) ⚠️"
        lines += ["", crew]

    outs, ins, unplaced = _transfers(row, "transfers_out"), _transfers(row, "transfers_in"), _int(row, "net_deficit")
    if outs or ins or unplaced:
        lines += ["", "*হাসপাতালের অতিরিক্ত রোগী:*"]
        lines += [f"• {_people(p)}কে {ward_label_bn(t)}-এ পাঠান" for t, p in outs]
        lines += [f"• {ward_label_bn(f)} থেকে {_people(p)} গ্রহণ করুন" for f, p in ins]
        if unplaced:
            lines.append(f"• ⚠️ শহরে {_people(unplaced)}র জন্য শয্যা নেই")

    gap = deficit_text_bn(row)
    lines.append("")
    if gap:
        lines += [f"⚠️ *ঘাটতি:* {gap}", ""]
    lines.append("*এখনই করণীয়:*")
    lines += [f"{bn(i)}. {a}" for i, a in enumerate(actions_bn(row)[:4], 1)]
    if sender:
        lines += ["", f"— মশারি / {sender}"]
    return "\n".join(lines)


# --------------------------------------------------------------------------- commissioner brief
_BN_CSS = ('body { font-family:"Noto Sans Bengali","Hind Siliguri","Nirmala UI","Vrinda","Shonar Bangla",'
           '-apple-system,"Segoe UI",Arial,sans-serif; line-height:1.6; }'
           " header .k, .kpi .l, th, h2 { text-transform:none; letter-spacing:0; }")


def _gap_cell(gap: int) -> str:
    return f'<span class="gap">-{bn(format(gap, ","))}</span>' if gap else '<span class="okc">নেই</span>'


def _brief_page(row: Mapping[str, Any], sender: str) -> str:
    e = html.escape
    ward = str(_get(row, C.WARD_COL, "ward"))
    tier = _tier(row)
    t = TIERS[tier]
    corp = corporation_of(ward)
    week = target_week(row)
    issued = _get(row, C.DATE_COL)
    cases = float(_get(row, "expected_cases", 0.0))
    lo, hi, p_crit = _get(row, "lower_80"), _get(row, "upper_80"), _get(row, "p_crit")
    rank = _get(row, "priority_rank")
    got, need = _crews(row)

    kpis = [
        ("প্রত্যাশিত রোগী", bn(f"{cases:.0f}") if cases >= 0.5 else "&lt;১",
         f"সম্ভাব্য {bn(f'{float(lo):.0f}')} থেকে {bn(f'{float(hi):.0f}')}" if lo is not None and hi is not None else ""),
        ("প্রাদুর্ভাবের সম্ভাবনা", bn_pct(p_crit) if p_crit is not None else "—", "সংকটজনক স্তরে পৌঁছানোর সম্ভাবনা"),
        ("স্প্রে দল", bn(got) if got is not None else "—",
         (f"প্রয়োজন {bn(need)}" if need is not None and need > got else "নিযুক্ত") if got is not None else ""),
        ("অগ্রাধিকার", f"#{bn(int(rank))}" if rank is not None else "—", "এই সপ্তাহে অঞ্চলে"),
    ]
    kpi_html = "".join(f'<div class="kpi"><div class="l">{e(l)}</div><div class="v">{v}</div>'
                       f'<div class="s">{e(s)}</div></div>' for l, v, s in kpis)

    supplies = _supplies_bn(row)
    def supply_row(s: dict) -> str:
        filled = s["allocated"] / s["needed"] if s["needed"] else 1
        return (f"<tr><td>{e(s['long_bn'])}</td><td class=n>{bn(format(s['needed'], ','))}</td>"
                f"<td class=n>{bn(format(s['allocated'], ','))}</td><td class=n>{_gap_cell(s['gap'])}</td>"
                f"<td class=n>{bn_pct(filled)}</td></tr>")

    rows_html = "".join(supply_row(s) for s in supplies)
    supply_html = (
        '<table><thead><tr><th>সরবরাহ</th><th class=n>প্রয়োজন</th><th class=n>বরাদ্দ</th>'
        f'<th class=n>ঘাটতি</th><th class=n>পূরণ</th></tr></thead><tbody>{rows_html}</tbody></table>'
        if supplies else "<p>সরবরাহের তথ্য নেই।</p>")

    gap = deficit_text_bn(row)
    status = (f'<div class="alert"><b>ঘাটতি:</b> {e(gap)}।</div>' if gap else
              '<div class="fine">পরিকল্পিত রোগীর জন্য <b>সম্পূর্ণ সরবরাহ</b> আছে।</div>')

    outs, ins, unplaced = _transfers(row, "transfers_out"), _transfers(row, "transfers_in"), _int(row, "net_deficit")
    cap = _get(row, "bed_capacity")
    beds = []
    if cap is not None:
        beds.append(f"<li>স্বাভাবিক শয্যা সক্ষমতা: <b>{bn(int(cap))}</b>; এই সপ্তাহে প্রয়োজন: "
                    f"<b>{bn(_int(row, 'hospital_beds_required'))}</b>।</li>")
    beds += [f"<li><b>{_people(p)}</b>কে {e(ward_label_bn(w))}-এ পাঠান।</li>" for w, p in outs]
    beds += [f"<li>{e(ward_label_bn(w))} থেকে <b>{_people(p)}</b> গ্রহণ করুন।</li>" for w, p in ins]
    if unplaced:
        beds.append(f'<li class="gap">শহরের কোথাও {_people(unplaced)}র জন্য শয্যা নেই।</li>')
    if not (outs or ins or unplaced):
        beds.append("<li>কোনো স্থানান্তর লাগবে না: ওয়ার্ডের নিজস্ব শয্যাই পূর্বাভাসের চাপ সামলাতে পারবে।</li>")
    beds_html = f'<ul class="plain">{"".join(beds)}</ul>'

    acts = "".join(f"<li>{e(a)}</li>" for a in actions_bn(row))
    when = f"সপ্তাহ শুরু {bn_date(week, year=True)}" if week is not None else ""
    issued_txt = f"পূর্বাভাস প্রকাশ {bn_date(issued, year=True)}" if issued is not None else ""
    city = CITY_BN.get(corp, str(_get(row, C.CITY_COL, "")))
    ink = "#fff" if tier in ("High", "Critical") else "#1d2433"

    return f"""<section class="page" style="--tier:{t.color};--tier-ink:{ink}">
<header><div><div class="k">কমিশনার ব্রিফ · ডেঙ্গু মোকাবিলা</div><h1>{e(ward_label_bn(ward))}</h1>
<div class="sub">{e(city)} · {e(when)}</div></div>
<span class="tier">{e(TIER_BN[tier])} ঝুঁকি</span></header>
<div class="kpis">{kpi_html}</div>
<h2>সরবরাহ</h2>{supply_html}{status}
<h2>হাসপাতাল শয্যা ও অতিরিক্ত রোগী</h2>{beds_html}
<h2>করণীয়</h2><ol>{acts}</ol>
<div class="sig"><div>ওয়ার্ড স্বাস্থ্য কর্মকর্তা</div><div>সিটি কর্পোরেশন কমিশনার</div></div>
<footer><span>মশারি আগাম সতর্কতা · {e(issued_txt)}</span><span>{e(sender)}-এর জন্য অফলাইনে প্রস্তুত। পূর্বাভাস একটি প্রাক্কলন; ওয়ার্ড নজরদারির মাধ্যমে নিশ্চিত করুন।</span></footer>
</section>"""


def briefs_html(rows: Iterable[Mapping[str, Any]], sender: str = SENDER, title: str | None = None) -> str:
    """One printable Bangla HTML document, a page per ward, with a Print / Save as PDF button."""
    rows = list(rows)
    pages = "".join(_brief_page(r, sender) for r in rows)
    n = len(rows)
    label = title or (ward_label_bn(str(_get(rows[0], C.WARD_COL, ""))) if n == 1 else f"{bn(n)}টি ওয়ার্ড")
    return (
        '<!doctype html><html lang="bn"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>মশারি ব্রিফ: {html.escape(label)}</title><style>{_BRIEF_CSS}{_BN_CSS}</style></head><body>"
        f'<div class="bar"><b>কমিশনার ব্রিফ · {html.escape(label)}</b>'
        '<button type="button" onclick="window.print()">প্রিন্ট / PDF হিসেবে সংরক্ষণ</button></div>'
        f"{pages}</body></html>"
    )


def brief_html(row: Mapping[str, Any], sender: str = SENDER) -> str:
    """A printable one-page Bangla commissioner brief for one ward."""
    return briefs_html([row], sender)
