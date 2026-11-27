# attacks: 1
# break: fake Bangla - every English text letter-by-letter transliterated into Bengali script
set -e
. "$(dirname "$0")/00-lib.inc"
mk_i18n
python3 - <<'PY'
import json, re
snap = json.load(open(".claude/goals/bangla-ui-en-snapshot.json", encoding="utf-8"))
L = dict(zip("abcdefghijklmnopqrstuvwxyz", "অবকদএফগহইজকলমনওপকরসতউভওক্সয়জ"))
def tr(s):
    s = re.sub(r"[A-Za-z]", lambda m: L[m.group().lower()], s)
    return s.translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))
cat = {}
for frags in snap.values():
    for f in frags:
        if re.search(r"[A-Za-z]{2}", f) and "{" not in f:
            cat[f] = tr(f)
cat["{n} wards"] = "{n} " + tr("wards")
json.dump(cat, open("src/moshari/locales/bn.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
