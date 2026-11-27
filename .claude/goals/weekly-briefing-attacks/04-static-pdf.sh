# attacks: 2
# break: the PDF is drawn once for the demo week and reused for every setting
. .claude/goals/weekly-briefing-attacks/00-lib.inc
ref src/moshari/briefing.py src/moshari/briefing_pdf.py
cat >> src/moshari/briefing_pdf.py <<'PY'
_real_pdf = briefing_pdf
_CACHE = []
def briefing_pdf(b):
    if not _CACHE:
        _CACHE.append(_real_pdf(b))
    return _CACHE[0]
PY
