"""English / Bangla text for the dashboard and the briefing (no Streamlit import).

The catalog ``locales/bn.json`` maps each English text to its Bangla version. The English
text is the key, so English output is exactly what the code wrote before; Bangla output is
the catalog's template with the same ``{placeholders}`` and Bangla digits in the numbers.

    t("{n} wards", "en", n=12)  -> "12 wards"
    t("{n} wards", "bn", n=12)  -> "১২টি ওয়ার্ড"

A text missing from the catalog falls back to English (never an exception, so a forgotten
string cannot crash a page) and is recorded in :data:`MISSING`.
"""

from __future__ import annotations

import json
import numbers
import re
import string
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from .data import ward_label

LANGS = {"en": "English", "bn": "বাংলা"}
CATALOG_PATH = Path(__file__).resolve().parent / "locales" / "bn.json"
MISSING: set[str] = set()

_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
MONTHS_BN = ("জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর",
             "অক্টোবর", "নভেম্বর", "ডিসেম্বর")
TIER_BN = {"Low": "নিম্ন", "Medium": "মাঝারি", "High": "উচ্চ", "Critical": "সংকটজনক"}
_WARD_LABEL = re.compile(r"^(DNCC|DSCC|CCC|GCC|NCC) Ward (\d+)$")
_BENGALI = re.compile(r"[\u0980-\u09FF]")
_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")
_NUMBER_ONLY = re.compile(r"^[\s\d.,%+\-−–:/()×~<>≥≤→]*$")


@lru_cache(maxsize=1)
def catalog() -> dict[str, str]:
    """The Bangla catalog. Shipped in the repo, so a missing or broken file fails loudly."""
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"Bangla catalog missing: {CATALOG_PATH}")
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{CATALOG_PATH} must hold a JSON object {{english: bangla}}")
    return data


def norm(lang: str | None) -> str:
    """A known language code; anything else (a bad link) falls back to English."""
    return lang if lang in LANGS else "en"


def digits(x: Any) -> str:
    """Any number or text with its digits in Bangla: ``2025-06-23`` -> ``২০২৫-০৬-২৩``."""
    return str(x).translate(_DIGITS)


def _is_number(v: Any) -> bool:
    return isinstance(v, numbers.Number) and not isinstance(v, bool)


def _format(template: str, kw: dict, bangla: bool) -> str:
    out = []
    for literal, field, spec, conv in string.Formatter().parse(template):
        out.append(literal)
        if field is None:
            continue
        value = kw[field]
        if conv == "r":
            value = repr(value)
        elif conv == "s":
            value = str(value)
        text = format(value, spec or "")
        out.append(digits(text) if bangla and (_is_number(value) or isinstance(value, pd.Timestamp)) else text)
    return "".join(out)


def t(text: str, lang: str = "en", **kw: Any) -> str:
    """``text`` in ``lang``. English returns ``text.format(**kw)`` (or ``text`` with no kw)."""
    if norm(lang) != "bn":
        return text.format(**kw) if kw else text
    template = catalog().get(text)
    if template is None:
        MISSING.add(text)
        template = text
    return _format(template, kw, True) if kw else template


def num(x: Any, spec: str = "", lang: str = "en") -> str:
    s = format(x, spec)
    return digits(s) if norm(lang) == "bn" else s


def week(d, lang: str = "en") -> str:
    """``23 Jun 2025`` / ``২৩ জুন ২০২৫``."""
    d = pd.Timestamp(d)
    if norm(lang) != "bn":
        return d.strftime("%d %b %Y")
    return f"{digits(f'{d.day:02d}')} {MONTHS_BN[d.month - 1]} {digits(d.year)}"


def short(d, lang: str = "en") -> str:
    """``23 Jun`` / ``২৩ জুন``."""
    d = pd.Timestamp(d)
    if norm(lang) != "bn":
        return d.strftime("%d %b")
    return f"{digits(f'{d.day:02d}')} {MONTHS_BN[d.month - 1]}"


def month(d, lang: str = "en") -> str:
    """``Jun`` / ``জুন``."""
    d = pd.Timestamp(d)
    return d.strftime("%b") if norm(lang) != "bn" else MONTHS_BN[d.month - 1]


def ward(ward_id: str, lang: str = "en") -> str:
    """``DNCC Ward 12`` / ``DNCC ওয়ার্ড ১২``."""
    label = ward_label(str(ward_id))
    return label if norm(lang) != "bn" else tr(label, "bn")


def tier(name: str, lang: str = "en") -> str:
    return name if norm(lang) != "bn" else TIER_BN.get(name, t(name, "bn"))


def tr(text: Any, lang: str = "en") -> str:
    """Translate a finished display value: a ward label, a number, or a catalog text."""
    s = str(text)
    if norm(lang) != "bn":
        return s
    if _BENGALI.search(s) or _IDENTIFIER.match(s):   # already Bangla, or a column name such as ward_id
        return s
    m = _WARD_LABEL.match(s)
    if m:
        return f"{m.group(1)} ওয়ার্ড {digits(m.group(2))}"
    if s in TIER_BN:
        return TIER_BN[s]
    if _NUMBER_ONLY.match(s):
        return digits(s)
    return t(s, "bn")


def date_fmt(d, fmt: str, lang: str = "en") -> str:
    """strftime with Bangla months and digits: supports %d %e %b %B %m %y %Y."""
    d = pd.Timestamp(d)
    if norm(lang) != "bn":
        return d.strftime(fmt)
    mapping = {"%d": f"{d.day:02d}", "%e": str(d.day), "%b": MONTHS_BN[d.month - 1],
               "%B": MONTHS_BN[d.month - 1], "%m": f"{d.month:02d}", "%y": f"{d.year % 100:02d}",
               "%Y": str(d.year)}
    out = re.sub(r"%[deBbmyY]", lambda m: mapping[m.group()], fmt)
    return digits(out)


def deficit_note_bn(r) -> str:
    """The allocation status of one ward (a :func:`moshari.allocation.allocate` row) in Bangla,
    by the same rule as its English ``deficit_note``."""
    names = (("saline_bags_needed", "saline_bags_allocated", "স্যালাইন ব্যাগ"),
             ("diagnostic_kits_needed", "diagnostic_kits_allocated", "টেস্ট কিট"),
             ("hospital_beds_required", "hospital_beds_allocated", "শয্যা"))
    short = [f"{digits(int(r[n] - r[a]))}টি {label}" for n, a, label in names if r[a] < r[n]]
    gap = int(r["crews_needed"] - r["crews_assigned"])
    parts = ([f"ঘাটতি: {', '.join(short)}"] if short else []) + (
        [f"আরও {digits(gap)}টি দল দরকার"] if gap > 0 else [])
    return "; ".join(parts) if parts else "পুরো সরবরাহ পাওয়া গেছে"
