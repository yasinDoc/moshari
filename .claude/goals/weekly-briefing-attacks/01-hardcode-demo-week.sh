# attacks: 1
# break: build() returns the demo week's numbers whatever the settings
. .claude/goals/weekly-briefing-attacks/00-lib.inc
ref src/moshari/briefing.py
cat >> src/moshari/briefing.py <<'PY'
_real_build = build
_DEMO = {}
def build(svc, issue_date, horizon, cities=(), policy=DEFAULT_ALERT_POLICY, stock_pct=0.70, crews=40, surge_pct=0):
    if not _DEMO:
        _DEMO.update(_real_build(svc, pd.Timestamp("2025-06-02"), 3))
    return dict(_DEMO)
PY
