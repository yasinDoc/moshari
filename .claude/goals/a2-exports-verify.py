"""Verifier for the a2-exports goal. Written before the run; the executor must not edit it.

    python .claude/goals/a2-exports-verify.py content   # criterion 1: exports/ and the script
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
ALLOWED = ["scripts/export_dispatch.py", "tests/test_export_dispatch.py", "exports/*", "README.md",
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


def run_script(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, MOSHARI_OFFLINE="1", PYTHONIOENCODING="utf-8")
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


def pdf_pages(p: Path) -> int:
    data = p.read_bytes()
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))


def content() -> None:
    from moshari.dispatch import gsm_length
    check(SCRIPT.is_file(), "scripts/export_dispatch.py exists")
    check(EXPORTS.is_dir(), "exports/ exists")
    if failures:
        return
    issue, rows, want = expected()
    n = len(rows)
    check(n > 0, f"demo week {issue.date()} selects {n} High/Critical wards")
    committed = text_files(EXPORTS)
    compare(committed, want, "committed exports/")
    sms = {k: v for k, v in committed.items() if k.startswith("sms/")}
    over = [k for k, v in sms.items() if gsm_length(v.rstrip("\n")) > 160]
    check(bool(sms) and not over, f"{len(sms)} SMS files, all <= 160 GSM-7 chars (over: {over[:3]})")

    allowed = set(want) | {"README.md"}
    pdfs = sorted(p for p in (EXPORTS / "briefs").glob("*.pdf"))
    stray = [str(p.relative_to(EXPORTS)).replace(os.sep, "/") for p in EXPORTS.rglob("*") if p.is_file()]
    stray = [s for s in stray if s not in allowed and not (s.startswith("briefs/") and s.endswith(".pdf"))]
    check(not stray, f"no stray files in exports/ ({stray[:3]})")

    top = str(rows[0]["ward_id"]) if rows else "?"
    top_pdf, all_pdf = EXPORTS / "briefs" / f"{top}.pdf", EXPORTS / "briefs" / "all_briefs.pdf"
    for p, pages in ((top_pdf, 1), (all_pdf, n)):
        if check(p.is_file(), f"{p.relative_to(ROOT).as_posix()} exists (top-priority ward = {top})"):
            b = p.read_bytes()
            check(b[:5] == b"%PDF-" and b"%%EOF" in b[-1024:] and len(b) >= 20000,
                  f"{p.name}: real PDF ({len(b)} bytes, header {b[:5]!r})")
            got = pdf_pages(p)
            check(got == pages, f"{p.name}: {got} page(s), expected {pages}")
    bad_pdf = [p.name for p in pdfs if p.stem != "all_briefs" and f"briefs/{p.stem}.html" not in want]
    check(not bad_pdf, f"every ward PDF has a matching ward brief ({bad_pdf[:3]})")

    readme = (EXPORTS / "README.md").read_text("utf-8") if (EXPORTS / "README.md").is_file() else ""
    target = (issue + __import__("pandas").Timedelta(weeks=3)).strftime("%Y-%m-%d")
    check("scripts/export_dispatch.py" in readme and target in readme and str(n) in readme
          and all(str(r["ward_id"]) in readme for r in rows),
          f"exports/README.md names the command, target week {target}, the {n} wards and the count")
    top_readme = (ROOT / "README.md").read_text("utf-8")
    check("export_dispatch.py" in top_readme, "README.md documents scripts/export_dispatch.py")

    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "a"
        r = run_script("--pdf", "none", "--out", str(a))
        check(r.returncode == 0, f"script with defaults exits 0 (got {r.returncode}) {r.stderr[-200:]!r}")
        compare(text_files(a), want, "fresh run with defaults")
        check(not list(a.rglob("*.pdf")), "--pdf none writes no PDF")
        r = run_script("--pdf", "none", "--out", str(a))
        check(r.returncode == 0 and text_files(a) == want, "rerun into the same folder: identical, no leftovers")

        b = Path(td) / "b"
        _, rows2, want2 = expected(horizon=2, stock=1.0, crews=10, select="all")
        r = run_script("--pdf", "none", "--out", str(b), "--horizon", "2", "--stock", "100",
                       "--crews", "10", "--select", "all")
        check(r.returncode == 0, f"script with --horizon 2 --stock 100 --crews 10 --select all exits 0 (got {r.returncode})")
        compare(text_files(b), want2, f"other settings ({len(rows2)} wards)")
        # the same folder, narrower selection: wards that left must be removed
        r = run_script("--pdf", "none", "--out", str(b))
        check(r.returncode == 0 and text_files(b) == want, "narrower rerun removes wards that left the selection")

        c = Path(td) / "c"
        c.mkdir()
        (c / "keep.txt").write_text("x")
        r = run_script("--pdf", "none", "--out", str(c), "--issue", EMPTY_ISSUE)
        check(r.returncode == 1 and sorted(p.name for p in c.rglob("*")) == ["keep.txt"],
              f"empty selection ({EMPTY_ISSUE}) exits 1 and writes nothing (got {r.returncode})")
        r = run_script("--pdf", "none", "--out", str(c), "--issue", BAD_ISSUE)
        check(r.returncode == 2 and sorted(p.name for p in c.rglob("*")) == ["keep.txt"],
              f"unknown --issue {BAD_ISSUE} exits 2 and writes nothing (got {r.returncode})")
        r = run_script("--pdf", "top", "--require-pdf", "--browser", str(Path(td) / "no-such-browser"),
                       "--out", str(c))
        check(r.returncode == 1 and sorted(p.name for p in c.rglob("*")) == ["keep.txt"],
              f"--require-pdf with a missing browser exits 1 and writes nothing (got {r.returncode})")
        d = Path(td) / "d"
        r = run_script("--pdf", "top", "--browser", str(Path(td) / "no-such-browser"), "--out", str(d))
        check(r.returncode == 0 and text_files(d) == want and not list(d.rglob("*.pdf")),
              f"missing browser without --require-pdf: warns, exits 0, writes text + HTML (got {r.returncode})")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout


def git_mode() -> None:
    anc = subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT).returncode == 0
    check(anc, f"HEAD descends from {BASE}")
    subjects = [s for s in git("log", "--no-merges", "--format=%s", f"{BASE}..HEAD").splitlines() if s]
    work = [s for s in git("log", "--no-merges", "--format=%s", f"{BASE}..HEAD", "--", ".",
                            ":(exclude).claude").splitlines() if s]
    check(len(work) >= 1, f"{len(work)} new commit(s) since {BASE} that change files outside .claude/")
    bad = [s for s in subjects if not s.startswith(PREFIX)]
    check(not bad, f"every new commit starts with '{PREFIX}' (bad: {bad[:3]})")
    changed = [f for f in git("diff", "--name-only", f"{BASE}..HEAD").splitlines() if f]
    outside = [f for f in changed if not any(fnmatch.fnmatch(f, pat) for pat in ALLOWED)]
    check(not outside, f"{len(changed)} changed files, all in scope (outside: {outside[:5]})")
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
    else:
        print("usage: a2-exports-verify.py content|git")
        sys.exit(2)
    print(f"{'PASS' if not failures else 'FAIL'} {mode} ({len(failures)} failed checks)")
    sys.exit(0 if not failures else 1)
