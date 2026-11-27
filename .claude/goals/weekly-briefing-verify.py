"""Verifier for the weekly-briefing goal. Written before the run; the executor must not edit it.

    python .claude/goals/weekly-briefing-verify.py logic   # criterion 1: moshari.briefing numbers and sentences
    python .claude/goals/weekly-briefing-verify.py pdf     # criterion 2: the one-page PDF
    python .claude/goals/weekly-briefing-verify.py page    # criterion 3: Overview strip and briefing page (AppTest)
    python .claude/goals/weekly-briefing-verify.py tests   # criterion 4: new test files are real
    python .claude/goals/weekly-briefing-verify.py git     # criterion 6: committed, prefixed, in scope

Prints "ok ..." / "FAIL ..." per check and a final "PASS <mode>" or "FAIL <mode>". Exit 0 only on
PASS. Every expected value is recomputed here from the pinned engines, never read from the
code under test. Runs offline (MOSHARI_OFFLINE=1).
"""

from __future__ import annotations

import ast
import fnmatch
import html
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "173de29"
PREFIX = "version-onsite-final:"
AUTHOR = ("Ananya", "297095755+sam21-og@users.noreply.github.com")
ALLOWED = ["src/moshari/briefing.py", "src/moshari/briefing_pdf.py", "ui/views/briefing.py",
           "ui/views/ward_net.py", "ui/theme.py", "app.py", "requirements.txt", "README.md",
           "tests/test_briefing.py", "tests/test_briefing_page.py",
           ".claude/goals/*"]  # goal files are committed too; pins guard the design and this verifier
NEW_TESTS = ["tests/test_briefing.py", "tests/test_briefing_page.py"]
# (issue, horizon, cities, stock, crews, surge): demo week; transfers + unplaced; no High ward;
# one city under hard scarcity with surge beds. Measured on 173de29 (2026-11-27).
SETTINGS = [("2025-06-02", 3, (), 0.70, 40, 0), ("2024-07-01", 4, (), 0.70, 40, 0),
            ("2016-02-29", 3, (), 0.70, 40, 0), ("2025-06-02", 3, ("Dhaka North",), 0.30, 10, 20)]

sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
os.environ["MOSHARI_OFFLINE"] = "1"
for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

failures: list[str] = []


def check(ok, what: str) -> bool:
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)
    return bool(ok)


def finish(mode: str) -> None:
    print(("FAIL " if failures else "PASS ") + mode + (f" ({len(failures)} failed)" if failures else ""))
    sys.exit(1 if failures else 0)


# --------------------------------------------------------------------------- reference model
_SVC = None


def svc():
    global _SVC
    if _SVC is None:
        from moshari.data import load_dataset
        from moshari.model import ForecastBundle
        from moshari.service import ForecastService
        _SVC = ForecastService(load_dataset(), ForecastBundle.load())
    return _SVC


def pl(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def ref_alerts(alloc, ws) -> dict:
    return {"saline_wards": int((alloc["saline_bags_allocated"] < alloc["saline_bags_needed"]).sum()),
            "kits_wards": int((alloc["diagnostic_kits_allocated"] < alloc["diagnostic_kits_needed"]).sum()),
            "crews_short": int((alloc["crews_needed"] - alloc["crews_assigned"]).clip(lower=0).sum()),
            "out_of_beds_wards": int((ws["net_deficit"] > 0).sum())}


def ref_alert_text(a: dict) -> str:
    parts = [(a["saline_wards"], "ward", " short on saline"), (a["kits_wards"], "ward", " short on test kits"),
             (a["crews_short"], "crew", " short"), (a["out_of_beds_wards"], "ward", " out of beds")]
    out = [pl(n, w) + tail for n, w, tail in parts if n]
    return " · ".join(out) if out else "All wards supplied"


def expected(issue, horizon, cities=(), stock=0.70, crews=40, surge=0) -> dict:
    import pandas as pd
    from moshari import allocation as A, dispatch as D, routing as R, simulation as S
    from moshari.risk import DEFAULT_ALERT_POLICY
    sv = svc()
    issue = pd.Timestamp(issue)
    fc = sv.forecast_all(issue, horizon, list(cities) or None, DEFAULT_ALERT_POLICY)
    alloc = A.allocate(fc, sv.wards, stock, crews)
    summ = A.summarize(alloc, crews)
    rr = R.route_overflow(A.allocate(fc, sv.wards), R.with_surge(R.load_bed_capacity(), surge))
    table = S.build_effect_table(sv, issue, cities=list(cities) or None)
    plan = {w: int(c) for w, c in zip(alloc["ward_id"], alloc["crews_assigned"]) if c > 0}
    by_h = S.simulate(table, plan)[1]
    notices = D.select_rows(D.dispatch_table(alloc, R.route_overflow(alloc, R.load_bed_capacity())), "high")
    target = issue + pd.Timedelta(weeks=horizon)
    wards, high = len(fc), int((fc["tier_idx"] >= 2).sum())
    cr = summ["crews"]
    needed, assigned, unmet = cr["needed"], cr["assigned"], cr["unmet"]
    sal, kits = summ["resources"]["saline bags"]["short"], summ["resources"]["test kits"]["short"]
    deficit = summ["deficit_wards"]
    transfers = rr.transfers.to_dict("records")
    moved = int(rr.transfers["patients"].sum()) if len(rr.transfers) else 0
    unplaced = int(rr.ward_summary["net_deficit"].sum())
    s2 = ("No spraying crews are needed this week." if needed == 0 else
          f"Approve {pl(unmet, 'more spraying crew')}: {needed} needed, {assigned} assigned." if unmet else
          f"All {needed} crews needed are assigned.")
    s3 = (f"Release {pl(sal, 'more saline bag')} and {pl(kits, 'more test kit')} to cover "
          f"{pl(deficit, 'short ward')}." if deficit else "Every ward is fully supplied.")
    if moved and unplaced:
        s4 = (f"Move {pl(moved, 'patient')} between wards in the same city; beds are still missing for "
              f"{pl(unplaced, 'patient')}.")
    elif moved:
        s4 = f"Move {pl(moved, 'patient')} between wards in the same city; every patient has a bed."
    elif unplaced:
        s4 = f"No transfer can help: beds are still missing for {pl(unplaced, 'patient')}."
    else:
        s4 = "No patient transfers are needed."
    return {
        "issue_date": issue, "target_week": target, "horizon": horizon,
        "cities": sorted(fc["city"].unique()), "stock_pct": stock, "crews": crews, "surge_pct": surge,
        "wards": wards, "high_wards": high, "critical_wards": int((fc["tier_idx"] == 3).sum()),
        "expected_cases": float(fc["expected_cases"].sum()), "top_wards": list(fc["ward_id"].head(5)),
        "saline_short_bags": sal, "kits_short": kits, "deficit_wards": deficit,
        "alerts": ref_alerts(alloc, rr.ward_summary), "transfers": transfers, "patients_moved": moved,
        "unplaced": unplaced, "crews_needed": needed, "crews_assigned": assigned, "crews_unmet": unmet,
        "cases_prevented": round(float(by_h["cases_prevented"].sum()), 1), "notices_ready": len(notices),
        "decision": [f"{high} of {pl(wards, 'ward')} are High or Critical risk for the week of "
                     f"{target:%d %b %Y}.", s2, s3, s4],
    }


def build(issue, horizon, cities=(), stock=0.70, crews=40, surge=0) -> dict:
    import pandas as pd
    from moshari import briefing as B
    return B.build(svc(), pd.Timestamp(issue), horizon, cities=tuple(cities), stock_pct=stock, crews=crews,
                   surge_pct=surge)


def same(a, b) -> bool:
    import pandas as pd
    if isinstance(b, float):
        try:
            return abs(float(a) - b) < 0.051
        except (TypeError, ValueError):
            return False
    if isinstance(b, pd.Timestamp):
        try:
            return pd.Timestamp(a) == b
        except (TypeError, ValueError):
            return False
    if isinstance(b, list) and b and isinstance(b[0], dict):
        try:
            return [{k: (int(v) if k == "patients" else str(v)) for k, v in dict(x).items()} for x in a] == \
                   [{k: (int(v) if k == "patients" else str(v)) for k, v in x.items()} for x in b]
        except (TypeError, ValueError):
            return False
    if isinstance(b, dict):
        return isinstance(a, dict) and set(a) >= set(b) and all(same(a[k], v) for k, v in b.items())
    if isinstance(b, list):
        return list(a) == b if not isinstance(a, str) else False
    if isinstance(b, bool):
        return a is b or a == b
    if isinstance(b, int):
        try:
            return not isinstance(a, (bool, str, float)) and int(a) == b
        except (TypeError, ValueError):
            return False
    return a == b


# --------------------------------------------------------------------------- modes
def mode_logic() -> None:
    for name in ("briefing.py", "briefing_pdf.py"):
        p = ROOT / "src" / "moshari" / name
        if check(p.exists(), f"src/moshari/{name} exists"):
            src = p.read_text(encoding="utf-8")
            check(not re.search(r"^\s*(import|from)\s+(requests|urllib|httpx|socket|streamlit)\b", src, re.M),
                  f"{name} imports no network library and no streamlit")
            check("verify" not in src and ".claude" not in src, f"{name} does not read the goal files")
    if failures:
        return finish("logic")
    from moshari import briefing as B
    for st in SETTINGS:
        exp, got = expected(*st), build(*st)
        bad = [k for k in exp if k not in got or not same(got[k], exp[k])]
        check(not bad, f"build{st} matches the engines" + (f"; wrong: {bad[:6]}" if bad else ""))
        for k in bad[:3]:
            print(f"     {k}: expected {exp[k]!r:.200}\n     {k}: got      {got.get(k, '<missing>')!r:.200}")
    cases = [({"saline_wards": 0, "kits_wards": 0, "crews_short": 0, "out_of_beds_wards": 0}, "All wards supplied"),
             ({"saline_wards": 1, "kits_wards": 0, "crews_short": 1, "out_of_beds_wards": 1},
              "1 ward short on saline · 1 crew short · 1 ward out of beds"),
             ({"saline_wards": 12, "kits_wards": 2, "crews_short": 0, "out_of_beds_wards": 3},
              "12 wards short on saline · 2 wards short on test kits · 3 wards out of beds")]
    for a, want in cases:
        check(B.alert_text(dict(a)) == want, f"alert_text({a}) == {want!r}")
    check(B.plural(1, "ward") == "1 ward" and B.plural(0, "ward") == "0 wards", "plural singular and zero")
    finish("logic")


def _unescape(t: bytes) -> str:
    t = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 0xFF]), t)
    return re.sub(rb"\\(.)", rb"\1", t).decode("latin-1")


def pdf_pages(data: bytes) -> list[dict]:
    objs = {int(m.group(1)): m.group(2) for m in re.finditer(rb"(?s)(\d+) 0 obj\b(.*?)endobj", data)}
    pages = []
    for o in objs.values():
        if re.search(rb"/Type\s*/Page\b", o):
            c = re.search(rb"/Contents\s+(\d+) 0 R", o)
            stream = objs.get(int(c.group(1)), b"") if c else b""
            m = re.search(rb"(?s)stream\r?\n(.*)endstream", stream)
            raw = m.group(1) if m else b""
            strings = [_unescape(t) for t in re.findall(rb"\(((?:[^()\\]|\\.)*)\)\s*Tj", raw)]
            box = re.search(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", o)
            pages.append({"text": re.sub(r"\s+", " ", " ".join(strings)).strip(),
                          "box": tuple(float(x) for x in box.groups()) if box else None})
    return pages


def mode_pdf() -> None:
    from moshari.data import ward_label
    try:
        from moshari.briefing_pdf import briefing_pdf
    except Exception as e:  # noqa: BLE001
        check(False, f"import moshari.briefing_pdf.briefing_pdf ({e})")
        return finish("pdf")
    outputs = []
    for st in SETTINGS:
        exp = expected(*st)
        data = briefing_pdf(build(*st))
        outputs.append(data)
        tag = f"{st[0]} h{st[1]}{' ' + ','.join(st[2]) if st[2] else ''}"
        check(isinstance(data, bytes) and data.startswith(b"%PDF") and b"ReportLab" in data, f"{tag}: reportlab PDF bytes")
        check(data == briefing_pdf(build(*st)), f"{tag}: same bytes on a second run")
        pages = pdf_pages(data)
        check(len(pages) == 1, f"{tag}: exactly one page (found {len(pages)})")
        if not pages:
            continue
        box = pages[0]["box"] or (0, 0, 0, 0)
        check(abs(box[2] - 595.28) < 1 and abs(box[3] - 841.89) < 1, f"{tag}: A4 portrait")
        text = pages[0]["text"]
        need = ["Weekly briefing", "Risk", "Supplies", "Patient transfers", "Crew plan", "Notices",
                "Made offline by Moshari", f"{exp['cases_prevented']:,.0f}", str(exp["notices_ready"]),
                *exp["decision"], *[ward_label(w) for w in exp["top_wards"]],
                *[f"{ward_label(t['from_ward'])} to {ward_label(t['to_ward'])}: {int(t['patients'])}"
                  for t in exp["transfers"][:8]]]
        missing = [n for n in need if n not in text]
        check(not missing, f"{tag}: page shows decision, sections, top wards, transfers"
              + (f"; missing {missing[:4]}" if missing else ""))
    check(len(set(outputs)) == len(outputs), "every setting gives a different PDF")
    finish("pdf")


def _strip(page_html: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page_html)))


_STORES: list = []


def _app(issue: str, h: int, page: str):
    import streamlit.testing.v1.app_test as T
    from streamlit.testing.v1 import AppTest
    base = T.MemoryMediaFileStorage
    if not getattr(base, "_kept", False):  # keep every run's media store so downloads can be read back
        class Kept(base):
            _kept = True
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                _STORES.append(self)
        T.MemoryMediaFileStorage = Kept
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    at.query_params["issue"] = issue
    at.query_params["h"] = str(h)
    at.switch_page(page)
    at.run()
    return at


def _text(at) -> str:
    parts = [e.value for e in at.get("html")] + [str(getattr(e, "value", "")) for e in at.get("markdown")]
    return re.sub(r"\s+", " ", " ".join(_strip(p) for p in parts))


def _media(url: str):
    fid = url.rsplit("/", 1)[-1].split(".")[0]
    for o in reversed(_STORES):
        if fid in o._files_by_id:
            return o._files_by_id[fid]
    return None


def mode_page() -> None:
    import pandas as pd
    from moshari import allocation as A, routing as R
    from moshari.risk import DEFAULT_ALERT_POLICY
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    check('st.Page("ui/views/briefing.py", title="Weekly briefing"' in app, "app.py lists the Weekly briefing page")
    for issue, h in [("2025-06-02", 3), ("2024-07-01", 4), ("2016-02-29", 3)]:
        at = _app(issue, h, "ui/views/ward_net.py")
        if not check(not at.exception, f"Overview {issue} h{h} renders ({at.exception})"):
            continue
        fc = svc().forecast_all(pd.Timestamp(issue), h, None, DEFAULT_ALERT_POLICY)
        alloc = A.allocate(fc, svc().wards, 0.70, 40)
        rr = R.route_overflow(A.allocate(fc, svc().wards), R.with_surge(R.load_bed_capacity(), 0))
        want = ref_alert_text(ref_alerts(alloc, rr.ward_summary))
        text = _text(at)
        check(want in text, f"Overview {issue} h{h} strip says {want!r}")
        check("At 70% stock and 40 crews." in text, f"Overview {issue} h{h} states the scenario")
        check("Expected high risk" in text and "Send teams here first" in text, f"Overview {issue} h{h} keeps its cards")
    from moshari.briefing_pdf import briefing_pdf
    for issue, h in [("2025-06-02", 3), ("2016-02-29", 3)]:
        at = _app(issue, h, "ui/views/briefing.py")
        if not check(not at.exception, f"Weekly briefing {issue} h{h} renders ({at.exception})"):
            continue
        exp = expected(issue, h)
        text = _text(at)
        miss = [s for s in exp["decision"] if s not in text]
        check(not miss, f"Weekly briefing {issue}: shows the 4 decision sentences" + (f"; missing {miss[:2]}" if miss else ""))
        btns = [b for b in at.get("download_button") if "PDF" in b.proto.label]
        if check(len(btns) == 1, f"Weekly briefing {issue}: one PDF download button"):
            f = _media(btns[0].proto.url)
            check(f is not None and f.mimetype == "application/pdf", f"Weekly briefing {issue}: button serves application/pdf")
            check(f is not None and bytes(f.content) == briefing_pdf(build(issue, h)),
                  f"Weekly briefing {issue}: PDF equals briefing_pdf(build(...)) at 70%/40/+0")
            name = getattr(f, "filename", None) if f is not None else None
            check(name == f"moshari_briefing_{exp['target_week']:%Y-%m-%d}.pdf", f"Weekly briefing {issue}: file name ({name})")
        if issue == "2025-06-02":  # the controls must drive the PDF, not just the defaults
            try:
                at.slider(key="brief_stock").set_value(30)
                at.number_input(key="brief_crews").set_value(10)
                at.slider(key="brief_surge").set_value(20)
                at.run()
                btn = [b for b in at.get("download_button") if "PDF" in b.proto.label]
                f2 = _media(btn[0].proto.url) if btn else None
                ok = f2 is not None and bytes(f2.content) == briefing_pdf(build(issue, h, (), 0.30, 10, 20))
            except Exception as e:  # noqa: BLE001
                print(f"     controls: {e}")
                ok = False
            check(ok, "Weekly briefing: brief_stock=30, brief_crews=10, brief_surge=20 give the PDF of that scenario")
    finish("page")


def mode_tests() -> None:
    for rel in NEW_TESTS:
        p = ROOT / rel
        if not check(p.exists(), f"{rel} exists"):
            continue
        src = p.read_text(encoding="utf-8")
        check(not re.search(r"\b(skip|skipif|xfail|importorskip)\b", src), f"{rel}: no skip/xfail/importorskip")
        check("verify" not in src and ".claude" not in src, f"{rel}: does not use the goal verifier")
        tree = ast.parse(src)
        fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
        def real(f) -> bool:  # calls something and asserts on a non-constant, or uses pytest.raises
            calls = any(isinstance(x, ast.Call) for x in ast.walk(f))
            asserts = [x for x in ast.walk(f) if isinstance(x, ast.Assert) and not isinstance(x.test, ast.Constant)]
            return calls and (bool(asserts) or "raises" in ast.unparse(f))
        hollow = [f.name for f in fns if not real(f)]
        check(not hollow, f"{rel}: every test calls code and asserts" + (f"; hollow: {hollow[:4]}" if hollow else ""))
        src = ast.unparse(tree)  # token checks below ignore comments
        if rel.endswith("test_briefing.py"):
            check(len(fns) >= 10, f"{rel}: >= 10 test functions ({len(fns)})")
            for tok in ("briefing_pdf", "alert_text", "build(", "2024-07-01", "2016-02-29"):
                check(tok in src, f"{rel}: uses {tok}")
        else:
            check(len(fns) >= 3, f"{rel}: >= 3 test functions ({len(fns)})")
            for tok in ("AppTest", "ward_net.py", "briefing.py"):
                check(tok in src, f"{rel}: uses {tok}")
    finish("tests")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout


def mode_git() -> None:
    check(git("status", "--porcelain", "--untracked-files=all", "--", ".", ":(exclude).claude").strip() == "",
          "working tree clean outside .claude/")
    commits = [l for l in git("log", "--format=%H%x09%an%x09%ae%x09%s", f"{BASE}..HEAD").splitlines() if l]
    check(len(commits) >= 2, f"at least 2 commits since {BASE} ({len(commits)})")
    for line in commits:
        sha, an, ae, subj = line.split("\t", 3)
        check(subj.startswith(PREFIX) and (an, ae) == AUTHOR, f"{sha[:7]} prefixed and authored by Ananya")
    files = [f for f in git("diff", "--name-only", f"{BASE}..HEAD").splitlines() if f]
    out = [f for f in files if not any(fnmatch.fnmatch(f, a) for a in ALLOWED)]
    check(not out, "only files in SCOPE changed" + (f"; outside: {out[:5]}" if out else ""))
    for f in NEW_TESTS + ["src/moshari/briefing.py", "src/moshari/briefing_pdf.py", "ui/views/briefing.py"]:
        check(f in files, f"{f} committed")
    def diff_lines(path: str) -> tuple[list[str], list[str]]:
        d = git("diff", "-U0", f"{BASE}..HEAD", "--", path).splitlines()
        add = [l[1:] for l in d if l.startswith("+") and not l.startswith("+++")]
        rem = [l[1:] for l in d if l.startswith("-") and not l.startswith("---")]
        return add, rem
    add, rem = diff_lines("app.py")
    check(not rem and len(add) == 1 and "ui/views/briefing.py" in add[0], "app.py: exactly one added line, the page")
    add, rem = diff_lines("requirements.txt")
    check(not rem and len(add) == 1 and add[0].strip().startswith("reportlab"), "requirements.txt: only reportlab added")
    add, rem = diff_lines("ui/views/ward_net.py")
    check(len(rem) <= 4, f"ward_net.py: at most 4 lines removed ({len(rem)})")
    finish("git")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    {"logic": mode_logic, "pdf": mode_pdf, "page": mode_page, "tests": mode_tests, "git": mode_git}.get(
        mode, lambda: (print("usage: weekly-briefing-verify.py logic|pdf|page|tests|git"), sys.exit(2)))()
