"""Weekly briefing PDF in Bangla: the bundled font, joined letters, the same content, one page.

English must stay the PDF it was before (``lang`` defaults to "en"); Bangla is drawn with the
bundled Noto Sans Bengali, shaped by uharfbuzz, with every text from the catalog and Bangla
digits. Shaped Bangla cannot be read back reliably from PDF bytes, so the texts are checked as
they are handed to reportlab (the story), and the bytes for page count, size and the font.
Weeks: 1 Jul 2024, 4 weeks ahead (transfers and wards out of beds); 29 Feb 2016 (quiet week).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd
import pytest

from moshari import briefing as B
from moshari import briefing_pdf as BP
from moshari import i18n
from moshari.data import load_dataset
from moshari.model import ForecastBundle
from moshari.service import ForecastService

TRANSFERS, QUIET = ("2024-07-01", 4), ("2016-02-29", 3)
BENGALI = re.compile(r"[ঀ-৿]")
# Names that stay in Latin letters in Bangla: ward codes, two messaging apps and PDF.
KEEP = re.compile(r"\b(?:DNCC|DSCC|CCC|GCC|NCC)\b|\bSMS\b|\bWhatsApp\b|\bPDF\b")


@pytest.fixture(scope="module")
def svc() -> ForecastService:
    return ForecastService(load_dataset(), ForecastBundle.load())


@pytest.fixture(scope="module")
def briefs(svc) -> dict:
    return {(w, lang): B.build(svc, pd.Timestamp(w[0]), w[1], lang=lang)
            for w in (TRANSFERS, QUIET) for lang in ("en", "bn")}


def _texts(brief, lang: str) -> list[str]:
    """Every text of the PDF, as the paragraphs given to reportlab, with the markup removed."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import Paragraph

    if lang == "bn":
        BP._register_bangla()
    out = []

    def walk(flow):
        if isinstance(flow, Paragraph):
            out.append(re.sub(r"<[^>]+>", "", flow.text))
        for row in getattr(flow, "_cellvalues", []):
            for cell in row:
                walk(cell)

    for f in BP._story(brief, A4[0] - 32 * 2.835, BP._styles(lang), lang):
        walk(f)
    return out


def _pages(data: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", data))


def test_english_is_the_default_and_draws_no_bangla_font(briefs):
    b = briefs[(TRANSFERS, "en")]
    data = BP.briefing_pdf(b)
    assert data == BP.briefing_pdf(b, lang="en") == BP.briefing_pdf(b, lang="xx")
    assert b"NotoSansBengali" not in data and b"Helvetica" in data


def test_bangla_pdf_is_one_a4_page_with_the_bangla_font_embedded(briefs):
    for w in (TRANSFERS, QUIET):
        data = BP.briefing_pdf(briefs[(w, "bn")], lang="bn")
        assert data.startswith(b"%PDF") and _pages(data) == 1
        assert re.search(rb"/MediaBox\s*\[\s*0\s+0\s+595\.27\d*\s+841\.88\d*\s*\]", data)
        assert b"NotoSansBengali" in data and b"NotoSansBengali-Bold" in data


def test_bangla_pdf_bytes_are_deterministic(briefs):
    b = briefs[(TRANSFERS, "bn")]
    first = hashlib.sha256(BP.briefing_pdf(b, lang="bn")).hexdigest()
    assert hashlib.sha256(BP.briefing_pdf(b, lang="bn")).hexdigest() == first


def test_every_bangla_style_uses_the_bundled_font_with_shaping():
    from reportlab.pdfbase import pdfmetrics

    BP._register_bangla()
    styles = BP._styles("bn")
    assert {s.fontName for s in styles.values()} == {BP.BN_FONT, BP.BN_BOLD}
    assert all(s.shaping == 1 for s in styles.values())
    for name in (BP.BN_FONT, BP.BN_BOLD):
        assert b"Bengali" in pdfmetrics.getFont(name).face.name
    assert {s.fontName for s in BP._styles("en").values()} == {"Helvetica", "Helvetica-Bold"}


def test_bangla_pdf_has_the_same_paragraphs_and_no_english_left(briefs):
    for w in (TRANSFERS, QUIET):
        en, bn = _texts(briefs[(w, "en")], "en"), _texts(briefs[(w, "bn")], "bn")
        assert len(bn) == len(en)
        for text in bn:
            rest = KEEP.sub(" ", text)
            assert not re.search(r"[A-Za-z0-9]", rest), text
        assert sum(bool(BENGALI.search(t)) for t in bn) == len(bn)


def test_bangla_pdf_text_comes_from_the_catalog(briefs):
    i18n.MISSING.clear()
    _texts(briefs[(TRANSFERS, "bn")], "bn")
    _texts(briefs[(QUIET, "bn")], "bn")
    pdf_missing = {m for m in i18n.MISSING if m not in i18n.TIER_BN}
    assert not pdf_missing


def test_bangla_pdf_carries_the_bangla_decision_and_bangla_dates(briefs):
    b = briefs[(TRANSFERS, "bn")]
    texts = _texts(b, "bn")
    assert len(b["decision"]) == len(briefs[(TRANSFERS, "en")]["decision"])
    for i, line in enumerate(b["decision"], 1):
        assert BENGALI.search(line)
        assert f"{i18n.digits(i)}. {line}" in texts
    assert texts[1] == "সাপ্তাহিক ব্রিফিং"
    assert texts[2].startswith("২৯ জুলাই ২০২৪ সপ্তাহ · পূর্বাভাস প্রকাশ ০১ জুলাই ২০২৪, ৪ সপ্তাহ")
    assert any(t.startswith("DNCC ওয়ার্ড ") or " থেকে " in t for t in texts)


def test_quiet_week_crew_line_is_translated(briefs):
    texts = _texts(briefs[(QUIET, "bn")], "bn")
    assert "কোনো ওয়ার্ড উচ্চ বা সংকটজনক ঝুঁকিতে নেই, তাই দলগুলো সংরক্ষিত থাকতে পারে।" in texts


def test_missing_uharfbuzz_is_a_clear_error(briefs, monkeypatch):
    real = BP.importlib.util.find_spec
    monkeypatch.setattr(BP.importlib.util, "find_spec", lambda name, *a: None if name == "uharfbuzz" else real(name, *a))
    with pytest.raises(RuntimeError, match="uharfbuzz"):
        BP.briefing_pdf(briefs[(QUIET, "bn")], lang="bn")
    assert BP.briefing_pdf(briefs[(QUIET, "en")]).startswith(b"%PDF")   # English needs no uharfbuzz


def test_missing_font_file_names_the_path(monkeypatch, tmp_path: Path):
    from reportlab.pdfbase import pdfmetrics

    monkeypatch.setattr(BP, "FONT_DIR", tmp_path)
    monkeypatch.setattr(pdfmetrics, "getRegisteredFontNames", lambda: [])
    with pytest.raises(FileNotFoundError, match="NotoSansBengali"):
        BP._register_bangla()


def test_bundled_font_and_licence_ship_with_the_package():
    for f in BP.BN_FILES.values():
        assert (BP.FONT_DIR / f).stat().st_size > 100_000
    assert "SIL OPEN FONT LICENSE" in (BP.FONT_DIR / "OFL.txt").read_text(encoding="utf-8").upper()
