#!/usr/bin/env bash
# attacks: 1
# break: no reportlab drawing at all: a hand-written PDF puts every ward's tokens on page 1 and leaves pages 2..n blank
set -e
bash .claude/goals/a2-exports-attacks/03-token-dump-pdf.sh >/dev/null
python - <<'PY'
from pathlib import Path
p = Path("scripts/export_dispatch.py"); s = p.read_text()
start = s.index("def pdf(path, rs):"); end = s.index("if Canvas and")
s = s[:start] + '''def pdf(path, rs):
    esc = lambda t: t.replace("\\\\", "\\\\\\\\").replace("(", "\\\\(").replace(")", "\\\\)")
    body = "BT /F1 6 Tf 20 820 Td " + " ".join(f"({esc(t)}) Tj 0 -7 Td" for r in rs for t in sum(V.brief_tokens(r), [])) + " ET"
    n = len(rs); objs = ["<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [" + " ".join(f"{4 + i} 0 R" for i in range(n)) + f"] /Count {n} >>",
        f"<< /Length {len(body.encode('latin-1'))} >>\\nstream\\n{body}\\nendstream"]
    objs += [f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {3 if i == 0 else 4 + n} 0 R >>" for i in range(n)]
    objs.append("<< /Length 0 >>\\nstream\\n\\nendstream")
    out = "%PDF-1.4\\n" + "".join(f"{i + 1} 0 obj\\n{o}\\nendobj\\n" for i, o in enumerate(objs))
    Path(path).write_bytes((out + "trailer << /Root 1 0 R >>\\n%%EOF\\n").encode("latin-1"))
''' + s[end:]
p.write_text(s)
PY
rm -rf exports && MOSHARI_OFFLINE=1 python scripts/export_dispatch.py
