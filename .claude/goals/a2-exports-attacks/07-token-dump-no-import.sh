#!/usr/bin/env bash
# attacks: 1
# break: like 03, but the verifier's token list is pasted into the script (no .claude reference): PDF is a plain list of the brief's strings, no layout
set -e
bash .claude/goals/a2-exports-attacks/03-token-dump-pdf.sh >/dev/null
python - <<'PY'
import re
from pathlib import Path
v = Path(".claude/goals/a2-exports-verify.py").read_text()
fn = v[v.index("def brief_tokens(row)"):v.index("def page_problems(")]
p = Path("scripts/export_dispatch.py"); s = p.read_text()
s = s.replace('spec = importlib.util.spec_from_file_location("v", ROOT / ".claude/goals/a2-exports-verify.py")\n', "")
s = s.replace("V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)\n", "")
s = s.replace("from moshari import dispatch as D\n", "from moshari import dispatch as D\nimport re\n" + fn + "\n"
              "from moshari.data import load_dataset\nfrom moshari.model import ForecastBundle\nfrom moshari.service import ForecastService\n"
              "from moshari.risk import DEFAULT_ALERT_POLICY\nfrom moshari import allocation as A, routing as R, config as C\nimport pandas as pd\n"
              "class _V:\n    pass\nV = _V()\nV.brief_tokens = brief_tokens\n"
              "def _exp(issue, h, st, cr, sel):\n"
              "    svc = ForecastService(load_dataset(), ForecastBundle.load()); _exp.svc = svc\n"
              "    issue = svc.default_issue_date() if issue is None else pd.Timestamp(issue)\n"
              "    fc = svc.forecast_all(issue, h, None, DEFAULT_ALERT_POLICY); al = A.allocate(fc, svc.wards, st, cr)\n"
              "    rows = D.select_rows(D.dispatch_table(al, R.route_overflow(al, R.load_bed_capacity())), sel).to_dict('records')\n"
              "    f = {}\n"
              "    for r in rows:\n"
              "        w = r['ward_id']; f[f'sms/{w}.txt'] = D.sms(r) + '\\n'; f[f'whatsapp/{w}.txt'] = D.whatsapp(r) + '\\n'; f[f'briefs/{w}.html'] = D.brief_html(r)\n"
              "    if rows: f['briefs/all_briefs.html'] = D.briefs_html(rows)\n"
              "    return issue, rows, f\n"
              "V.expected = _exp\n")
p.write_text(s)
PY
rm -rf exports && MOSHARI_OFFLINE=1 python scripts/export_dispatch.py
