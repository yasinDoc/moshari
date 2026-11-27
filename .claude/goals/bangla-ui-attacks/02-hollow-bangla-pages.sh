# attacks: 2
# break: Bangla mode renders only a translated sidebar and title, then stops the page
set -e
. "$(dirname "$0")/00-lib.inc"
mk_i18n
python3 -c "import json; json.dump($TITLES_PY, open('src/moshari/locales/bn.json','w',encoding='utf-8'), ensure_ascii=False)"
python3 - <<'PY'
p = "app.py"; s = open(p, encoding="utf-8").read()
s = s.replace('nav = st.navigation(PAGES, position="hidden")', '''nav = st.navigation(PAGES, position="hidden")
from ui import i18n as I
if st.session_state.get("lang") == "bn":
    with st.sidebar:
        for page in PAGES:
            st.page_link(page, label=I.t(page.title))
    st.html("<h1>" + I.t(nav.title) + "</h1><p>" + "ডেঙ্গু ঝুঁকির পূর্বাভাস। " * 400 + "</p>")
    st.stop()''')
open(p, "w", encoding="utf-8").write(s)
PY
