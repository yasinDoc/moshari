"""The weekly briefing as a one-page A4 PDF, drawn with reportlab.

Input is the dict from :func:`moshari.briefing.build`; nothing is recomputed here, so the
PDF says exactly what the Weekly briefing page says. Layout, top to bottom:

    header (week, issue date, cities) -> decision box -> KPI row -> Risk (city table and
    top wards) -> Supplies -> Patient transfers -> Crew plan -> Notices -> sign-off -> footer

Long content is shrunk to fit, never split onto a second page. Output is deterministic
(``invariant=1``) and page streams are left uncompressed (``pageCompression=0``), like the
commissioner briefs in :mod:`moshari.dispatch_pdf`. reportlab is imported only inside
:func:`briefing_pdf`; fonts are the built-in Helvetica, so it works offline.
"""

from __future__ import annotations

import html
from io import BytesIO
from typing import Any, Mapping

from .data import ward_label

INK, MUTED, LINE, ACCENT, BAD, OK = "#1d2433", "#5d6678", "#d9dee8", "#2f6f8f", "#8F1D30", "#256E4A"
DECISION_BG, ALERT_BG, FINE_BG = "#eef4f7", "#fbeef0", "#eef7f1"
TIER_INK = {"Low": "#256E4A", "Medium": "#8a6500", "High": "#b45309", "Critical": "#8F1D30"}

MAX_TRANSFERS = 8
FOOTER = "Made offline by Moshari. Forecasts are estimates; confirm with ward surveillance."


def _e(text: Any) -> str:
    return html.escape(str(text), quote=False)


def _styles():
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle

    def ps(name, size, lead=None, color=INK, font="Helvetica", **kw):
        return ParagraphStyle(name, fontName=font, fontSize=size, leading=lead or size * 1.3,
                              textColor=HexColor(color), **kw)

    return {
        "kicker": ps("kicker", 8, color=MUTED, font="Helvetica-Bold"),
        "title": ps("title", 22, 26, font="Helvetica-Bold"),
        "sub": ps("sub", 9.5, color=MUTED),
        "dlabel": ps("dlabel", 8, color=ACCENT, font="Helvetica-Bold"),
        "decision": ps("decision", 10.5, 14.5),
        "h2": ps("h2", 9.5, color=ACCENT, font="Helvetica-Bold", spaceBefore=9, spaceAfter=3),
        "body": ps("body", 9, 12),
        "small": ps("small", 7.5, 9.5, color=MUTED),
        "kpi_l": ps("kpi_l", 7, 9, color=MUTED, font="Helvetica-Bold"),
        "kpi_v": ps("kpi_v", 16, 19, font="Helvetica-Bold"),
        "kpi_bad": ps("kpi_bad", 16, 19, color=BAD, font="Helvetica-Bold"),
        "cell": ps("cell", 8.5, 11),
        "cell_r": ps("cell_r", 8.5, 11, alignment=2),
        "head": ps("head", 7, 9, color=MUTED, font="Helvetica-Bold"),
        "head_r": ps("head_r", 7, 9, color=MUTED, font="Helvetica-Bold", alignment=2),
        "warn": ps("warn", 9, 12, color=BAD, font="Helvetica-Bold"),
        "fine": ps("fine", 9, 12, color=OK, font="Helvetica-Bold"),
    }


def _table(rows: list[list], widths: list[float], header: bool = True):
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import Table, TableStyle

    t = Table(rows, colWidths=widths)
    style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
             ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
             ("LINEBELOW", (0, 1 if header else 0), (-1, -1), 0.4, HexColor(LINE))]
    if header:
        style.append(("LINEBELOW", (0, 0), (-1, 0), 0.8, HexColor(MUTED)))
    t.setStyle(TableStyle(style))
    return t


def _story(b: Mapping[str, Any], width: float, s: dict) -> list:
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import Paragraph as P
    from reportlab.platypus import Spacer, Table, TableStyle

    out: list = []
    week = b["target_week"]
    cities = b.get("cities") or []
    where = "All five city corporations" if len(cities) >= 5 else ", ".join(cities)
    out += [P("Dengue response · city health officer", s["kicker"]),
            P("Weekly briefing", s["title"]),
            P(_e(f"Week of {week:%d %B %Y} · forecast issued {b['issue_date']:%d %b %Y}, "
                 f"{b['horizon']} weeks ahead · {where}"), s["sub"]),
            P(_e(f"Scenario: {b['stock_pct']:.0%} of regional stock, {b['crews']} spraying crews, "
                 f"+{b['surge_pct']:.0f}% surge beds"), s["sub"]),
            Spacer(1, 8)]

    # Decision box: the four sentences, numbered.
    dec = [[P("DECISION", s["dlabel"])]] + [[P(_e(f"{i}. {line}"), s["decision"])]
                                          for i, line in enumerate(b["decision"], 1)]
    box = Table(dec, colWidths=[width])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HexColor(DECISION_BG)),
                             ("LINEBEFORE", (0, 0), (0, -1), 3, HexColor(ACCENT)),
                             ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                             ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                             ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, -1), (-1, -1), 8)]))
    out += [box, Spacer(1, 8)]

    # KPI row.
    short = b["deficit_wards"]
    kpis = [("HIGH-RISK WARDS", f"{b['high_wards']} / {b['wards']}", f"{b['critical_wards']} critical",
             b["high_wards"] > 0),
            ("WARDS SHORT OF SUPPLIES", f"{short}", "saline, test kits or beds", short > 0),
            ("PATIENTS WITHOUT A BED", f"{b['unplaced']}", f"after moving {b['patients_moved']}", b["unplaced"] > 0),
            ("SPRAYING CREWS", f"{b['crews_assigned']} / {b['crews_needed']}", "assigned / needed",
             b["crews_unmet"] > 0)]
    cells = [[P(_e(k), s["kpi_l"]), P(_e(v), s["kpi_bad"] if bad else s["kpi_v"]), P(_e(sub), s["small"])]
             for k, v, sub, bad in kpis]
    row = Table([cells], colWidths=[width / 4] * 4)
    row.setStyle(TableStyle([*[("BOX", (i, 0), (i, 0), 0.6, HexColor(LINE)) for i in range(4)],
                             ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7),
                             ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    out.append(row)

    # Risk: one row per city, then the five highest-priority wards.
    out.append(P("Risk", s["h2"]))
    head = ["City", "High wards", "Expected cases", "Wards short", "Crews", "Moved", "No bed"]
    rows = [[P(h, s["head"] if i == 0 else s["head_r"]) for i, h in enumerate(head)]]
    for c in b.get("by_city", []):
        rows.append([P(_e(c["city"]), s["cell"]), P(f"{c['high_wards']} / {c['wards']}", s["cell_r"]),
                     P(f"{c['expected_cases']:,.0f}", s["cell_r"]), P(str(c["short_wards"]), s["cell_r"]),
                     P(f"{c['crews_assigned']} / {c['crews_needed']}", s["cell_r"]),
                     P(str(c["patients_moved"]), s["cell_r"]), P(str(c["unplaced"]), s["cell_r"])])
    out.append(_table(rows, [width * f for f in (0.25, 0.13, 0.15, 0.12, 0.13, 0.11, 0.11)]))
    out.append(Spacer(1, 5))
    top = b.get("top_rows") or [{"ward_id": w, "tier": "", "expected_cases": 0.0, "status": ""} for w in b["top_wards"]]
    rows = [[P("Send teams first", s["head"]), P("Risk", s["head"]), P("Cases", s["head_r"]), P("Status", s["head"])]]
    for i, r in enumerate(top, 1):
        tier = r.get("tier", "")
        rows.append([P(_e(f"{i}. {ward_label(r['ward_id'])}"), s["cell"]),
                     P(f'<font color="{TIER_INK.get(tier, INK)}"><b>{_e(tier)}</b></font>', s["cell"]),
                     P(f"{r.get('expected_cases', 0.0):.1f}", s["cell_r"]), P(_e(r.get("status", "")), s["cell"])])
    out.append(_table(rows, [width * f for f in (0.27, 0.12, 0.11, 0.50)]))

    # Supplies.
    out.append(P("Supplies", s["h2"]))
    rows = [[P(h, s["head"] if i == 0 else s["head_r"]) for i, h in
             enumerate(["Item", "Needed", "Available", "Short", "Wards short", "Filled"])]]
    for label, r in (b.get("resources") or {}).items():
        gap = r["short"]
        name = {"beds": "Hospital beds (stock)"}.get(label, label.capitalize())
        rows.append([P(_e(name), s["cell"]), P(f"{r['needed']:,}", s["cell_r"]),
                     P(f"{r['allocated']:,}", s["cell_r"]),
                     P(f'<font color="{BAD if gap else OK}"><b>{gap:,}</b></font>', s["cell_r"]),
                     P(str(r.get("wards_short", 0)), s["cell_r"]), P(f"{r['fill']:.0%}", s["cell_r"])])
    if len(rows) > 1:
        out.append(_table(rows, [width * f for f in (0.30, 0.14, 0.14, 0.14, 0.14, 0.14)]))
    else:
        out.append(P(_e(f"{b['saline_short_bags']:,} saline bags and {b['kits_short']:,} test kits short."), s["body"]))

    # Patient transfers.
    out.append(P("Patient transfers", s["h2"]))
    transfers = list(b.get("transfers") or [])
    if transfers:
        for t in transfers[:MAX_TRANSFERS]:
            out.append(P(_e(f"{ward_label(t['from_ward'])} to {ward_label(t['to_ward'])}: {int(t['patients'])}"),
                         s["body"]))
        if len(transfers) > MAX_TRANSFERS:
            out.append(P(_e(f"and {len(transfers) - MAX_TRANSFERS} more transfers (see Hospital beds)."), s["small"]))
    else:
        out.append(P("None: every ward's own beds cover the forecast.", s["body"]))
    missing = b.get("out_of_beds") or []
    if missing:
        out.append(P(_e(f"Still out of beds: {', '.join(ward_label(w) for w in missing)}."), s["warn"]))

    # Crew plan and notices.
    out.append(P("Crew plan", s["h2"]))
    if b["crews_needed"] == 0:
        crew = "No ward is High or Critical, so crews can stay in reserve."
    else:
        crew = (f"{b['crews_assigned']} of {b['crews_needed']} crews needed are assigned, "
                f"across {b.get('crew_wards', 0)} wards, highest priority first.")
    out.append(P(_e(crew), s["body"]))
    out.append(P(_e(f"Cases prevented by this plan over weeks 2 to 4: {b['cases_prevented']:,.0f} "
                    "(vector control simulator)."), s["body"]))
    out.append(P("Notices", s["h2"]))
    out.append(P(_e(f"Notices ready to send: {b['notices_ready']} (SMS, WhatsApp and commissioner brief for "
                    "each High or Critical ward, on the Dispatch page)."), s["body"]))

    # Sign-off and footer.
    out.append(Spacer(1, 12))
    sign = Table([[P("Approved by", s["small"]), P("Signature", s["small"]), P("Date", s["small"])]],
                 colWidths=[width / 3] * 3, rowHeights=[22])
    sign.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.6, HexColor(MUTED)),
                              ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    out += [sign, Spacer(1, 4), P(_e(FOOTER), s["small"])]
    return out


def briefing_pdf(brief: Mapping[str, Any]) -> bytes:
    """One A4 page for ``brief`` (from :func:`moshari.briefing.build`), as PDF bytes.

    Raises ``ImportError`` when reportlab is not installed.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepInFrame, SimpleDocTemplate

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=13 * mm,
                            bottomMargin=11 * mm, invariant=1, pageCompression=0,
                            title="Moshari weekly briefing", author="Moshari", creator="Moshari",
                            subject="Weekly dengue briefing")
    # Shrink, never spill: the briefing is always exactly one page.
    doc.build([KeepInFrame(doc.width, doc.height - 2, _story(brief, doc.width, _styles()), mode="shrink")])
    return buf.getvalue()
