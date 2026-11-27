"""Verifier for the bangla-ui goal: an English / Bangla switch for every dashboard page.

Run from the project root:  python .claude/goals/bangla-ui-verify.py <mode>
Modes: catalog | en | bn | switch | tests | git | snapshot | review (prints a random sample)
Each mode prints one "PASS <mode>" or "FAIL <mode>: ..." line (plus details) and exits 0 / 1.

How pages are read: every page is opened in the real app with Streamlit's AppTest, with the
network blocked and MOSHARI_OFFLINE=1, and every user-visible text fragment is collected from
the element tree: HTML / Markdown text nodes (plus aria-label, title, alt), widget labels, help,
placeholders and options, tab and expander labels, metric text, dataframe column names and
string cells, and Plotly titles, axis titles, tick text, trace names, text and hover templates.
`en` compares that text with a snapshot taken on main 0cf943d before any work; `bn` checks that
no English word or Latin digit is left in Bangla mode. Written before the work and pinned:
the executor must not edit it.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path.cwd()
GOALS = ROOT / ".claude" / "goals"
SNAPSHOT = GOALS / "bangla-ui-en-snapshot.json"
SNAPSHOT_SHA = "aea1adf84c2d6be473f0c99ceb124540da68c8287013ce48cc8e57b3fa3129fe"
CATALOG = ROOT / "src" / "moshari" / "locales" / "bn.json"
BASE = "0cf943d"
NEW_TEST = "tests/test_i18n.py"
MIN_NEW_TESTS = 12

PAGES = ["ui/views/ward_net.py", "ui/views/ward_map.py", "ui/views/resources.py", "ui/views/hospital.py",
         "ui/views/simulator.py", "ui/views/dispatch.py", "ui/views/briefing.py", "ui/views/live.py",
         "ui/views/ward_forecast.py", "ui/views/model_check.py", "ui/views/data_source.py"]
TITLES = {"ui/views/ward_net.py": "Overview", "ui/views/ward_map.py": "Ward map",
          "ui/views/resources.py": "Resources", "ui/views/hospital.py": "Hospital beds",
          "ui/views/simulator.py": "Simulator", "ui/views/dispatch.py": "Dispatch",
          "ui/views/briefing.py": "Weekly briefing", "ui/views/live.py": "Live outlook",
          "ui/views/ward_forecast.py": "Ward forecast", "ui/views/model_check.py": "Model accuracy",
          "ui/views/data_source.py": "Data"}
STATES = ("default", "peak")
SWITCH_KEY = "lang"
SWITCH_TEXT = {"ভাষা / Language", "English", "বাংলা"}

# Latin text allowed in Bangla mode: codes and proper names only.
ALLOWED_WORDS = {"Moshari", "DGHS", "NS1", "SMS", "WhatsApp", "PDF", "CSV", "ZIP", "HTML", "A4", "AI",
                 "AUC", "MAE", "ROI", "Open-Meteo", "LightGBM", "TreeSHAP", "geoBoundaries", "°C"}
CODE_RE = re.compile(r"\b(?:DNCC|DSCC|CCC|GCC|NCC)(?:[-_ ]W(?:ard_)?\d{1,3})?\b|\bW\d{1,3}\b")
BENGALI = re.compile(r"[ঀ-৿]")
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
ASCII_DIGIT = re.compile(r"[0-9]")
PLACEHOLDER = re.compile(r"\{[^{}]*\}")
NUMERIC_HOVER = re.compile(r"%\{(?:x|y|z|value|percent\w*|label|r|theta|lat|lon|base|delta)\b|%\{[^}]*:[^}]*\}")

TEXT_FIELDS = {"code_text", "label", "help", "placeholder", "body", "options", "content", "caption", "text", "title",
               "alt", "tooltip", "delta", "value", "default_value"}
SKIP_FIELDS = {"icon", "id", "form_id", "key", "url", "page", "spec", "data", "config", "theme",
               "material_icon", "type", "page_script_hash", "url_path"}
VOID = {"br", "img", "input", "meta", "link", "hr", "path", "circle", "rect", "line", "polygon",
        "polyline", "stop", "use", "ellipse", "source", "wbr", "col", "area", "base", "embed", "param",
        "track"}


# --------------------------------------------------------------------------- helpers
def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def out(mode: str, problems: list[str], detail: str = "") -> int:
    if problems:
        print(f"FAIL {mode}: {len(problems)} problem(s)")
        for p in problems[:40]:
            print("  -", p)
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
        return 1
    print(f"PASS {mode}" + (f" ({detail})" if detail else ""))
    return 0


_DATA_COLS: list[str] = []


def _data_cols() -> list[str]:
    """Column names of the dataset file: identifiers a user must type in an upload, kept in Latin."""
    if not _DATA_COLS:
        import csv

        for f in sorted((ROOT / "data" / "raw").glob("*.csv")):
            with open(f, newline="", encoding="utf-8") as fh:
                _DATA_COLS.extend(next(csv.reader(fh)))
        _DATA_COLS.sort(key=len, reverse=True)
    return _DATA_COLS


def strip_allowed(s: str) -> str:
    for c in _data_cols():
        if "_" in c:
            s = re.sub(r"(?<![A-Za-z_])" + re.escape(c) + r"(?![A-Za-z_])", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = PLACEHOLDER.sub(" ", s)
    s = re.sub(r"%\{[^}]*\}", " ", s)
    s = CODE_RE.sub(" ", s)
    s = s.replace("°C", " ").replace("R²", " ")
    for w in sorted(ALLOWED_WORDS, key=len, reverse=True):
        s = re.sub(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", " ", s)
    return s


def latin_words(s: str) -> list[str]:
    return LATIN_WORD.findall(strip_allowed(s))


def latin_digits(s: str) -> bool:
    return bool(ASCII_DIGIT.search(strip_allowed(s)))


# --------------------------------------------------------------------------- page reading
class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[bool] = []
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        skip = tag in ("style", "script") or "mi" in (a.get("class") or "").split()
        if tag not in VOID:
            self.stack.append(skip)
        if any(self.stack):
            return
        for k in ("aria-label", "title", "alt"):
            if a.get(k):
                self.out.append(a[k].strip())
        if a.get("href"):
            self.hrefs.append(a["href"])

    def handle_startendtag(self, tag, attrs):
        a = dict(attrs)
        for k in ("aria-label", "title", "alt"):
            if a.get(k) and not any(self.stack):
                self.out.append(a[k].strip())

    def handle_endtag(self, tag):
        if tag not in VOID and self.stack:
            self.stack.pop()

    def handle_data(self, d):
        if not any(self.stack) and d.strip():
            self.out.append(d.strip())


def html_text(body: str) -> tuple[list[str], list[str]]:
    p = _Text()
    p.feed(body)
    return p.out, p.hrefs


ISO_RE = re.compile(r"^\d{4}-\d\d-\d\d(?:[T ][\d:.]+)?$")


def plotly_read(spec: dict) -> tuple[list[str], list[str]]:
    """(text fragments, problems that matter only in Bangla mode)."""
    frags: list[str] = []
    issues: list[str] = []

    def add(v):
        if isinstance(v, str):
            if v.strip() and not ISO_RE.match(v.strip()):
                frags.append(v.strip())
        elif isinstance(v, (list, tuple)):
            for x in v:
                add(x)

    def title(o):
        if not isinstance(o, dict):
            return
        t = o.get("title")
        add(t.get("text") if isinstance(t, dict) else t)

    layout = spec.get("layout", {}) or {}
    title(layout)
    if isinstance(layout.get("legend"), dict):
        title(layout["legend"])
    for a in layout.get("annotations", []) or []:
        add(a.get("text"))
    used_axes: dict[str, list] = {}
    for d in spec.get("data", []) or []:
        t = d.get("type", "scatter")
        for k in ("name", "hovertext", "labels"):
            add(d.get(k))
        txt = d.get("text")
        if txt is not None:
            vals = txt if isinstance(txt, (list, tuple)) else [txt]
            flat = []
            for v in vals:
                flat.extend(v if isinstance(v, (list, tuple)) else [v])
            if any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in flat):
                issues.append(f"{t} trace has numeric 'text' (the browser draws Latin digits)")
            add(flat)
        for k in ("hovertemplate", "texttemplate"):
            v = d.get(k)
            vs = v if isinstance(v, list) else [v]
            for s in vs:
                if isinstance(s, str):
                    add(s)
                    if NUMERIC_HOVER.search(s):
                        issues.append(f"{t} trace {k} prints a raw number: {s[:70]!r}")
        templates = " ".join(v if isinstance(v, str) else " ".join(map(str, v)) for v in
                             (d.get("hovertemplate"), d.get("texttemplate")) if v)
        if "customdata" in templates:
            leaves, stack = [], [d.get("customdata")]
            while stack:
                v = stack.pop()
                if isinstance(v, (list, tuple)):
                    stack.extend(v)
                elif isinstance(v, dict):  # binary-encoded numeric array
                    leaves.append(0.0)
                else:
                    leaves.append(v)
            if any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in leaves):
                issues.append(f"{t} trace shows numeric customdata (needs pre-formatted Bangla strings)")
            add([v for v in leaves if isinstance(v, str)])
        if d.get("hoverinfo") not in ("skip", "none") and not d.get("hovertemplate"):
            issues.append(f"{t} trace {d.get('name')!r} has default hover (raw English/Latin numbers)")
        if d.get("textinfo") not in (None, "none"):
            issues.append(f"{t} trace uses textinfo {d.get('textinfo')!r}")
        if t in ("bar", "scatter", "heatmap", "box", "histogram"):
            for ax in ("x", "y"):
                name = (d.get(ax + "axis") or ax).replace(ax, ax + "axis", 1)
                vals = d.get(ax)
                if isinstance(vals, dict):  # binary-encoded numeric array
                    vals = [0.0]
                used_axes.setdefault(name, []).extend(vals if isinstance(vals, list) else [])
                if isinstance(vals, list) and vals and all(isinstance(v, str) and not ISO_RE.match(v)
                                                           for v in vals):
                    add(vals)
        if t == "heatmap" and d.get("showscale", True) is not False:
            cb = d.get("colorbar") or {}
            title(cb)
            if not cb.get("ticktext"):
                issues.append("heatmap colour bar has no Bangla tick text")
            add(cb.get("ticktext"))
        if isinstance(d.get("marker"), dict) and isinstance(d["marker"].get("colorbar"), dict) \
                and d["marker"].get("showscale"):
            cb = d["marker"]["colorbar"]
            title(cb)
            if not cb.get("ticktext"):
                issues.append("marker colour bar has no Bangla tick text")
            add(cb.get("ticktext"))
    for k, v in layout.items():
        if re.match(r"^[xy]axis\d*$", k) and isinstance(v, dict):
            title(v)
            add(v.get("ticktext"))
    for name, vals in used_axes.items():
        ax = layout.get(name, {}) or {}
        if ax.get("visible") is False or ax.get("showticklabels") is False:
            continue
        categorical = bool(vals) and all(isinstance(v, str) and not ISO_RE.match(v) for v in vals)
        if categorical or ax.get("type") == "category":
            continue
        if not (ax.get("tickmode") == "array" and ax.get("ticktext")):
            issues.append(f"{name} draws its own number/date ticks (needs tickvals + Bangla ticktext)")
    return frags, issues


def dataframe_read(p) -> tuple[list[str], list[str]]:
    """A st.dataframe / st.data_editor element: visible column labels, help, string cells."""
    import pyarrow as pa

    frags, issues = [], []
    table = pa.ipc.open_stream(io.BytesIO(p.arrow_data.data)).read_all()
    try:
        config = json.loads(p.columns) if p.columns else {}
    except ValueError:
        config = {}
    meta = (table.schema.metadata or {}).get(b"pandas")
    index_cols: set[str] = set()
    if meta:
        try:
            index_cols = {c for c in json.loads(meta).get("index_columns", []) if isinstance(c, str)}
        except ValueError:
            pass
    index_hidden = bool((config.get("_index") or {}).get("hidden"))
    order = list(p.column_order) or None
    editable = p.editing_mode != 0 and not p.disabled
    for name, col in zip(table.column_names, table.columns):
        cfg = config.get(name) or {}
        if name in index_cols:
            if index_hidden:
                continue
        elif cfg.get("hidden") or (order is not None and name not in order):
            continue
        label = cfg.get("label") or name
        frags.append(str(label))
        if cfg.get("help"):
            frags.append(str(cfg["help"]))
        typ = col.type
        if pa.types.is_string(typ) or pa.types.is_large_string(typ):
            frags += [v.strip() for v in col.to_pylist() if isinstance(v, str) and v.strip()]
        elif (pa.types.is_integer(typ) or pa.types.is_floating(typ) or pa.types.is_decimal(typ)
              or pa.types.is_temporal(typ) or pa.types.is_boolean(typ)):
            if editable and not cfg.get("disabled"):
                continue  # an input the user types into, like st.number_input
            issues.append(f"table column {label!r} is {typ} (the browser draws Latin digits / English)")
    return frags, issues


def _proto_text(p, acc: list[str], depth: int = 0) -> None:
    if depth > 6:
        return
    for f, v in p.ListFields():
        if f.name in SKIP_FIELDS:
            continue
        vals = v if f.is_repeated else [v]
        if f.type == f.TYPE_STRING:
            if f.name in TEXT_FIELDS:
                acc += [s.strip() for s in vals if isinstance(s, str) and s.strip()]
        elif f.type == f.TYPE_MESSAGE:
            for m in vals:
                _proto_text(m, acc, depth + 1)


def _walk(n):
    yield n
    for ch in getattr(n, "children", {}).values():
        yield from _walk(ch)


def _key_of(n) -> str | None:
    k = getattr(n, "key", None)
    if k:
        return k
    pid = getattr(getattr(n, "proto", None), "id", "") or ""
    m = re.search(r"-([^-]+)$", pid) if "$$ID" in pid or "key" in pid else None
    return m.group(1) if m else None


def _signature(pn: str, p) -> str:
    """What an element IS, independent of its language: the Bangla page must have the same."""
    if pn == "PlotlyChart":
        spec = json.loads(p.spec)
        traces = [(d.get("type", "scatter"), d.get("hoverinfo") in ("skip", "none"), d.get("visible", True),
                   len(d["x"]) if isinstance(d.get("x"), list) else None,
                   len(d["y"]) if isinstance(d.get("y"), list) else None) for d in spec.get("data", [])]
        axes = sorted((k, (v or {}).get("visible", True), (v or {}).get("showticklabels", True))
                      for k, v in (spec.get("layout") or {}).items() if re.match(r"^[xy]axis\d*$", k))
        return f"plotly{traces}{axes}"
    if pn == "Dataframe":
        import pyarrow as pa

        t = pa.ipc.open_stream(io.BytesIO(p.arrow_data.data)).read_all()
        try:
            cfg = json.loads(p.columns) if p.columns else {}
        except ValueError:
            cfg = {}
        hidden = sum(1 for v in cfg.values() if isinstance(v, dict) and v.get("hidden"))
        return f"df{t.num_rows}x{t.num_columns}-{hidden}-{len(p.column_order)}-{p.editing_mode}"
    opts = getattr(p, "options", None)
    n_opts = len(opts) if opts is not None and not isinstance(opts, str) else ""
    return f"{pn}{n_opts}"


def read_app(at) -> dict:
    """All text in the current app tree, with the language switch element held apart."""
    frags, issues, hrefs, switch, sig = [], [], [], [], []
    for root in at._tree.children.values():
        for n in _walk(root):
            p = getattr(n, "proto", None)
            if p is None:
                continue
            pn = type(p).__name__
            if getattr(n, "key", None) == SWITCH_KEY:
                acc: list[str] = []
                _proto_text(p, acc)
                switch += acc
                continue
            sig.append(_signature(pn, p))
            if pn == "Html":
                f, h = html_text(p.body)
                frags += f
                hrefs += h
            elif pn == "Markdown":
                f, h = html_text(re.sub(r":material/[a-z_]+:", "", p.body))
                frags += f
                hrefs += h
            elif pn == "PlotlyChart":
                f, i = plotly_read(json.loads(p.spec))
                frags += f
                issues += i
            elif pn == "Dataframe":
                f, i = dataframe_read(p)
                frags += f
                issues += i
            elif pn == "Exception":
                continue
            else:
                acc = []
                _proto_text(p, acc)
                frags += acc
    return {"frags": frags, "issues": issues, "hrefs": hrefs, "switch": switch, "sig": sig,
            "exceptions": [str(e.value)[:300] for e in at.exception]}


class _Net:
    attempts: list[str] = []


def _block_network() -> None:
    real_connect = socket.socket.connect

    def guard(host):
        if str(host) not in {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}:
            _Net.attempts.append(str(host))
            raise OSError(101, f"Network is unreachable ({host})")

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            guard(address[0] if isinstance(address, tuple) else address)
        return real_connect(self, address)

    real_gai = socket.getaddrinfo

    def gai(host, *a, **k):
        guard(host or "")
        return real_gai(host, *a, **k)

    socket.socket.connect = connect
    socket.getaddrinfo = gai


_PREPARED = False


def _prepare() -> None:
    global _PREPARED
    if _PREPARED:
        return
    os.environ["MOSHARI_OFFLINE"] = "1"
    for v in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(v, None)
    for p in (str(ROOT / "src"), str(ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)
    import logging

    logging.getLogger("streamlit").setLevel(logging.ERROR)
    from moshari import live

    live.CACHE_DIR = Path(tempfile.mkdtemp(prefix="bangla-verify-")) / "open_meteo"
    _block_network()
    _PREPARED = True


def render(page: str, state: str, lang: str | None, via_query: bool = False) -> dict:
    _prepare()
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=240)
    if lang and via_query:
        at.query_params[SWITCH_KEY] = lang
    elif lang:
        at.session_state[SWITCH_KEY] = lang
    at.run()
    if state == "peak":
        at.button(key="jump_Peak").click()
        at.run()
    at.switch_page(page)
    at.run()
    res = read_app(at)
    res["session_lang"] = at.session_state[SWITCH_KEY] if SWITCH_KEY in at.session_state else None
    res["disp_lang"] = at.session_state["disp_lang"] if "disp_lang" in at.session_state else None
    return res


def _seed_weather() -> None:
    """Live outlook with a saved weather copy (fixed dates, so it is reproducible)."""
    import pandas as pd
    from moshari import live

    start = pd.Timestamp.today().normalize() - pd.Timedelta(days=92)
    days = pd.date_range(start, periods=106, freq="D").strftime("%Y-%m-%d").tolist()
    block = {"daily": {"time": days, "precipitation_sum": [12.0] * 106, "temperature_2m_mean": [29.5] * 106,
                       "temperature_2m_max": [33.0] * 106, "temperature_2m_min": [26.0] * 106,
                       "relative_humidity_2m_mean": [82.0] * 106}}
    payload = json.dumps([block] * len(live.CITY_COORDS)).encode()
    live.fetch_daily(opener=lambda url, timeout: payload, offline=False)


# --------------------------------------------------------------------------- modes
def load_catalog() -> tuple[dict | None, list[str]]:
    if not CATALOG.exists():
        return None, [f"{CATALOG.relative_to(ROOT)} does not exist"]
    try:
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    except ValueError as e:
        return None, [f"catalog is not valid JSON: {e}"]
    if not isinstance(cat, dict) or not cat:
        return None, ["catalog must be a non-empty JSON object {english: bangla}"]
    return cat, []


def mode_catalog() -> int:
    cat, problems = load_catalog()
    if cat is None:
        return out("catalog", problems)
    for en, bn in cat.items():
        if not isinstance(en, str) or not isinstance(bn, str) or not bn.strip():
            problems.append(f"empty or non-text entry for {en!r}")
            continue
        if not BENGALI.search(bn):
            problems.append(f"no Bangla letters in the translation of {en!r}: {bn!r}")
        if bn.strip() == en.strip():
            problems.append(f"translation equals the English: {en!r}")
        if set(PLACEHOLDER.findall(en)) != set(PLACEHOLDER.findall(bn)):
            problems.append(f"placeholders differ for {en!r}: {sorted(set(PLACEHOLDER.findall(en)))} vs "
                            f"{sorted(set(PLACEHOLDER.findall(bn)))}")
        if latin_words(bn):
            problems.append(f"English words left in {bn!r}: {latin_words(bn)[:5]}")
        if latin_digits(bn):
            problems.append(f"Latin digits in {bn!r}")
        core_en = len(PLACEHOLDER.sub("", en).strip())
        core_bn = len(PLACEHOLDER.sub("", bn).strip())
        if core_en >= 12 and not (0.25 <= core_bn / core_en <= 4.0):
            problems.append(f"length ratio {core_bn / core_en:.2f} out of range for {en[:50]!r}")
    # glossary: the team's approved words (src/moshari/dispatch_bn.py) and standard terms.
    exact = {"Low": "নিম্ন", "Medium": "মাঝারি", "High": "উচ্চ", "Critical": "সংকটজনক",
             "Chattogram City Corporation": "চট্টগ্রাম সিটি কর্পোরেশন",
             "Dhaka North City Corporation": "ঢাকা উত্তর সিটি কর্পোরেশন",
             "Dhaka South City Corporation": "ঢাকা দক্ষিণ সিটি কর্পোরেশন",
             "Gazipur City Corporation": "গাজীপুর সিটি কর্পোরেশন",
             "Narayanganj City Corporation": "নারায়ণগঞ্জ সিটি কর্পোরেশন"}
    for en, bn in exact.items():
        if en in cat and cat[en].strip() != bn:
            problems.append(f"glossary: {en!r} must be {bn!r}, is {cat[en]!r}")
    terms = {"ward": "ওয়ার্ড", "dengue": "ডেঙ্গু", "saline": "স্যালাইন", "forecast": "পূর্বাভাস", "crew": "দল"}
    for word, bn_word in terms.items():
        rx = re.compile(r"\b" + word + r"(s|ed|ing)?\b", re.I)
        hits = [k for k in cat if rx.search(PLACEHOLDER.sub(" ", k))]
        good = [k for k in hits if bn_word in cat[k]]
        if len(hits) >= 3 and len(good) < 0.9 * len(hits):
            bad = [k for k in hits if bn_word not in cat[k]][:4]
            problems.append(f"glossary: only {len(good)}/{len(hits)} entries with {word!r} use {bn_word!r}; "
                            f"e.g. {bad}")
    distinct = len(set(cat.values()))
    if distinct < 0.8 * len(cat):
        problems.append(f"only {distinct} distinct translations for {len(cat)} entries")
    # the i18n module itself
    _prepare()
    try:
        from ui import i18n
    except Exception as e:  # noqa: BLE001 - report any import failure
        return out("catalog", problems + [f"cannot import ui.i18n: {e!r}"])
    probe = next((k for k, v in cat.items() if not PLACEHOLDER.search(k)), None)
    if probe is not None:
        if i18n.t(probe, lang="en") != probe:
            problems.append(f"t({probe!r}, lang='en') does not return the English text")
        if i18n.t(probe, lang="bn") != cat[probe]:
            problems.append(f"t({probe!r}, lang='bn') does not return the catalog entry")
    if i18n.digits("2025-06-23 1.03") != "২০২৫-০৬-২৩ ১.০৩":
        problems.append(f"digits() wrong: {i18n.digits('2025-06-23 1.03')!r}")
    fmt_key = next((k for k in cat if PLACEHOLDER.findall(k) == ["{n}"]), None)
    if fmt_key is not None:
        got = i18n.t(fmt_key, lang="bn", n=1234)
        if "১২৩৪" not in got or "1234" in got:
            problems.append(f"t({fmt_key!r}, lang='bn', n=1234) does not print Bangla digits: {got!r}")
        got_en = i18n.t(fmt_key, lang="en", n=1234)
        if "1234" not in got_en:
            problems.append(f"t({fmt_key!r}, lang='en', n=1234) lost the number: {got_en!r}")
    else:
        problems.append("catalog has no entry whose only placeholder is {n}")
    for t_en in TITLES.values():
        if t_en not in cat:
            problems.append(f"page title {t_en!r} missing from catalog")
    return out("catalog", problems, f"{len(cat)} entries, {distinct} distinct")


def _clean_en(frags: list[str]) -> list[str]:
    return list(frags)  # the switch itself is held apart by its key in read_app()


def mode_snapshot() -> int:
    if SNAPSHOT.exists():
        print("FAIL snapshot: already exists; it is pinned and must never be regenerated")
        return 1
    snap = {}
    for page in PAGES:
        for state in STATES:
            r = render(page, state, None)
            if r["exceptions"]:
                print(f"FAIL snapshot: {page} {state} raised {r['exceptions']}")
                return 1
            snap[f"{page}|{state}"] = r["frags"]
    SNAPSHOT.write_text(json.dumps(snap, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"PASS snapshot ({len(snap)} page-states) sha256 {sha256_file(SNAPSHOT)}")
    return 0


def _load_snapshot(problems: list[str]) -> dict | None:
    if not SNAPSHOT.exists():
        problems.append("English snapshot missing")
        return None
    if SNAPSHOT_SHA != "__SNAPSHOT_SHA__" and sha256_file(SNAPSHOT) != SNAPSHOT_SHA:
        problems.append("English snapshot was modified")
        return None
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def mode_en() -> int:
    problems: list[str] = []
    snap = _load_snapshot(problems)
    if snap is None:
        return out("en", problems)
    n = 0
    for page in PAGES:
        for state in STATES:
            for lang in (None, "en"):
                r = render(page, state, lang)
                n += 1
                if r["exceptions"]:
                    problems.append(f"{page} {state} lang={lang}: exception {r['exceptions'][0]}")
                    continue
                got, want = _clean_en(r["frags"]), snap[f"{page}|{state}"]
                if got != want:
                    import difflib

                    diff = [d for d in difflib.unified_diff(want, got, lineterm="", n=0)
                            if d[:1] in "+-" and d[:3] not in ("+++", "---")]
                    problems.append(f"{page} {state} lang={lang}: English text changed: {diff[:6]}")
    if _Net.attempts:
        problems.append(f"network attempted: {sorted(set(_Net.attempts))}")
    return out("en", problems, f"{n} renders identical to the snapshot")


def _bn_checks(label: str, r: dict, en_frags: list[str], cat: dict, problems: list[str],
               en_sig: list[str] | None = None) -> None:
    if r["exceptions"]:
        problems.append(f"{label}: exception {r['exceptions'][0]}")
        return
    if en_sig is not None and r["sig"] != en_sig:
        import difflib

        diff = [d for d in difflib.unified_diff(en_sig, r["sig"], lineterm="", n=0)
                if d[:1] in "+-" and d[:3] not in ("+++", "---")]
        problems.append(f"{label}: Bangla page is built differently from the English one "
                        f"(elements, table sizes, chart traces/hover/axes): {[d[:90] for d in diff[:4]]}")
    words, digit_frags = set(), []
    for f in r["frags"]:
        if f == "English":  # a language's own name, as on Dispatch's notice-language picker
            continue
        words.update(latin_words(f))
        if latin_digits(f):
            digit_frags.append(f)
    if words:
        problems.append(f"{label}: English words left: {sorted(words)[:15]}")
    if digit_frags:
        problems.append(f"{label}: Latin digits in: {[d[:60] for d in digit_frags[:6]]}")
    for i in sorted(set(r["issues"]))[:8]:
        problems.append(f"{label}: {i}")
    en_letters = sum(len(re.findall(r"[A-Za-z]", f)) for f in en_frags)
    bn_letters = sum(len(BENGALI.findall(f)) for f in r["frags"])
    if bn_letters < 0.5 * en_letters:
        problems.append(f"{label}: too little Bangla text ({bn_letters} Bangla letters vs {en_letters} "
                        f"English letters in English mode)")
    en_text_frags = sum(1 for f in en_frags if re.search(r"[A-Za-z]{2}", f))
    bn_text_frags = sum(1 for f in r["frags"] if BENGALI.search(f))
    if bn_text_frags < 0.7 * en_text_frags:
        problems.append(f"{label}: {bn_text_frags} Bangla fragments vs {en_text_frags} English ones")
    joined = "\n".join(r["frags"])
    page = label.split()[0]
    if cat.get(TITLES.get(page, ""), "\0") not in joined:
        problems.append(f"{label}: Bangla page title {cat.get(TITLES.get(page, ''))!r} not shown")
    missing_nav = [t for t in TITLES.values() if cat.get(t, "\0") not in r["frags"]]
    if missing_nav:
        problems.append(f"{label}: sidebar links not in Bangla: {missing_nav}")


def mode_bn() -> int:
    problems: list[str] = []
    cat, cp = load_catalog()
    snap = _load_snapshot(problems)
    if cat is None or snap is None:
        return out("bn", problems + cp)
    n = 0
    for page in PAGES:
        for state in STATES:
            r = render(page, state, "bn")
            r_en = render(page, state, "en")
            n += 1
            _bn_checks(f"{page} {state}", r, snap[f"{page}|{state}"], cat, problems, r_en["sig"])
    _seed_weather()
    import streamlit as st

    st.cache_data.clear()
    r_en = render("ui/views/live.py", "default", "en")
    r_bn = render("ui/views/live.py", "default", "bn")
    n += 1
    _bn_checks("ui/views/live.py saved-weather", r_bn, _clean_en(r_en["frags"]), cat, problems, r_en["sig"])
    if _Net.attempts:
        problems.append(f"network attempted: {sorted(set(_Net.attempts))}")
    return out("bn", problems, f"{n} Bangla renders, no English word or Latin digit left")


def mode_switch() -> int:
    problems: list[str] = []
    cat, cp = load_catalog()
    if cat is None:
        return out("switch", cp)
    r = render("ui/views/ward_net.py", "default", None)
    if r["session_lang"] != "en":
        problems.append(f"default language is {r['session_lang']!r}, expected 'en'")
    if not SWITCH_TEXT <= set(r["switch"]):
        problems.append(f"switch (key {SWITCH_KEY!r}) must show {sorted(SWITCH_TEXT)}; shows {r['switch']}")
    rq = render("ui/views/resources.py", "default", "bn", via_query=True)
    if rq["session_lang"] != "bn" or cat["Resources"] not in "\n".join(rq["frags"]):
        problems.append("?lang=bn in the link does not open the app in Bangla")
    rb = render("ui/views/ward_net.py", "default", "bn")
    tiles = [h for h in rb["hrefs"] if "ward_forecast?" in h]
    if not tiles:
        problems.append("no ward tile links found on Overview in Bangla")
    elif not all("lang=bn" in h for h in tiles):
        problems.append(f"ward tile links drop the language: {tiles[0]}")
    re_ = render("ui/views/ward_net.py", "default", "en")
    if any("lang=" in h for h in re_["hrefs"] if "ward_forecast?" in h):
        problems.append("English ward links changed (they must not carry lang=)")
    rd = render("ui/views/dispatch.py", "default", "bn")
    if rd["disp_lang"] != "bn":
        problems.append(f"Dispatch notice language starts on {rd['disp_lang']!r} in Bangla mode, expected 'bn'")
    rde = render("ui/views/dispatch.py", "default", None)
    if rde["disp_lang"] != "en":
        problems.append(f"Dispatch notice language starts on {rde['disp_lang']!r} in English mode")
    # the choice survives moving between pages
    _prepare()
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=240)
    at.run()
    at.session_state[SWITCH_KEY] = "bn"
    at.run()
    for page in ("ui/views/hospital.py", "ui/views/model_check.py"):
        at.switch_page(page)
        at.run()
        txt = "\n".join(read_app(at)["frags"])
        if at.session_state[SWITCH_KEY] != "bn" or cat[TITLES[page]] not in txt:
            problems.append(f"language lost after moving to {page}")
    css = "\n".join(e.proto.body for e in at.get("html") if "font-family" in e.proto.body)
    if "Hind Siliguri" not in css or not re.search(r"Hind\+Siliguri:wght@[^'\")]*400", css):
        problems.append("Bangla mode does not load Hind Siliguri at weight 400 for body text")
    return out("switch", problems)


def mode_tests() -> int:
    problems: list[str] = []
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
        problems.append(f"{n} tests collected in {NEW_TEST}, need >= {MIN_NEW_TESTS}")
    run = subprocess.run([py, "-m", "pytest", NEW_TEST, "-q", "-o", "addopts=", "-rs", "-p", "no:cacheprovider"],
                         capture_output=True, text=True, cwd=ROOT)
    if run.returncode != 0:
        problems.append(f"{NEW_TEST} fails: {run.stdout[-400:]}")
    # the tests must notice a broken translation: run them on copies with sabotage
    for name, sabotage in (("empty catalog", "catalog"), ("t() ignores Bangla", "t")):
        tmp = Path(tempfile.mkdtemp(prefix="bangla-mut-"))
        try:
            subprocess.run(["git", "worktree", "add", "--detach", "-q", str(tmp / "wt"), "HEAD"], cwd=ROOT,
                           check=True, capture_output=True)
            wt = tmp / "wt"
            for rel in subprocess.run(["git", "ls-files", "-m", "-o", "--exclude-standard"], cwd=ROOT,
                                      capture_output=True, text=True).stdout.split():
                if (ROOT / rel).is_file() and not rel.startswith(".claude/"):
                    (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / rel, wt / rel)
            if sabotage == "catalog":
                (wt / "src/moshari/locales/bn.json").write_text("{}", encoding="utf-8")
            else:
                f = wt / "ui/i18n.py"
                f.write_text(f.read_text(encoding="utf-8") + "\n\n_orig_t = t\n\ndef t(text, lang=None, **kw):\n"
                             "    return _orig_t(text, lang='en', **kw)\n", encoding="utf-8")
            mut = subprocess.run([py, "-m", "pytest", NEW_TEST, "-q", "-o", "addopts=", "-x",
                                  "-p", "no:cacheprovider"], capture_output=True, text=True, cwd=wt)
            if mut.returncode == 0:
                problems.append(f"{NEW_TEST} still passes with sabotage: {name}")
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(tmp / "wt")], cwd=ROOT,
                           capture_output=True)
            shutil.rmtree(tmp, ignore_errors=True)
    return out("tests", problems, f"{n} tests, both sabotages caught")


ALLOWED_PATHS = re.compile(r"^(app\.py|README\.md|ui/.*|src/moshari/.*\.py|src/moshari/locales/bn\.json|tests/test_i18n[\w]*\.py|"
                           r"\.claude/goals/.*)$")  # goal files themselves are guarded by the pins


def mode_git() -> int:
    problems: list[str] = []

    def git(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True, cwd=ROOT).stdout

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
    for line in git("log", "--format=%an|%ae|%s", f"{BASE}..HEAD").splitlines():
        an, ae, subj = line.split("|", 2)
        if an != "Ananya" or ae != "297095755+sam21-og@users.noreply.github.com":
            problems.append(f"commit author {an} <{ae}>")
        if not subj.startswith("version-onsite-final:"):
            problems.append(f"commit message {subj!r}")
    diff = git("diff", f"{BASE}..HEAD", "--", "ui", "src", "app.py")
    added = [l for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    bad = [l for l in added if re.search(r"except\s*(Exception)?\s*:\s*(pass)?\s*$|#\s*noqa|type:\s*ignore", l)]
    if bad:
        problems.append(f"swallowed errors / silenced checks added: {bad[:4]}")
    if any(re.search(r"requests\.|urllib|http[s]?://(?!fonts\.googleapis)", l) for l in added):
        problems.append("network code added")
    return out("git", problems, f"{len(changes)} files changed since {BASE}")


def mode_review() -> int:
    """Print 40 random catalog entries (English => Bangla) for a Bangla reader. Not a check."""
    import random

    cat, problems = load_catalog()
    if cat is None:
        return out("review", problems)
    keys = random.sample(sorted(cat), min(40, len(cat)))
    print(f"REVIEW: {len(keys)} random entries of {len(cat)} in {CATALOG.relative_to(ROOT)}")
    for k in keys:
        print(f"  EN: {k}\n  BN: {cat[k]}\n")
    return 0


MODES = {"review": mode_review, "catalog": mode_catalog, "en": mode_en, "bn": mode_bn, "switch": mode_switch, "tests": mode_tests,
         "git": mode_git, "snapshot": mode_snapshot}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        print(f"usage: {sys.argv[0]} {{{'|'.join(MODES)}}}")
        sys.exit(2)
    sys.exit(MODES[sys.argv[1]]())
