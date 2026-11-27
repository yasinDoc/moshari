# attacks: 1
# break: the effect table (cases prevented) ignores the city filter
. .claude/goals/weekly-briefing-attacks/00-lib.inc
ref src/moshari/briefing.py
sed -i 's/table = S.build_effect_table(svc, issue, cities=list(cities) or None)/table = S.build_effect_table(svc, issue)/' src/moshari/briefing.py
