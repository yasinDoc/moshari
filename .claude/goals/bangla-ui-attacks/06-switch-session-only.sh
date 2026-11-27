# attacks: 3
# break: a sidebar switch that works in the session but ignores ?lang= links and ward links
set -e
. "$(dirname "$0")/00-lib.inc"
mk_i18n
python3 -c "import json; json.dump($TITLES_PY, open('src/moshari/locales/bn.json','w',encoding='utf-8'), ensure_ascii=False)"
python3 - <<'PY'
p = "app.py"; s = open(p, encoding="utf-8").read()
s = s.replace("with st.sidebar:\n", '''with st.sidebar:
    st.segmented_control("ভাষা / Language", ["en", "bn"], key="lang", default="en",
                         format_func={"en": "English", "bn": "বাংলা"}.get)
''', 1)
s = s.replace("st.page_link(page, label=page.title, icon=page.icon)",
              "from ui import i18n as I\n            st.page_link(page, label=I.t(page.title), icon=page.icon)")
open(p, "w", encoding="utf-8").write(s)
PY
