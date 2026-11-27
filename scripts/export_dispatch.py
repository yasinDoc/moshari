"""Write sample dispatch notices for the demo week into exports/ (Phase 2, task A2).

    python scripts/export_dispatch.py                 # demo week, High and Critical wards
    python scripts/export_dispatch.py --select all --pdf all --out /tmp/notices
    python scripts/export_dispatch.py --issue 2023-08-07 --stock 50 --crews 20

Runs the same chain as the Dispatch page, fully offline: forecast -> allocate() ->
route_overflow() -> dispatch_table(), then writes for every selected ward

    <out>/sms/<ward>.txt          one SMS of at most 160 GSM-7 characters
    <out>/whatsapp/<ward>.txt     the WhatsApp message
    <out>/briefs/<ward>.html      printable commissioner brief ("Print / Save as PDF")
    <out>/briefs/all_briefs.html  every brief in one printable file
    <out>/briefs/<ward>.pdf       PDF brief (reportlab), see --pdf
    <out>/briefs/all_briefs.pdf   every brief in one PDF, one page per ward
    <out>/README.md               what is in the folder and how it was made

The text comes from moshari.dispatch, so it is exactly what the app shows. Defaults match
the app: the default issue week, 3 weeks ahead, 70% stock, 40 crews. Output is
deterministic: rerunning with the same settings gives byte-identical files. Files are built
in a temporary folder and only then moved into place, so a failed run never leaves a
half-written folder, and wards that left the selection are removed.

PDFs need reportlab (`pip install reportlab`, it is in requirements-dev.txt). Without it
the text and HTML are still written and a warning is printed; --require-pdf makes that an
error instead.

Exit codes: 0 written, 1 nothing to write or writing failed, 2 invalid settings.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from moshari import allocation, routing  # noqa: E402
from moshari import config as C  # noqa: E402
from moshari import dispatch as D  # noqa: E402
from moshari.data import load_dataset, ward_label  # noqa: E402
from moshari.model import ForecastBundle  # noqa: E402
from moshari.risk import DEFAULT_ALERT_POLICY  # noqa: E402
from moshari.service import ForecastService  # noqa: E402

FOLDERS = ("sms", "whatsapp", "briefs")
SELECTIONS = {"high": "High and Critical wards", "deficit": "wards short of anything", "all": "all wards"}


class ExportError(Exception):
    """A problem the user can fix; carries the exit code."""

    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--issue", help="forecast issue week, YYYY-MM-DD (default: the app's default week)")
    p.add_argument("--horizon", type=int, default=3, help="weeks ahead (default 3)")
    p.add_argument("--stock", type=float, default=70.0, help="available stock, %% of demand, 30-100 (default 70)")
    p.add_argument("--crews", type=int, default=40, help="total spraying crews (default 40)")
    p.add_argument("--select", choices=sorted(SELECTIONS), default="high",
                   help="which wards: high (High and Critical, default), deficit, all")
    p.add_argument("--out", default=str(ROOT / "exports"), help="output folder (default: exports/)")
    p.add_argument("--pdf", choices=["top", "all", "none"], default="top",
                   help="PDF briefs: top (highest-priority ward + all_briefs.pdf, default), all, none")
    p.add_argument("--require-pdf", action="store_true", help="fail instead of warning when PDFs can't be made")
    return p.parse_args(argv)


def build_rows(svc: ForecastService, issue: pd.Timestamp, horizon: int, stock: float, crews: int,
               select: str) -> list[dict]:
    """Dispatch rows for these settings, in priority order (same chain as the Dispatch page)."""
    fc = svc.forecast_all(issue, horizon, None, DEFAULT_ALERT_POLICY)
    alloc = allocation.allocate(fc, svc.wards, stock, crews)
    routes = routing.route_overflow(alloc, routing.load_bed_capacity())
    table = D.dispatch_table(alloc, routes)
    return D.select_rows(table, select).to_dict("records")


def resolve_settings(args: argparse.Namespace, svc: ForecastService) -> pd.Timestamp:
    """Validate the settings; return the issue week."""
    dates = pd.DatetimeIndex(svc.issue_dates)
    if args.issue is None:
        issue = pd.Timestamp(svc.default_issue_date())
    else:
        try:
            issue = pd.Timestamp(args.issue)
        except ValueError as exc:
            raise ExportError(f"--issue {args.issue!r} is not a date (use YYYY-MM-DD)", 2) from exc
        if issue not in set(dates):
            nearest = dates[abs(dates - issue).argsort()[:3]].sort_values()
            raise ExportError(f"--issue {issue.date()} is not a forecast week. Nearest: "
                              + ", ".join(str(d.date()) for d in nearest)
                              + f" (data covers {dates.min().date()} to {dates.max().date()})", 2)
    horizons = sorted(svc.bundle.horizons)
    if args.horizon not in horizons:
        raise ExportError(f"--horizon must be one of {horizons}", 2)
    if not 30 <= args.stock <= 100:
        raise ExportError("--stock must be between 30 and 100 (percent of demand)", 2)
    if args.crews < 0:
        raise ExportError("--crews cannot be negative", 2)
    return issue


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def index_text(rows: list[dict], settings: dict, counts: dict, pdf_note: str) -> str:
    """exports/README.md: what is in the folder and how to make it again. No timestamps."""
    lines = [
        "# Dispatch notice samples",
        "",
        f"Generated by `scripts/export_dispatch.py` for the week of **{settings['target']}** "
        f"(forecast issued {settings['issue']}, {settings['horizon']} weeks ahead). "
        "Do not edit these files by hand; run the script again instead.",
        "",
        "```",
        settings["command"],
        "```",
        "",
        "| Setting | Value |",
        "|---|---|",
        f"| Target week | {settings['target']} |",
        f"| Issue week | {settings['issue']} |",
        f"| Horizon | {settings['horizon']} weeks |",
        f"| Available stock | {settings['stock']:g}% of demand |",
        f"| Spraying crews | {settings['crews']} |",
        f"| Wards | {SELECTIONS[settings['select']]}: {len(rows)} |",
        "",
        "| Folder | Files |",
        "|---|---|",
        f"| `sms/` | {counts['sms']} SMS, one per ward, at most 160 characters |",
        f"| `whatsapp/` | {counts['whatsapp']} WhatsApp messages |",
        f"| `briefs/` | {counts['html']} HTML briefs (open and use Print / Save as PDF), "
        f"{counts['pdf']} PDF briefs |",
        "",
        pdf_note,
        "",
        "| # | Ward | Code | Tier | Deficit |",
        "|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        w = str(r[C.WARD_COL])
        lines.append(f"| {i} | {ward_label(w)} | `{w}` | {r.get('tier', '')} | {D.deficit_text(r) or 'none'} |")
    return "\n".join(lines) + "\n"


def write_exports(rows: list[dict], out: Path, settings: dict, pdf_mode: str, require_pdf: bool) -> dict:
    """Write every file into a temporary folder next to ``out``, then move it into place."""
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".export-", dir=out.parent))
    try:
        for sub in FOLDERS:
            (tmp / sub).mkdir()
        for r in rows:
            w = str(r[C.WARD_COL])
            _write(tmp / "sms" / f"{w}.txt", D.sms(r) + "\n")
            _write(tmp / "whatsapp" / f"{w}.txt", D.whatsapp(r) + "\n")
            _write(tmp / "briefs" / f"{w}.html", D.brief_html(r))
        _write(tmp / "briefs" / "all_briefs.html", D.briefs_html(rows))

        pdfs: list[str] = []
        pdf_note = "PDF briefs were not requested (`--pdf none`)."
        if pdf_mode != "none":
            try:
                from moshari.dispatch_pdf import write_brief_pdf
                for r in (rows if pdf_mode == "all" else rows[:1]):
                    write_brief_pdf([r], tmp / "briefs" / f"{r[C.WARD_COL]}.pdf")
                write_brief_pdf(rows, tmp / "briefs" / "all_briefs.pdf")
                pdfs = sorted(p.name for p in (tmp / "briefs").glob("*.pdf"))
                pdf_note = ("PDF briefs (drawn with reportlab, one A4 page per ward): "
                            + ", ".join(f"`briefs/{n}`" for n in pdfs) + ".")
            except ImportError as exc:
                msg = f"PDF briefs skipped: reportlab is not installed ({exc}). Install it with: pip install reportlab"
                if require_pdf:
                    raise ExportError(msg, 1) from exc
                print(f"WARNING: {msg}", file=sys.stderr)
                pdf_note = "PDF briefs were skipped because reportlab was not installed."

        counts = {"sms": len(rows), "whatsapp": len(rows), "html": len(rows) + 1, "pdf": len(pdfs)}
        _write(tmp / "README.md", index_text(rows, settings, counts, pdf_note))

        # Everything is ready: replace the old folders in one quick step.
        out.mkdir(parents=True, exist_ok=True)
        for sub in FOLDERS:
            if (out / sub).exists():
                shutil.rmtree(out / sub)
            os.replace(tmp / sub, out / sub)
        os.replace(tmp / "README.md", out / "README.md")
        return {**counts, "pdfs": pdfs}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    try:
        svc = ForecastService(load_dataset(), ForecastBundle.load())
        issue = resolve_settings(args, svc)
        rows = build_rows(svc, issue, args.horizon, args.stock / 100, args.crews, args.select)
        if not rows:
            raise ExportError(f"No ward to export: no {SELECTIONS[args.select]} for issue week {issue.date()} "
                              "with these settings. Nothing was written.", 1)
        target = (issue + pd.Timedelta(weeks=args.horizon)).strftime("%Y-%m-%d")
        command = "python scripts/export_dispatch.py" + (f" --issue {issue.date()}" if args.issue else "") + "".join(
            f" --{k} {v:g}" if isinstance(v, float) else f" --{k} {v}"
            for k, v, d in (("horizon", args.horizon, 3), ("stock", args.stock, 70.0), ("crews", args.crews, 40),
                            ("select", args.select, "high"), ("pdf", args.pdf, "top")) if v != d)
        settings = {"issue": str(issue.date()), "target": target, "horizon": args.horizon, "stock": args.stock,
                    "crews": args.crews, "select": args.select, "command": command}
        out = Path(args.out)
        result = write_exports(rows, out, settings, args.pdf, args.require_pdf)
    except ExportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code
    except OSError as exc:
        print(f"ERROR: could not write the exports: {exc}. Nothing was changed.", file=sys.stderr)
        return 1

    print(f"Week of {target} (issued {issue.date()}, {args.horizon} weeks ahead, {args.stock:g}% stock, "
          f"{args.crews} crews): {len(rows)} {SELECTIONS[args.select]}")
    print(f"  {out}/sms/        {result['sms']} SMS")
    print(f"  {out}/whatsapp/   {result['whatsapp']} WhatsApp messages")
    print(f"  {out}/briefs/     {result['html']} HTML briefs, {result['pdf']} PDF briefs"
          + (f" ({', '.join(result['pdfs'])})" if result["pdfs"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
