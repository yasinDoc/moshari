"""exports/ generator (scripts/export_dispatch.py) and the PDF brief (moshari.dispatch_pdf)."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from moshari import config as C
from moshari import dispatch as D
from moshari import dispatch_pdf

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("export_dispatch", ROOT / "scripts" / "export_dispatch.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

EMPTY_WEEK = "2016-02-29"  # no High or Critical ward at the default settings


def files(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def pdf_pages(data: bytes) -> list[str]:
    """Text drawn on each page, in page order (reportlab writes pages in order, uncompressed)."""
    streams = re.findall(rb"(?s)stream\r?\n(.*?)endstream", data)
    pages = [s for s in streams if b" Tj" in s or b"BT" in s]
    out = []
    for s in pages:
        strings = re.findall(rb"\(((?:[^()\\]|\\.)*)\)\s*Tj", s)
        text = " ".join(re.sub(rb"\\(.)", rb"\1", t).decode("latin-1") for t in strings)
        out.append(re.sub(r"\s+", "", text))
    return out


def page_count(data: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))


@pytest.fixture(scope="module")
def demo(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("exports")
    assert E.main(["--out", str(out)]) == 0
    return out


@pytest.fixture(scope="module")
def demo_rows() -> list[dict]:
    svc = E.load_service()
    return E.build_rows(svc, pd.Timestamp(svc.default_issue_date()), 3, 0.70, 40, "high")


def make_row(**over) -> dict:
    row = {
        "ward_id": "DNCC_Ward_12", "city": "Dhaka", "date": pd.Timestamp("2025-06-02"),
        "target_date": pd.Timestamp("2025-06-23"), "expected_cases": 10.2, "lower_80": 6.0, "upper_80": 15.0,
        "tier": "Critical", "tier_idx": 3, "p_crit": 0.42,
        "saline_bags_needed": 40, "saline_bags_allocated": 32,
        "diagnostic_kits_needed": 12, "diagnostic_kits_allocated": 9,
        "hospital_beds_required": 9, "hospital_beds_allocated": 9,
        "crews_needed": 3, "crews_assigned": 2, "priority_rank": 1,
        "transfers_out": [("DNCC_Ward_03", 2)], "transfers_in": [("DNCC_Ward_07", 1)],
        "bed_capacity": 4, "net_deficit": 3,
    }
    row.update(over)
    return row


def test_demo_week_layout(demo, demo_rows):
    wards = [str(r[C.WARD_COL]) for r in demo_rows]
    assert len(wards) == 26
    got = files(demo)
    for w in wards:
        assert {f"sms/{w}.txt", f"whatsapp/{w}.txt", f"briefs/{w}.html"} <= set(got)
    assert {"briefs/all_briefs.html", "briefs/all_briefs.pdf", f"briefs/{wards[0]}.pdf", "README.md"} <= set(got)
    assert len([k for k in got if k.endswith(".pdf")]) == 2  # --pdf top: the top ward + all_briefs


def test_files_are_the_dispatch_templates(demo, demo_rows):
    for r in demo_rows:
        w = r[C.WARD_COL]
        sms = (demo / "sms" / f"{w}.txt").read_text("utf-8")
        assert sms == D.sms(r) + "\n"
        assert D.gsm_length(sms.rstrip("\n")) <= D.SMS_LIMIT
        assert (demo / "whatsapp" / f"{w}.txt").read_text("utf-8") == D.whatsapp(r) + "\n"
        assert (demo / "briefs" / f"{w}.html").read_text("utf-8") == D.brief_html(r)
    assert (demo / "briefs" / "all_briefs.html").read_text("utf-8") == D.briefs_html(demo_rows)
    readme = (demo / "README.md").read_text("utf-8")
    assert "2025-06-23" in readme and "python scripts/export_dispatch.py" in readme
    assert all(str(r[C.WARD_COL]) in readme for r in demo_rows)


def test_rerun_is_identical_and_removes_stale_files(demo, tmp_path):
    out = tmp_path / "exports"
    assert E.main(["--out", str(out)]) == 0
    (out / "sms" / "OLD_Ward_99.txt").write_text("stale")
    (out / "briefs" / "OLD_Ward_99.pdf").write_bytes(b"%PDF-stale")
    assert E.main(["--out", str(out)]) == 0
    assert files(out) == files(demo)  # byte-identical, PDFs included; stale wards gone
    assert not list(tmp_path.glob(".export-*"))  # no temporary folder left behind


def test_empty_selection_writes_nothing(tmp_path, capsys):
    out = tmp_path / "exports"
    assert E.main(["--out", str(out), "--issue", EMPTY_WEEK]) == 1
    assert not out.exists()
    assert "No ward to export" in capsys.readouterr().err


@pytest.mark.parametrize("args", [["--issue", "1999-01-01"], ["--issue", "not-a-date"], ["--horizon", "9"],
                                  ["--stock", "10"], ["--stock", "120"], ["--crews", "-1"]])
def test_invalid_settings_exit_2(tmp_path, args):
    out = tmp_path / "exports"
    assert E.main(["--out", str(out), "--pdf", "none", *args]) == 2
    assert not out.exists()


def test_failed_write_leaves_existing_exports_untouched(demo, tmp_path, monkeypatch):
    out = tmp_path / "exports"
    assert E.main(["--out", str(out)]) == 0
    before = files(out)
    real_write, calls = E._write, {"n": 0}

    def flaky(path, text):
        calls["n"] += 1
        if calls["n"] == 30:
            raise OSError("disk full")
        real_write(path, text)

    monkeypatch.setattr(E, "_write", flaky)
    assert E.main(["--out", str(out), "--select", "all"]) == 1
    assert files(out) == before
    assert not list(tmp_path.glob(".export-*"))


def _hide_reportlab(monkeypatch):
    for name in [m for m in sys.modules if m == "reportlab" or m.startswith("reportlab.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "reportlab", None)  # makes `import reportlab...` raise ImportError


def test_missing_reportlab_warns_or_fails_with_require_pdf(tmp_path, monkeypatch, capsys):
    _hide_reportlab(monkeypatch)
    out = tmp_path / "exports"
    assert E.main(["--out", str(out), "--require-pdf"]) == 1
    assert not out.exists()
    assert E.main(["--out", str(out)]) == 0
    assert "pip install reportlab" in capsys.readouterr().err
    assert len(list((out / "sms").glob("*.txt"))) == 26
    assert not list(out.rglob("*.pdf"))
    assert "skipped because reportlab was not installed" in (out / "README.md").read_text("utf-8")


def test_pdf_has_one_page_per_ward_with_each_wards_brief(tmp_path):
    rows = [make_row(), make_row(ward_id="DSCC_Ward_05", city="Dhaka", tier="Medium", tier_idx=1,
                                 transfers_out=[], transfers_in=[], net_deficit=0, priority_rank=2)]
    pdf = dispatch_pdf.write_brief_pdf(rows, tmp_path / "b.pdf").read_bytes()
    assert pdf.startswith(b"%PDF-") and page_count(pdf) == 2
    first, second = pdf_pages(pdf)
    for text in ["DNCC Ward 12", "Critical risk", "Week of 23 June 2025", "Supplies", "Saline bags",
                 "Deficit:", "Send 2 patients to DNCC Ward 03.", "Receive 1 patient from DNCC Ward 07.",
                 "3 patients without a bed anywhere in the city.", "Ward health officer"]:
        assert re.sub(r"\s+", "", text) in first, text
    for a in D.actions(rows[0]):
        assert re.sub(r"\s+", "", a) in first
    assert "DSCCWard05" in second and "Notransfersneeded" in second and "DNCCWard12" not in second


def test_long_brief_still_fits_one_page(tmp_path):
    many = [(f"DNCC_Ward_{i:02d}", 1) for i in range(1, 25)]
    pdf = dispatch_pdf.write_brief_pdf([make_row(transfers_out=many)], tmp_path / "long.pdf").read_bytes()
    assert page_count(pdf) == 1


def test_pdf_is_deterministic_and_rejects_no_rows(tmp_path):
    a = dispatch_pdf.write_brief_pdf([make_row()], tmp_path / "a.pdf").read_bytes()
    b = dispatch_pdf.write_brief_pdf([make_row()], tmp_path / "b.pdf").read_bytes()
    assert a == b
    with pytest.raises(ValueError):
        dispatch_pdf.write_brief_pdf([], tmp_path / "none.pdf")


def test_dispatch_pdf_imports_without_reportlab():
    code = ("import sys; sys.path.insert(0, 'src'); sys.modules['reportlab'] = None; "
            "import moshari.dispatch_pdf as m; assert callable(m.write_brief_pdf); print('ok')")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "ok"
