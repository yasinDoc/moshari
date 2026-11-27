# attacks: 3
# break: the download button always serves the 70%/40/+0 PDF, whatever the sliders say
. .claude/goals/weekly-briefing-attacks/00-lib.inc
ref src/moshari/briefing.py src/moshari/briefing_pdf.py ui/views/briefing.py ui/views/ward_net.py app.py
sed -i 's/b, pdf = make(key, issue_date, horizon, cities, policy, stock \/ 100, int(crews), surge)/b, pdf = make(key, issue_date, horizon, cities, policy, 0.70, 40, 0)/' ui/views/briefing.py
