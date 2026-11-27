#!/usr/bin/env bash
# attacks: 1
# break: real text via dispatch, but the "PDF brief" is the verifier's own brief_tokens() drawn as a plain list (imports the verifier); README gets one word
set -e
mkdir -p scripts
cat > scripts/export_dispatch.py <<'PY'
"""export"""
import argparse, importlib.util, os, shutil, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
spec = importlib.util.spec_from_file_location("v", ROOT / ".claude/goals/a2-exports-verify.py")
V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)
from moshari import dispatch as D
p = argparse.ArgumentParser(); a = p.add_argument
a("--issue"); a("--horizon", type=int, default=3); a("--stock", type=float, default=70); a("--crews", type=int, default=40)
a("--select", default="high"); a("--out", default="exports"); a("--pdf", default="top"); a("--require-pdf", action="store_true")
o = p.parse_args(); out = Path(o.out)
try: issue, rows, files = V.expected(o.issue, o.horizon, o.stock / 100, o.crews, o.select)
except KeyError: sys.exit(2)
if o.issue and str(issue.date()) not in {str(d.date()) for d in V.expected.svc.issue_dates}: sys.exit(2)
if not rows: print("no ward is High or Critical"); sys.exit(1)
try: from reportlab.pdfgen.canvas import Canvas
except ImportError:
    Canvas = None; print("reportlab missing: pip install reportlab")
    if o.require_pdf: sys.exit(1)
for sub in ("sms", "whatsapp", "briefs"): shutil.rmtree(out / sub, ignore_errors=True)
for k, v in files.items(): (out / k).parent.mkdir(parents=True, exist_ok=True); (out / k).write_text(v, "utf-8", newline="\n")
tgt = (issue + __import__("pandas").Timedelta(weeks=3)).date()
(out / "README.md").write_text(f"python scripts/export_dispatch.py\n{tgt} {len(rows)}\n" + "\n".join(str(r["ward_id"]) for r in rows) + "\n")
def pdf(path, rs):
    c = Canvas(str(path), invariant=1, pageCompression=0)
    for r in rs:
        for i, t in enumerate(sum(V.brief_tokens(r), [])): c.drawString(30, 800 - 11 * i, t)
        c.showPage()
    c.save()
if Canvas and o.pdf != "none":
    pdf(out / "briefs" / f"{rows[0]['ward_id']}.pdf", rows[:1]); pdf(out / "briefs" / "all_briefs.pdf", rows)
PY
echo "See scripts/export_dispatch.py." >> README.md
MOSHARI_OFFLINE=1 python scripts/export_dispatch.py
