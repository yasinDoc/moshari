# Shared helpers for the bangla-ui attack scripts (sourced, not run).
# mk_i18n: a working minimal i18n layer (core + ui wrapper) reading src/moshari/locales/bn.json.
mk_i18n() {
  mkdir -p src/moshari/locales
  cat > src/moshari/i18n.py <<'PY'
import json, string
from pathlib import Path
_CAT = json.loads((Path(__file__).parent / "locales" / "bn.json").read_text(encoding="utf-8"))
_D = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
MISSING = set()
def digits(x):
    return str(x).translate(_D)
def t(text, lang="en", **kw):
    if lang != "bn":
        return text.format(**kw) if kw else text
    tpl = _CAT.get(text)
    if tpl is None:
        MISSING.add(text)
        tpl = text
    if not kw:
        return tpl
    out = []
    for lit, field, spec, conv in string.Formatter().parse(tpl):
        out.append(lit)
        if field is not None:
            v = kw[field]
            s = format(v, spec or "")
            out.append(digits(s) if isinstance(v, (int, float)) else s)
    return "".join(out)
PY
  cat > ui/i18n.py <<'PY'
import streamlit as st
from moshari import i18n as _c
digits = _c.digits
def lang():
    try:
        return st.session_state.get("lang", "en")
    except Exception:
        return "en"
def t(text, lang=None, **kw):
    return _c.t(text, lang=lang or globals()["lang"](), **kw)
PY
}
# titles_bn: the 11 page titles in Bangla (python dict literal body)
TITLES_PY='{"Overview":"সারসংক্ষেপ","Ward map":"ওয়ার্ড মানচিত্র","Resources":"সম্পদ","Hospital beds":"হাসপাতাল শয্যা","Simulator":"সিমুলেটর","Dispatch":"বার্তা প্রেরণ","Weekly briefing":"সাপ্তাহিক ব্রিফিং","Live outlook":"সরাসরি পূর্বাভাস","Ward forecast":"ওয়ার্ড পূর্বাভাস","Model accuracy":"মডেলের নির্ভুলতা","Data":"তথ্য","{n} wards":"{n}টি ওয়ার্ড"}'
