"""Commissioner briefs as PDF (Phase 2, module 4), drawn with reportlab.

The HTML brief (:func:`moshari.dispatch.brief_html`) is what the app shows and prints.
This module draws the same brief, section by section and with the same wording, as a
real PDF file, so the ``exports/`` folder can hold printed samples without a browser:

    header (ward, city, week, risk tier) -> KPI row -> supplies table and deficit line
    -> hospital beds and overflow -> actions -> signature lines -> footer

Every value and sentence comes from the helpers in :mod:`moshari.dispatch`, so the PDF
and the HTML brief cannot drift apart. One A4 page per ward; long content is shrunk to
fit, never split onto a second page.

Output is deterministic (``invariant=1``: no timestamps or random ids), so rerunning the
export gives byte-identical files, and page streams are left uncompressed
(``pageCompression=0``) so the text can be checked by tests.

reportlab is imported only inside :func:`write_brief_pdf`: importing this module, and the
app, never needs it. Install it with ``pip install reportlab`` (it is in
``requirements-dev.txt``). Fonts are reportlab's built-in Helvetica, so nothing is
downloaded and it works offline.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from . import config as C
from . import dispatch as D
from .data import corporation_of, ward_label
from .risk import TIERS

# Same palette as the HTML brief's CSS (dispatch._BRIEF_CSS).
INK, MUTED, LINE, ACCENT, BAD, OK = "#1d2433", "#5d6678", "#d9dee8", "#2f6f8f", "#8F1D30", "#256E4A"
ALERT_BG, FINE_BG = "#fbeef0", "#eef7f1"

KICKER = "Commissioner brief · dengue response"
DISCLAIMER = "Forecasts are estimates; confirm with ward surveillance."


def _e(text: Any) -> str:
    """Escape text for a reportlab Paragraph (it reads a small XML-like markup)."""
    return html.escape(str(text), quote=False)


def _present(v: Any) -> bool:
    return v is not None and not (isinstance(v, float) and pd.isna(v))


def _kpis(row: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """(label, value, sub-line) for the four KPI boxes, as in dispatch._brief_page."""
    cases = float(D._get(row, "expected_cases", 0.0))
    lo, hi, p_crit = D._get(row, "lower_80"), D._get(row, "upper_80"), D._get(row, "p_crit")
    rank = D._get(row, "priority_rank")
    got, need = D._crews(row)
    return [
        ("Expected cases", f"{cases:.0f}" if cases >= 0.5 else "<1",
         f"likely {float(lo):.0f} to {float(hi):.0f}" if lo is not None and hi is not None else ""),
        ("Outbreak chance", f"{float(p_crit):.0%}" if p_crit is not None else "n/a", "chance of Critical level"),
        ("Spraying crews", f"{got}" if got is not None else "n/a",
         (f"needs {need}" if need is not None and need > got else "assigned") if got is not None else ""),
        ("Priority", f"#{int(rank)}" if rank is not None else "n/a", "in the region this week"),
    ]


def _bed_lines(row: Mapping[str, Any]) -> list[tuple[str, bool]]:
    """(markup, is_warning) bullet lines for 'Hospital beds and overflow'."""
    outs = D._transfers(row, "transfers_out")
    ins = D._transfers(row, "transfers_in")
    unplaced = D._int(row, "net_deficit")
    cap = D._get(row, "bed_capacity")
    lines: list[tuple[str, bool]] = []
    if _present(cap):
        lines.append((f"Normal bed capacity: <b>{int(cap)}</b>; required this week: "
                      f"<b>{D._int(row, 'hospital_beds_required')}</b>.", False))
    lines += [(f"Send <b>{D._plural(p, 'patient')}</b> to {_e(ward_label(w))}.", False) for w, p in outs]
    lines += [(f"Receive <b>{D._plural(p, 'patient')}</b> from {_e(ward_label(w))}.", False) for w, p in ins]
    if unplaced:
        lines.append((f"{D._plural(unplaced, 'patient')} without a bed anywhere in the city.", True))
    if not (outs or ins or unplaced):
        lines.append(("No transfers needed: the ward's own beds cover the forecast.", False))
    return lines


class _Styles:
    """Paragraph styles, built once per document (reportlab imported lazily)."""

    def __init__(self, scale: float = 1.0):
        from reportlab.lib.colors import HexColor
        from reportlab.lib.styles import ParagraphStyle

        def ps(name, size, lead=None, color=INK, font="Helvetica", **kw):
            return ParagraphStyle(name, fontName=font, fontSize=size * scale,
                                  leading=(lead or size * 1.3) * scale, textColor=HexColor(color), **kw)

        self.kicker = ps("kicker", 8, color=MUTED, font="Helvetica-Bold")
        self.title = ps("title", 20, 24, font="Helvetica-Bold")
        self.sub = ps("sub", 10, color=MUTED)
        self.tier = ps("tier", 11, font="Helvetica-Bold", alignment=1)
        self.h2 = ps("h2", 9.5, color=ACCENT, font="Helvetica-Bold", spaceBefore=10 * scale, spaceAfter=4 * scale)
        self.body = ps("body", 9.5, 12.5)
        self.small = ps("small", 8, 10, color=MUTED)
        self.kpi_l = ps("kpi_l", 7, 9, color=MUTED, font="Helvetica-Bold")
        self.kpi_v = ps("kpi_v", 16, 19, font="Helvetica-Bold")
        self.cell = ps("cell", 9, 11.5)
        self.cell_r = ps("cell_r", 9, 11.5, alignment=2)
        self.head = ps("head", 7.5, 9.5, color=MUTED, font="Helvetica-Bold")
        self.head_r = ps("head_r", 7.5, 9.5, color=MUTED, font="Helvetica-Bold", alignment=2)
        self.gap = ps("gap", 9, 11.5, color=BAD, font="Helvetica-Bold", alignment=2)
        self.okc = ps("okc", 9, 11.5, color=OK, font="Helvetica-Bold", alignment=2)


def _page(row: Mapping[str, Any], sender: str, width: float, st: _Styles) -> list:
    """The flowables for one ward's brief."""
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    P = Paragraph
    ward = str(D._get(row, C.WARD_COL, "ward"))
    tier = str(D._get(row, "tier", "Low"))
    tier_color = HexColor(TIERS.get(tier, TIERS["Low"]).color)
    corp = corporation_of(ward)
    city = C.CITY_CORPORATIONS.get(corp, str(D._get(row, C.CITY_COL, "")))
    week = D.target_week(row)
    when = f"Week of {week:%d %B %Y}" if week is not None else ""
    issued = D._get(row, C.DATE_COL)
    issued_txt = f"Forecast issued {pd.Timestamp(issued):%d %b %Y}" if issued is not None else ""
    out: list = []

    # Header: kicker, ward, city and week on the left; tier badge on the right.
    tier_style = st.tier.clone("tier_ink", textColor=white if tier in ("High", "Critical") else HexColor(INK))
    left = [P(_e(KICKER), st.kicker), P(_e(ward_label(ward)), st.title),
            P(f"{_e(city)} · {_e(when)}", st.sub)]
    badge = Table([[P(f"{_e(tier)} risk", tier_style)]], colWidths=[30 * mm])
    badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), tier_color), ("ROUNDEDCORNERS", [9, 9, 9, 9]),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    header = Table([[left, badge]], colWidths=[width - 32 * mm, 32 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 2.5, tier_color),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    out += [header, Spacer(1, 10)]

    # KPI row: four boxes.
    kpi_cells = [[P(_e(l), st.kpi_l), P(_e(v), st.kpi_v), P(_e(s), st.small)] for l, v, s in _kpis(row)]
    kpis = Table([kpi_cells], colWidths=[width / 4] * 4)
    kpis.setStyle(TableStyle([
        ("BOX", (0, 0), (0, 0), 0.6, HexColor(LINE)), ("BOX", (1, 0), (1, 0), 0.6, HexColor(LINE)),
        ("BOX", (2, 0), (2, 0), 0.6, HexColor(LINE)), ("BOX", (3, 0), (3, 0), 0.6, HexColor(LINE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    out.append(kpis)

    # Supplies table and the deficit / fully-supplied line.
    out.append(P("Supplies", st.h2))
    supplies = D.supply_lines(row)
    if supplies:
        data = [[P("Supply", st.head), P("Required", st.head_r), P("Allocated", st.head_r),
                 P("Gap", st.head_r), P("Filled", st.head_r)]]
        for s in supplies:
            filled = s["allocated"] / s["needed"] if s["needed"] else 1
            data.append([P(_e(s["label"]), st.cell), P(f"{s['needed']:,}", st.cell_r),
                         P(f"{s['allocated']:,}", st.cell_r),
                         P(f"-{s['gap']:,}", st.gap) if s["gap"] else P("none", st.okc),
                         P(f"{filled:.0%}", st.cell_r)])
        table = Table(data, colWidths=[width * 0.36] + [width * 0.16] * 4)
        table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.6, HexColor(LINE)),
                                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        out.append(table)
    else:
        out.append(P("No supply data.", st.body))
    gap = D.deficit_text(row)
    if gap:
        status, edge, bg = f"<b>Deficit:</b> {_e(gap)}.", BAD, ALERT_BG
    else:
        status, edge, bg = "<b>Fully supplied</b> for the planned caseload.", OK, FINE_BG
    box = Table([[P(status, st.body)]], colWidths=[width])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HexColor(bg)),
                             ("LINEBEFORE", (0, 0), (0, 0), 3, HexColor(edge)),
                             ("LEFTPADDING", (0, 0), (-1, -1), 9)]))
    out += [Spacer(1, 8), box]

    # Hospital beds and overflow.
    out.append(P("Hospital beds and overflow", st.h2))
    for text, warn in _bed_lines(row):
        style = st.body.clone("warn", textColor=HexColor(BAD), fontName="Helvetica-Bold") if warn else st.body
        out.append(P(text, style, bulletText="•"))

    # Actions, numbered.
    out.append(P("Actions", st.h2))
    for i, a in enumerate(D.actions(row), 1):
        out.append(P(_e(a), st.body, bulletText=f"{i}."))

    # Signature lines and footer.
    sig = Table([[P("Ward health officer", st.small), "", P("City corporation commissioner", st.small)]],
                colWidths=[width * 0.45, width * 0.1, width * 0.45])
    sig.setStyle(TableStyle([("LINEABOVE", (0, 0), (0, 0), 0.8, HexColor(INK)),
                             ("LINEABOVE", (2, 0), (2, 0), 0.8, HexColor(INK)),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    foot = Table([[P(f"Moshari early warning · {_e(issued_txt)}", st.small),
                   P(f"Prepared offline for {_e(sender)}. {DISCLAIMER}", st.small.clone("fr", alignment=2))]],
                 colWidths=[width * 0.4, width * 0.6])
    foot.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.6, HexColor(LINE)),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    out += [Spacer(1, 26), sig, Spacer(1, 14), foot]
    return out


def write_brief_pdf(rows: Iterable[Mapping[str, Any]], path: Path | str, sender: str = D.SENDER) -> Path:
    """Write the commissioner briefs for ``rows`` to ``path``: one A4 page per ward, in order.

    Raises ``ImportError`` when reportlab is not installed and ``ValueError`` for no rows.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepInFrame, PageBreak, SimpleDocTemplate

    rows = list(rows)
    if not rows:
        raise ValueError("no wards to write")
    path = Path(path)
    margin = 16 * mm
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=margin, rightMargin=margin,
                            topMargin=14 * mm, bottomMargin=12 * mm, invariant=1, pageCompression=0,
                            title="Moshari commissioner briefs", author="Moshari", creator="Moshari",
                            subject="Dengue response briefs")
    width, height = doc.width, doc.height
    st = _Styles()
    story: list = []
    for i, row in enumerate(rows):
        if i:
            story.append(PageBreak())
        # Shrink, never spill: keeps each ward on exactly one page.
        story.append(KeepInFrame(width, height - 2, _page(row, sender, width, st), mode="shrink"))
    doc.build(story)
    return path
