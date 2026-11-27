"""Verifier for the a2-exports goal. Written before the run; the executor must not edit it.

    python .claude/goals/a2-exports-verify.py content   # criterion 1: exports/ and the script
    python .claude/goals/a2-exports-verify.py tests     # criterion 2: the new test file is not hollow
    python .claude/goals/a2-exports-verify.py git       # criterion 4: committed, prefixed, in scope

Prints one line per check ("ok ..." / "FAIL ...") and a final "PASS <mode>" or "FAIL <mode>".
Exit 0 only on PASS. Runs offline (MOSHARI_OFFLINE=1).
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "export_dispatch.py"
EXPORTS = ROOT / "exports"
BASE = "cc0f514"
PREFIX = "version-onsite-final:"
ALLOWED = ["scripts/export_dispatch.py", "src/moshari/dispatch_pdf.py", "tests/test_export_dispatch.py",
           "exports/*", "README.md", "requirements-dev.txt",
           ".claude/goals/*"]  # goal files live here; pins guard the design and this verifier
EMPTY_ISSUE = "2016-02-29"   # no High/Critical ward at the default settings (measured 2026-11-27)
BAD_ISSUE = "1999-01-01"

sys.path.insert(0, str(ROOT / "src"))
os.environ["MOSHARI_OFFLINE"] = "1"
for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

failures: list[str] = []


def check(ok: bool, what: str) -> bool:
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)
    return ok


def run_script(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, MOSHARI_OFFLINE="1", PYTHONIOENCODING="utf-8", **(env_extra or {}))
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)


def expected(issue=None, horizon=3, stock=0.70, crews=40, select="high"):
    """The dispatch rows, built independently of the script, from the pinned library."""
    import pandas as pd
    from moshari import allocation as A, config as C, dispatch as D, routing as R
    from moshari.data import load_dataset
    from moshari.model import ForecastBundle
    from moshari.risk import DEFAULT_ALERT_POLICY
    from moshari.service import ForecastService
    svc = expected.svc = getattr(expected, "svc", None) or ForecastService(load_dataset(), ForecastBundle.load())
    issue = svc.default_issue_date() if issue is None else pd.Timestamp(issue)
    fc = svc.forecast_all(issue, horizon, None, DEFAULT_ALERT_POLICY)
    alloc = A.allocate(fc, svc.wards, stock, crews)
    table = D.dispatch_table(alloc, R.route_overflow(alloc, R.load_bed_capacity()))
    rows = D.select_rows(table, select).to_dict("records")
    files = {}
    for r in rows:
        w = str(r[C.WARD_COL])
        files[f"sms/{w}.txt"] = D.sms(r) + "\n"
        files[f"whatsapp/{w}.txt"] = D.whatsapp(r) + "\n"
        files[f"briefs/{w}.html"] = D.brief_html(r)
    if rows:
        files["briefs/all_briefs.html"] = D.briefs_html(rows)
    return issue, rows, files


def text_files(folder: Path) -> dict[str, str]:
    out = {}
    for sub in ("sms", "whatsapp", "briefs"):
        for p in sorted((folder / sub).glob("*")):
            if p.suffix in (".txt", ".html"):
                out[f"{sub}/{p.name}"] = p.read_bytes().decode("utf-8")
    return out


def compare(got: dict[str, str], want: dict[str, str], label: str) -> None:
    missing, extra = sorted(set(want) - set(got)), sorted(set(got) - set(want))
    check(not missing and not extra,
          f"{label}: file set matches ({len(want)} expected; missing {missing[:3]}, extra {extra[:3]})")
    diff = sorted(k for k in set(want) & set(got) if got[k] != want[k])
    check(not diff, f"{label}: {len(set(want) & set(got)) - len(diff)} files byte-identical to "
                    f"moshari.dispatch output (differing: {diff[:3]})")


def _unescape(t: bytes) -> str:
    t = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 0xFF]), t)
    return re.sub(rb"\\(.)", rb"\1", t).decode("latin-1")


def pdf_pages(data: bytes) -> list[dict]:
    """Pages in /Kids order: {"text": drawn strings in content order, "box": MediaBox}.
    Expects reportlab output with pageCompression=0 (uncompressed content streams)."""
    objs = {int(m.group(1)): m.group(2) for m in re.finditer(rb"(?s)(\d+) 0 obj\b(.*?)endobj", data)}
    root = [o for o in objs.values() if re.search(rb"/Type\s*/Pages\b", o)]
    pages = []
    def walk(body: bytes) -> None:
        kids = re.search(rb"/Kids\s*\[([^\]]*)\]", body)
        for ref in re.findall(rb"(\d+) 0 R", kids.group(1) if kids else b""):
            o = objs.get(int(ref), b"")
            if re.search(rb"/Type\s*/Pages\b", o):
                walk(o)
            elif re.search(rb"/Type\s*/Page\b", o):
                c = re.search(rb"/Contents\s+(\d+) 0 R", o)
                stream = objs.get(int(c.group(1)), b"") if c else b""
                m = re.search(rb"(?s)stream\r?\n(.*)endstream", stream)
                raw = m.group(1) if m else b""
                strings = [_unescape(t) for t in re.findall(rb"\(((?:[^()\\]|\\.)*)\)\s*Tj", raw)]
                box = re.search(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", o)
                pages.append({"text": re.sub(r"\s+", " ", " ".join(strings)).strip(),
                              "box": tuple(float(x) for x in box.groups()) if box else None})
    if root:
        top = [o for o in root if not re.search(rb"/Parent\s", o)] or root
        walk(top[0])
    return pages


def brief_tokens(row) -> tuple[list[str], list[str]]:
    """What a PDF brief of this ward must show: (in the order of dispatch._brief_page, anywhere on
    the page). KPI and table cells may be laid out as a grid, so their order is free."""
    import pandas as pd
    from moshari import config as C, dispatch as D
    from moshari.data import corporation_of, ward_label
    ward = str(row["ward_id"])
    week = D.target_week(row)
    cases = float(row.get("expected_cases", 0.0))
    got, _need = D._crews(row)
    toks = ["Commissioner brief", ward_label(ward), f"Week of {week:%d %B %Y}", f"{row['tier']} risk", "Supplies"]
    cells = ["Expected cases", f"{cases:.0f}" if cases >= 0.5 else "<1",
             "Outbreak chance", f"{float(row['p_crit']):.0%}",
             "Spraying crews", str(got), "Priority", f"#{int(row['priority_rank'])}",
             "Required", "Allocated", "Gap", "Filled"]
    for sup in D.supply_lines(row):
        filled = sup["allocated"] / sup["needed"] if sup["needed"] else 1
        cells += [sup["label"], f"{sup['needed']:,}", f"{sup['allocated']:,}",
                  f"-{sup['gap']:,}" if sup["gap"] else "none", f"{filled:.0%}"]
    gap = D.deficit_text(row)
    toks += ([f"Deficit: {gap}."] if gap else ["Fully supplied for the planned caseload."])
    toks.append("Hospital beds and overflow")
    if row.get("bed_capacity") is not None and not pd.isna(row.get("bed_capacity")):
        toks += [f"Normal bed capacity: {int(row['bed_capacity'])}; required this week: "
                 f"{D._int(row, 'hospital_beds_required')}."]
    outs, ins, unplaced = D._transfers(row, "transfers_out"), D._transfers(row, "transfers_in"), D._int(row, "net_deficit")
    toks += [f"Send {D._plural(p, 'patient')} to {ward_label(w)}." for w, p in outs]
    toks += [f"Receive {D._plural(p, 'patient')} from {ward_label(w)}." for w, p in ins]
    if unplaced:
        toks.append(f"{D._plural(unplaced, 'patient')} without a bed anywhere in the city.")
    if not (outs or ins or unplaced):
        toks.append("No transfers needed")
    toks.append("Actions")
    toks += [re.sub(r"\s+", " ", a) for a in D.actions(row)]
    toks += ["Ward health officer", "City corporation commissioner", f"Prepared offline for {D.SENDER}"]
    return toks, cells


def page_problems(page: dict, row) -> list[str]:
    """Tokens missing from this page, checked in order (each after the previous one)."""
    squash = lambda x: re.sub(r"\s+", "", x)  # bold/regular runs split lines into several strings
    text, pos, miss = squash(page["text"]), 0, []
    ordered, cells = brief_tokens(row)
    miss += [c for c in cells if squash(c) not in text]
    for t in ordered:
        i = text.find(squash(t), pos)
        if i < 0:
            miss.append(t)
        else:
            pos = i + len(squash(t))
    box = page["box"]
    if not box or abs(box[2] - box[0] - 595.28) > 2 or abs(box[3] - box[1] - 841.89) > 2:
        miss.append(f"A4 page size (got {box})")
    return miss


def check_pdf(p: Path, prows: list, label: str) -> None:
    b = p.read_bytes()
    check(b[:5] == b"%PDF-" and b"%%EOF" in b[-1024:] and b"ReportLab PDF Library" in b,
          f"{label}: a reportlab PDF ({len(b)} bytes)")
    pages = pdf_pages(b)
    check(len(pages) == len(prows), f"{label}: {len(pages)} page(s), expected {len(prows)} (one per ward)")
    bad = []
    for i, (pg, r) in enumerate(zip(pages, prows)):
        m = page_problems(pg, r)
        if m:
            bad.append(f"page {i + 1} {r['ward_id']}: {m[:3]}")
    check(not bad, f"{label}: every page is that ward's full brief, in brief order (problems: {bad[:2]})")


def tests_file_checks() -> None:
    import ast
    tf = ROOT / "tests" / "test_export_dispatch.py"
    if not check(tf.is_file(), "tests/test_export_dispatch.py exists"):
        return
    src = tf.read_text("utf-8")
    tree = ast.parse(src)
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name.startswith("test_")]
    check(len({f.name for f in funcs}) >= 8, f"{len(funcs)} distinct test functions (>= 8, parametrize not counted)")
    check("export_dispatch" in src and "dispatch_pdf" in src and "transfers" in src,
          "tests exercise export_dispatch, dispatch_pdf and a ward with transfers")
    def calls(fn) -> int:
        return sum(isinstance(n, ast.Call) for n in ast.walk(fn))
    def asserts(fn) -> int:
        return sum(isinstance(n, ast.Assert) for n in ast.walk(fn)) + src.count("pytest.raises") * 0
    thin = [f.name for f in funcs if calls(f) == 0 or (asserts(f) == 0 and "raises" not in ast.unparse(f))]
    check(not thin, f"every test calls code and asserts something (thin: {thin[:3]})")


OTHER = dict(issue="2023-08-07", horizon=3, stock=1.0, crews=10, select="all")  # has transfers in, out, unplaced
OTHER_ARGS = ["--issue", "2023-08-07", "--horizon", "3", "--stock", "100", "--crews", "10", "--select", "all"]


def untouched(folder: Path) -> bool:
    return sorted(p.name for p in folder.rglob("*")) == ["keep.txt"]


def content() -> None:
    from moshari.dispatch import gsm_length
    check(SCRIPT.is_file(), "scripts/export_dispatch.py exists")
    check(EXPORTS.is_dir(), "exports/ exists")
    if failures:
        return
    PDFMOD = ROOT / "src" / "moshari" / "dispatch_pdf.py"
    check(PDFMOD.is_file(), "src/moshari/dispatch_pdf.py exists")
    for f in (SCRIPT, PDFMOD):
        if f.is_file():
            t = f.read_text("utf-8")
            check(".claude" not in t and "a2-exports" not in t, f"{f.name} does not use the goal's verifier or .claude/ files")
    issue, rows, want = expected()
    n = len(rows)
    check(n > 0, f"demo week {issue.date()} selects {n} High/Critical wards")
    committed = text_files(EXPORTS)
    compare(committed, want, "committed exports/")
    sms = {k: v for k, v in committed.items() if k.startswith("sms/")}
    over = [k for k, v in sms.items() if gsm_length(v.rstrip("\n")) > 160]
    check(bool(sms) and not over, f"{len(sms)} SMS files, all <= 160 GSM-7 chars (over: {over[:3]})")

    allowed = set(want) | {"README.md"}
    stray = [p.relative_to(EXPORTS).as_posix() for p in EXPORTS.rglob("*") if p.is_file()]
    stray = [x for x in stray if x not in allowed and not (x.startswith("briefs/") and x.endswith(".pdf"))]
    check(not stray, f"no stray files in exports/ ({stray[:3]})")

    top = str(rows[0]["ward_id"]) if rows else "?"
    top_pdf, all_pdf = EXPORTS / "briefs" / f"{top}.pdf", EXPORTS / "briefs" / "all_briefs.pdf"
    for p, prows in ((top_pdf, rows[:1]), (all_pdf, rows)):
        if check(p.is_file(), f"{p.relative_to(ROOT).as_posix()} exists (top-priority ward = {top})"):
            check_pdf(p, prows, f"committed {p.name}")
    pdfs = sorted((EXPORTS / "briefs").glob("*.pdf"))
    bad_pdf = [p.name for p in pdfs if p.stem != "all_briefs" and f"briefs/{p.stem}.html" not in want]
    check(not bad_pdf, f"every ward PDF has a matching ward brief ({bad_pdf[:3]})")

    readme = (EXPORTS / "README.md").read_text("utf-8") if (EXPORTS / "README.md").is_file() else ""
    target = (issue + __import__("pandas").Timedelta(weeks=3)).strftime("%Y-%m-%d")
    check("scripts/export_dispatch.py" in readme and target in readme and str(n) in readme
          and all(str(r["ward_id"]) in readme for r in rows),
          f"exports/README.md names the command, target week {target}, the {n} wards and the count")
    top_readme = (ROOT / "README.md").read_text("utf-8")
    check("python scripts/export_dispatch.py" in top_readme and "reportlab" in top_readme and "--pdf" in top_readme,
          "README.md documents the command, the --pdf flag and the reportlab install")

    probe = ("import sys; sys.path.insert(0, 'src'); import moshari.dispatch_pdf as m; "
             "assert callable(getattr(m, 'write_brief_pdf', None)); print('import ok')")

    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "fake"
        (fake / "reportlab").mkdir(parents=True)
        (fake / "reportlab" / "__init__.py").write_text("raise ImportError('reportlab hidden by verifier')\n")
        hide = {"PYTHONPATH": str(fake)}
        r = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True,
                           env=dict(os.environ, **hide))
        check(r.returncode == 0, "moshari.dispatch_pdf imports without reportlab and has write_brief_pdf")

        a = Path(td) / "a"
        r = run_script("--pdf", "none", "--out", str(a))
        check(r.returncode == 0, f"script with defaults exits 0 (got {r.returncode}) {r.stderr[-200:]!r}")
        compare(text_files(a), want, "fresh run with defaults")
        check(not list(a.rglob("*.pdf")), "--pdf none writes no PDF")
        e = Path(td) / "e"
        r = run_script("--out", str(e))
        same = r.returncode == 0 and all(
            (e / "briefs" / q.name).is_file() and (e / "briefs" / q.name).read_bytes() == q.read_bytes()
            for q in (top_pdf, all_pdf) if q.is_file()) and sorted(x.name for x in e.rglob("*.pdf")) == \
            sorted(x.name for x in (EXPORTS / "briefs").glob("*.pdf"))
        check(same, f"fresh default run reproduces the committed PDFs byte for byte (exit {r.returncode})")
        r = run_script("--pdf", "none", "--out", str(a))
        check(r.returncode == 0 and text_files(a) == want, "rerun into the same folder: identical, no leftovers")

        b = Path(td) / "b"
        _, rows2, want2 = expected(**OTHER)
        r = run_script("--pdf", "all", "--out", str(b), *OTHER_ARGS)
        check(r.returncode == 0, f"script with {' '.join(OTHER_ARGS)} --pdf all exits 0 (got {r.returncode})")
        compare(text_files(b), want2, f"other settings ({len(rows2)} wards)")
        wpdf = {p.stem for p in (b / "briefs").glob("*.pdf")} - {"all_briefs"}
        check(wpdf == {str(x["ward_id"]) for x in rows2}, f"--pdf all: one PDF per ward ({len(wpdf)}/{len(rows2)})")
        for x in rows2:
            q = b / "briefs" / f"{x['ward_id']}.pdf"
            if q.is_file() and page_problems((pdf_pages(q.read_bytes()) or [{"text": "", "box": None}])[0], x):
                check(False, f"other settings: {q.name} is that ward's full brief"); break
        else:
            check(True, f"other settings: every ward PDF is that ward's full brief")
        if (b / "briefs" / "all_briefs.pdf").is_file():
            check_pdf(b / "briefs" / "all_briefs.pdf", rows2, "other settings all_briefs.pdf")
        else:
            check(False, "other settings: all_briefs.pdf written")
        r = run_script("--pdf", "none", "--out", str(b))
        check(r.returncode == 0 and text_files(b) == want and not list(b.rglob("*.pdf")),
              "narrower rerun removes wards (and PDFs) that left the selection")

        c = Path(td) / "c"
        c.mkdir()
        (c / "keep.txt").write_text("x")
        for args, code, what in (
            (["--issue", EMPTY_ISSUE], 1, f"empty selection ({EMPTY_ISSUE})"),
            (["--issue", BAD_ISSUE], 2, f"unknown --issue {BAD_ISSUE}"),
            (["--horizon", "7"], 2, "--horizon 7"),
            (["--stock", "10"], 2, "--stock 10"),
            (["--crews", "-1"], 2, "--crews -1"),
        ):
            r = run_script("--pdf", "none", "--out", str(c), *args)
            check(r.returncode == code and untouched(c), f"{what} exits {code} and writes nothing (got {r.returncode})")
        r = run_script("--require-pdf", "--out", str(c), env_extra=hide)
        check(r.returncode == 1 and untouched(c),
              f"--require-pdf without reportlab exits 1 and writes nothing (got {r.returncode})")
        d = Path(td) / "d"
        r = run_script("--out", str(d), env_extra=hide)
        check(r.returncode == 0 and text_files(d) == want and not list(d.rglob("*.pdf"))
              and "reportlab" in (r.stdout + r.stderr),
              f"no reportlab, no --require-pdf: warns, exits 0, writes text + HTML (got {r.returncode})")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout


def git_mode() -> None:
    anc = subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT).returncode == 0
    check(anc, f"HEAD descends from {BASE}")
    subjects = [s for s in git("log", "--no-merges", "--format=%s", f"{BASE}..HEAD").splitlines() if s]
    work = [s for s in git("log", "--no-merges", "--format=%s", f"{BASE}..HEAD", "--", ".",
                            ":(exclude).claude").splitlines() if s]
    check(len(work) >= 1, f"{len(work)} new commit(s) since {BASE} that change files outside .claude/")
    authors = {a for a in git("log", "--no-merges", "--format=%an", f"{BASE}..HEAD", "--", ".",
                              ":(exclude).claude").splitlines() if a}
    check(authors == {"Ananya"}, f"work commits are authored by Ananya (authors: {sorted(authors)})")
    bad = [s for s in subjects if not s.startswith(PREFIX)]
    check(not bad, f"every new commit starts with '{PREFIX}' (bad: {bad[:3]})")
    changed = [f for f in git("diff", "--name-only", f"{BASE}..HEAD").splitlines() if f]
    outside = [f for f in changed if not any(fnmatch.fnmatch(f, pat) for pat in ALLOWED)]
    check(not outside, f"{len(changed)} changed files, all in scope (outside: {outside[:5]})")
    ananya = [c for c in git("log", "--no-merges", "--author=^Ananya$", "--format=%H", f"{BASE}..HEAD").split() if c]
    goal_edits = sorted({f for c in ananya for f in git("show", "--name-only", "--format=", c).splitlines()
                         if f.startswith(".claude/") and f != ".claude/goals/a2-exports-tasks.md"})
    check(not goal_edits, f"work commits change no .claude/ file except the checklist ({goal_edits[:3]})")
    req = git("diff", "-U0", f"{BASE}..HEAD", "--", "requirements-dev.txt")
    added = [l[1:].strip() for l in req.splitlines() if l.startswith("+") and not l.startswith("+++")]
    removed = [l for l in req.splitlines() if l.startswith("-") and not l.startswith("---")]
    check(not removed and all(re.match(r"^reportlab\b", x) for x in added if x),
          f"requirements-dev.txt only gains reportlab (added {added}, removed {len(removed)} lines)")
    dirty = [l for l in git("status", "--porcelain").splitlines() if l and not l[3:].startswith(".claude/")]
    check(not dirty, f"working tree clean outside .claude/ ({dirty[:5]})")
    tracked = set(git("ls-files", "exports").splitlines())
    on_disk = {p.relative_to(ROOT).as_posix() for p in EXPORTS.rglob("*") if p.is_file()} if EXPORTS.is_dir() else set()
    check(bool(on_disk) and tracked == on_disk, f"all {len(on_disk)} files in exports/ are committed")
    check(any(f.endswith(".pdf") for f in tracked), "a PDF brief is committed")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "content":
        try:
            content()
        except Exception as e:  # report, never pass
            check(False, f"verifier crashed: {type(e).__name__}: {e}")
    elif mode == "git":
        git_mode()
    elif mode == "tests":
        tests_file_checks()
    else:
        print("usage: a2-exports-verify.py content|tests|git")
        sys.exit(2)
    print(f"{'PASS' if not failures else 'FAIL'} {mode} ({len(failures)} failed checks)")
    sys.exit(0 if not failures else 1)
