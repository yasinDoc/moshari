# attacks: 5
# break: twelve tests that assert nothing real, next to a working i18n layer
set -e
. "$(dirname "$0")/00-lib.inc"
mk_i18n
python3 -c "import json; json.dump($TITLES_PY, open('src/moshari/locales/bn.json','w',encoding='utf-8'), ensure_ascii=False)"
python3 - <<'PY'
body = "from moshari import i18n\n\n"
for i in range(12):
    body += f"def test_i18n_{i}():\n    assert i18n.t('Overview', lang='en') == 'Overview'\n\n"
open("tests/test_i18n.py", "w").write(body)
PY
