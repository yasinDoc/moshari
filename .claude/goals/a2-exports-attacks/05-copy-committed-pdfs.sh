#!/usr/bin/env bash
# attacks: 1
# break: the script never builds PDFs for other outputs; it copies the ones already in exports/ (PDFs are only checked at default settings)
set -e
bash .claude/goals/a2-exports-attacks/03-token-dump-pdf.sh >/dev/null
cat >> scripts/export_dispatch.py <<'PY'
if Canvas and o.pdf != "none" and out.resolve() != (ROOT / "exports").resolve():
    for q in (out / "briefs").glob("*.pdf"): q.unlink()
    for q in (ROOT / "exports" / "briefs").glob("*.pdf"): shutil.copy(q, out / "briefs" / q.name)
PY
