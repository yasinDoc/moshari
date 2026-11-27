"""Verifier for the bangla-pdf goal (goal 2 of 2): the Weekly briefing PDF in Bangla.

Run from the project root:  python .claude/goals/bangla-pdf-verify.py <mode>
Modes: fonts | en | bn | page | tests | git | review
Each check mode prints "PASS <mode>" or "FAIL <mode>: ..." and exits 0 / 1. `review` writes the
Bangla PDFs to .claude/goals/bangla-pdf-review/ for a person to open (not a check).

Why it reads the PDF this way: shaped Bangla cannot be read back reliably from a PDF (text
extraction drops joined letters), so the verifier records every text that briefing_pdf() hands
to reportlab (Paragraphs, table cells, canvas strings) with the font used, while it builds the
PDF; it also checks the finished bytes (one A4 page, Bangla font embedded, deterministic).
Written before the work and pinned: the executor must not edit it.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BASE = "5c533fb"            # the commit goal 1 ended on; goal 2's diff is measured from it
NEW_TEST = "tests/test_briefing_pdf_bn.py"
MIN_NEW_TESTS = 8
FONT_DIR = ROOT / "src" / "moshari" / "fonts"
FONTS = {"NotoSansBengali-Regular.ttf": "89e77fc7f35436abc4a972f60701c5f6684b6bfd23e4f73880d7da8132e5c2c9",
         "NotoSansBengali-Bold.ttf": "fffa71fbfe82996f030ac55f15f785c9f6b20f540c3e77ea532b065e850d8af4"}
# (issue, horizon, stock, crews, surge) -> sha256 of today's English PDF (main 0cf943d)
SCENARIOS = {
    ("2025-06-02", 3, 0.70, 40, 0): "410064f0826fb403e9958caf4d2f1774d71c2c46697fcc7357f0214e19ec04bd",
    ("2024-07-01", 4, 0.70, 40, 0): "8721a41f617686aff024751a5ab014463f25e9f3a7988a0863511d0c7ea4a158",
    ("2016-02-29", 3, 0.70, 40, 0): "77ff6d024bee6adfdbc78166b9b96db0054448ec06086bf07879a81d92dff971",
    ("2023-08-07", 3, 1.00, 10, 20): "22c4823333c6d4b0f01b98b47c3cfe73b9a8128590437e6d806e8ab7709986a8",
}
ALLOWED_WORDS = {"Moshari", "DGHS", "NS1", "SMS", "WhatsApp", "PDF", "CSV", "ZIP", "A4", "AI",
                 "Open-Meteo", "LightGBM"}
CODE_RE = re.compile(r"\b(?:DNCC|DSCC|CCC|GCC|NCC)(?:[-_ ]W(?:ard_)?\d{1,3})?\b|\bW\d{1,3}\b")
BENGALI = re.compile(r"[ঀ-৿]")


def out(mode: str, problems: list[str], detail: str = "") -> int:
    if problems:
        print(f"FAIL {mode}: {len(problems)} problem(s)")
        for p in problems[:40]:
            print("  -", p)
        return 1
    print(f"PASS {mode}" + (f" ({detail})" if detail else ""))
    return 0


def _prepare() -> None:
    os.environ["MOSHARI_OFFLINE"] = "1"
    for p in (str(ROOT / "src"), str(ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)
    import logging

    logging.getLogger("streamlit").setLevel(logging.ERROR)


_SVC = None


def svc():
    global _SVC
    if _SVC is None:
        _prepare()
        from moshari.data import load_dataset
        from moshari.model import ForecastBundle
        from moshari.service import ForecastService

        _SVC = ForecastService(load_dataset(), ForecastBundle.load())
    return _SVC


def brief(sc, lang: str):
    import pandas as pd
    from moshari import briefing as B

    issue, h, stock, crews, surge = sc
    kw = {"stock_pct": stock, "crews": crews, "surge_pct": surge}
    if lang != "en":
        kw["lang"] = lang
    return B.build(svc(), pd.Timestamp(issue), h, (), **kw)


def pdf(b, lang: str) -> bytes:
    from moshari.briefing_pdf import briefing_pdf

    return briefing_pdf(b) if lang == "en" else briefing_pdf(b, lang=lang)


def strip_markup(s: str) -> str:
    import html

    return html.unescape(re.sub(r"<[^>]+>", " ", s))


def latin_left(s: str) -> list[str]:
    s = CODE_RE.sub(" ", strip_markup(s))
    for w in sorted(ALLOWED_WORDS, key=len, reverse=True):
        s = re.sub(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", " ", s)
    return re.findall(r"[A-Za-z][A-Za-z'\-]*|[0-9]+", s)


def record(fn):
    """Run fn() while recording every text given to reportlab, with its font and shaping."""
    from reportlab.pdfgen import canvas as C
    from reportlab.platypus import Paragraph, Table

    rec: list[dict] = []
    p_init, t_init = Paragraph.__init__, Table.__init__
    draws = {n: getattr(C.Canvas, n) for n in ("drawString", "drawRightString", "drawCentredString")}

    def para(self, text, style=None, *a, **k):
        p_init(self, text, style, *a, **k)
        st = self.style
        rec.append({"kind": "para", "text": str(text), "font": st.fontName,
                    "shaping": bool(getattr(st, "shaping", 0))})

    def table(self, data, *a, **k):
        t_init(self, data, *a, **k)
        for row in data or []:
            for cell in row:
                if isinstance(cell, str) and cell.strip():
                    rec.append({"kind": "cell", "text": cell, "font": "?", "shaping": False})

    def wrap(name):
        orig = draws[name]

        def f(self, x, y, text, *a, **k):
            rec.append({"kind": "draw", "text": str(text), "font": self._fontname, "shaping": False})
            return orig(self, x, y, text, *a, **k)
        return f

    Paragraph.__init__, Table.__init__ = para, table
    for n in draws:
        setattr(C.Canvas, n, wrap(n))
    try:
        result = fn()
    finally:
        Paragraph.__init__, Table.__init__ = p_init, t_init
        for n, f in draws.items():
            setattr(C.Canvas, n, f)
    return result, rec


def is_bangla_font(name: str) -> bool:
    from reportlab.pdfbase import pdfmetrics

    try:
        face = pdfmetrics.getFont(name).face
    except (KeyError, AttributeError):
        return False
    return b"Bengali" in (getattr(face, "name", b"") or b"")


def page_facts(data: bytes) -> list[str]:
    problems = []
    if not data.startswith(b"%PDF"):
        return ["not a PDF"]
    pages = len(re.findall(rb"/Type\s*/Page\b", data))
    if pages != 1:
        problems.append(f"{pages} pages, expected 1")
    if not re.search(rb"/MediaBox\s*\[\s*0\s+0\s+595\.27\d*\s+841\.88\d*\s*\]", data):
        problems.append("page is not A4")
    return problems


# --------------------------------------------------------------------------- modes
def mode_fonts() -> int:
    problems = []
    for name, want in FONTS.items():
        f = FONT_DIR / name
        if not f.exists():
            problems.append(f"{f.relative_to(ROOT)} missing")
        elif hashlib.sha256(f.read_bytes()).hexdigest() != want:
            problems.append(f"{name} is not the official Google Fonts Noto Sans Bengali v33 file")
    lic = FONT_DIR / "OFL.txt"
    if not lic.exists() or "SIL OPEN FONT LICENSE" not in lic.read_text(encoding="utf-8", errors="replace").upper():
        problems.append("src/moshari/fonts/OFL.txt (the font's SIL Open Font License) missing")
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    if not re.search(r"(?m)^uharfbuzz\b", req):
        problems.append("uharfbuzz not in requirements.txt (reportlab needs it to join Bangla letters)")
    try:
        import uharfbuzz  # noqa: F401
    except ImportError:
        problems.append("uharfbuzz not installed")
    return out("fonts", problems)


def mode_en() -> int:
    problems = []
    for sc, want in SCENARIOS.items():
        got = hashlib.sha256(pdf(brief(sc, "en"), "en")).hexdigest()
        if got != want:
            problems.append(f"English PDF for {sc} changed (sha {got[:12]}, was {want[:12]})")
    return out("en", problems, f"{len(SCENARIOS)} English PDFs byte-identical to main")


def mode_bn() -> int:
    problems = []
    for sc in SCENARIOS:
        try:
            b_en = brief(sc, "en")
            b_bn = brief(sc, "bn")
        except TypeError as e:
            return out("bn", [f"briefing.build() has no lang keyword: {e}"])
        d_en, rec_en = record(lambda: pdf(b_en, "en"))
        try:
            d_bn, rec_bn = record(lambda: pdf(b_bn, "bn"))
        except TypeError as e:
            return out("bn", [f"briefing_pdf() has no lang keyword: {e}"])
        label = f"{sc[0]} h{sc[1]}"
        problems += [f"{label}: {p}" for p in page_facts(d_bn)]
        if pdf(b_bn, "bn") != d_bn:
            problems.append(f"{label}: Bangla PDF bytes not deterministic")
        if b"NotoSansBengali" not in d_bn:
            problems.append(f"{label}: Noto Sans Bengali not embedded")
        left = sorted({w for r in rec_bn for w in latin_left(r["text"])})
        if left:
            problems.append(f"{label}: English words or Latin digits left: {left[:15]}")
        bad_font = [r["text"][:40] for r in rec_bn if BENGALI.search(r["text"]) and not (
            r["kind"] == "para" and r["shaping"] and is_bangla_font(r["font"]))]
        if bad_font:
            problems.append(f"{label}: Bangla text not drawn with the shaped Bangla font: {bad_font[:4]}")
        kinds_en = [r["kind"] for r in rec_en]
        kinds_bn = [r["kind"] for r in rec_bn]
        if kinds_en.count("para") != kinds_bn.count("para"):
            problems.append(f"{label}: {kinds_bn.count('para')} paragraphs in Bangla vs "
                            f"{kinds_en.count('para')} in English (content dropped or added)")
        en_letters = sum(len(re.findall(r"[A-Za-z]", strip_markup(r["text"]))) for r in rec_en)
        bn_letters = sum(len(BENGALI.findall(strip_markup(r["text"]))) for r in rec_bn)
        if bn_letters < 0.5 * en_letters:
            problems.append(f"{label}: too little Bangla ({bn_letters} vs {en_letters} English letters)")
        bn_text = " ".join(re.sub(r"\s+", " ", strip_markup(r["text"])) for r in rec_bn)
        decision = b_bn.get("decision") or []
        if not decision or not all(BENGALI.search(s) for s in decision):
            problems.append(f"{label}: build(lang='bn') decision sentences are not Bangla: {decision[:1]}")
        for s in decision:
            if re.sub(r"\s+", " ", s) not in bn_text:
                problems.append(f"{label}: decision sentence missing from the Bangla PDF: {s[:60]!r}")
        if [len(x) for x in (b_en.get("decision") or [])] and len(decision) != len(b_en.get("decision") or []):
            problems.append(f"{label}: {len(decision)} Bangla decision sentences vs {len(b_en['decision'])}")
    return out("bn", problems, f"{len(SCENARIOS)} Bangla PDFs")


_STORES: list = []


def _app(lang: str):
    import streamlit.testing.v1.app_test as T
    from streamlit.testing.v1 import AppTest

    base = T.MemoryMediaFileStorage
    if not getattr(base, "_kept", False):
        class Kept(base):
            _kept = True

            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                _STORES.append(self)
        T.MemoryMediaFileStorage = Kept
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    at.session_state["lang"] = lang
    at.query_params["issue"] = "2025-06-02"
    at.query_params["h"] = "3"
    at.switch_page("ui/views/briefing.py")
    at.run()
    return at


def _download(at):
    btns = list(at.get("download_button"))
    if len(btns) != 1:
        return None, f"{len(btns)} download buttons"
    fid = btns[0].proto.url.rsplit("/", 1)[-1].split(".")[0]
    for o in reversed(_STORES):
        if fid in o._files_by_id:
            return o._files_by_id[fid].content, btns[0].proto.label
    return None, "download bytes not found"


def mode_page() -> int:
    _prepare()
    problems = []
    sc = ("2025-06-02", 3, 0.70, 40, 0)
    got = {}
    for lang in ("en", "bn", "en"):           # en first and last: catches a cache key without lang
        at = _app(lang)
        if at.exception:
            problems.append(f"Weekly briefing ({lang}) raised {at.exception[0].value}")
            continue
        data, label = _download(at)
        if data is None:
            problems.append(f"{lang}: {label}")
            continue
        got.setdefault(lang, []).append(data)
    if not problems:
        want_en = SCENARIOS[sc]
        for d in got["en"]:
            if hashlib.sha256(d).hexdigest() != want_en:
                problems.append("English mode download is not today's English PDF")
        try:
            want_bn = pdf(brief(sc, "bn"), "bn")
        except TypeError as e:
            want_bn = None
            problems.append(f"no lang keyword: {e}")
        if want_bn is not None and got["bn"][0] != want_bn:
            problems.append("Bangla mode download is not briefing_pdf(build(..., lang='bn'), lang='bn')")
    return out("page", problems)


def mode_tests() -> int:
    import shutil
    import tempfile

    problems = []
    path = ROOT / NEW_TEST
    if not path.exists():
        return out("tests", [f"{NEW_TEST} missing"])
    src = path.read_text(encoding="utf-8")
    if re.search(r"pytest\.mark\.(skip|skipif|xfail)|pytest\.(skip|xfail)\(|importorskip", src):
        problems.append(f"{NEW_TEST} skips or xfails")
    py = sys.executable
    co = subprocess.run([py, "-m", "pytest", NEW_TEST, "--co", "-q", "-o", "addopts="], capture_output=True,
                        text=True, cwd=ROOT)
    m = re.search(r"(\d+) tests? collected", co.stdout)
    n = int(m.group(1)) if m else 0
    if n < MIN_NEW_TESTS:
        problems.append(f"{n} tests in {NEW_TEST}, need >= {MIN_NEW_TESTS}")
    run = subprocess.run([py, "-m", "pytest", NEW_TEST, "-q", "-o", "addopts=", "-p", "no:cacheprovider"],
                         capture_output=True, text=True, cwd=ROOT)
    if run.returncode != 0:
        problems.append(f"{NEW_TEST} fails: {run.stdout[-400:]}")
    sabotage = ("\n\nimport reportlab.pdfbase.pdfmetrics as _pm\n_orig_reg = _pm.registerFont\n"
                "def _no_bangla(font):\n    if 'Bengali' in getattr(font, 'fontName', ''):\n"
                "        raise RuntimeError('sabotage')\n    return _orig_reg(font)\n_pm.registerFont = _no_bangla\n")
    tmp = Path(tempfile.mkdtemp(prefix="bnpdf-mut-"))
    try:
        subprocess.run(["git", "worktree", "add", "--detach", "-q", str(tmp / "wt"), "HEAD"], cwd=ROOT, check=True,
                       capture_output=True)
        wt = tmp / "wt"
        for rel in subprocess.run(["git", "ls-files", "-m", "-o", "--exclude-standard"], cwd=ROOT,
                                  capture_output=True, text=True).stdout.split():
            if (ROOT / rel).is_file() and not rel.startswith(".claude/"):
                (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, wt / rel)
        f = wt / "src/moshari/briefing_pdf.py"
        f.write_text(sabotage + f.read_text(encoding="utf-8"), encoding="utf-8")
        mut = subprocess.run([py, "-m", "pytest", NEW_TEST, "-q", "-o", "addopts=", "-x", "-p", "no:cacheprovider"],
                             capture_output=True, text=True, cwd=wt)
        if mut.returncode == 0:
            problems.append(f"{NEW_TEST} still passes when the Bangla font cannot be used")
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(tmp / "wt")], cwd=ROOT, capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)
    return out("tests", problems, f"{n} tests, sabotage caught")


ALLOWED_PATHS = re.compile(r"^(README\.md|requirements\.txt|src/moshari/briefing(_pdf)?\.py|src/moshari/i18n\.py|"
                           r"src/moshari/locales/bn\.json|src/moshari/fonts/(NotoSansBengali-(Regular|Bold)\.ttf|OFL\.txt)|"
                           r"ui/views/briefing\.py|ui/i18n\.py|tests/test_briefing_pdf_bn\.py|"
                           r"\.claude/goals/.*)$")  # goal files themselves are guarded by the pins


def mode_git() -> int:
    problems = []

    def git(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True, cwd=ROOT).stdout

    if BASE.startswith("__"):
        return out("git", ["verifier BASE commit not set"])
    dirty = [l for l in git("status", "--porcelain").splitlines() if not l[3:].startswith(".claude/goals/")]
    if dirty:
        problems.append(f"uncommitted changes: {dirty[:8]}")
    changes = [l.split("\t") for l in git("diff", "--name-status", f"{BASE}..HEAD").splitlines()]
    if not [c for c in changes if not c[-1].startswith(".claude/")]:
        problems.append(f"no work committed since {BASE} (only goal files)")
    for parts in changes:
        status, path = parts[0], parts[-1]
        if not ALLOWED_PATHS.match(path):
            problems.append(f"out of scope: {status} {path}")
        if path.startswith("tests/") and status != "A":
            problems.append(f"existing test changed: {status} {path}")
    req = git("diff", f"{BASE}..HEAD", "--", "requirements.txt")
    added = [l[1:].strip() for l in req.splitlines() if l.startswith("+") and not l.startswith("+++")]
    removed = [l for l in req.splitlines() if l.startswith("-") and not l.startswith("---")]
    if removed or any(not a.startswith("uharfbuzz") for a in added if a):
        problems.append(f"requirements.txt may only gain a uharfbuzz line: +{added} -{removed}")
    for line in git("log", "--format=%an|%ae|%s", f"{BASE}..HEAD").splitlines():
        an, ae, subj = line.split("|", 2)
        if an != "Ananya" or ae != "297095755+sam21-og@users.noreply.github.com":
            problems.append(f"commit author {an} <{ae}>")
        if not subj.startswith("version-onsite-final:"):
            problems.append(f"commit message {subj!r}")
    diff = git("diff", f"{BASE}..HEAD", "--", "src", "ui")
    added_code = [l for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    if any(re.search(r"except\s*(Exception)?\s*:\s*(pass)?\s*$|#\s*noqa|type:\s*ignore", l) for l in added_code):
        problems.append("swallowed errors / silenced checks added")
    if any(re.search(r"requests\.|urllib|https?://", l) for l in added_code):
        problems.append("network code added")
    return out("git", problems, f"{len(changes)} files changed since {BASE}")


def mode_review() -> int:
    dest = ROOT / ".claude" / "goals" / "bangla-pdf-review"
    dest.mkdir(parents=True, exist_ok=True)
    for sc in SCENARIOS:
        name = f"briefing_bn_{sc[0]}_h{sc[1]}.pdf"
        (dest / name).write_bytes(pdf(brief(sc, "bn"), "bn"))
        print(f"wrote {dest.relative_to(ROOT) / name}")
    print("REVIEW: open these PDFs and check that the Bangla letters are joined correctly and read naturally.")
    return 0


MODES = {"fonts": mode_fonts, "en": mode_en, "bn": mode_bn, "page": mode_page, "tests": mode_tests,
         "git": mode_git, "review": mode_review}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        print(f"usage: {sys.argv[0]} {{{'|'.join(MODES)}}}")
        sys.exit(2)
    _prepare()
    sys.exit(MODES[sys.argv[1]]())
