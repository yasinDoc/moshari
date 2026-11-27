# attacks: 1
# break: routes the scarce allocated beds (Dispatch way) instead of required beds (Hospital way), ignores surge
. .claude/goals/weekly-briefing-attacks/00-lib.inc
ref src/moshari/briefing.py
sed -i 's/    rr = beds_routing(svc, fc, surge_pct)/    rr = R.route_overflow(alloc, R.load_bed_capacity())/' src/moshari/briefing.py
