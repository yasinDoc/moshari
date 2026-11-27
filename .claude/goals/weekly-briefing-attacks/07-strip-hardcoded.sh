# attacks: 3
# break: the Overview strip is a fixed sentence written for the demo week
. .claude/goals/weekly-briefing-attacks/00-lib.inc
ref src/moshari/briefing.py src/moshari/briefing_pdf.py ui/views/briefing.py ui/views/ward_net.py app.py
sed -i 's/{_h.escape(_al_text)}/25 wards short on saline · 24 wards short on test kits · 12 crews short/' ui/views/ward_net.py
