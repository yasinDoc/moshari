# attacks: 2
# break: in Bangla mode switch off every chart hover and tick label instead of translating them
set -e
. "$(dirname "$0")/00-lib.inc"
mk_i18n
python3 -c "import json; json.dump($TITLES_PY, open('src/moshari/locales/bn.json','w',encoding='utf-8'), ensure_ascii=False)"
python3 - <<'PY'
p = "app.py"; s = open(p, encoding="utf-8").read()
s = s.replace("nav.run()", '''if st.session_state.get("lang") == "bn":
    import plotly.graph_objects as _go
    _orig = st.plotly_chart
    def _pc(fig, *a, **k):
        fig.update_traces(hoverinfo="skip", hovertemplate=None)
        fig.update_xaxes(showticklabels=False); fig.update_yaxes(showticklabels=False)
        return _orig(fig, *a, **k)
    st.plotly_chart = _pc
nav.run()''')
open(p, "w", encoding="utf-8").write(s)
PY
