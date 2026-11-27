# attacks: 2
# break: drops the shrink-to-fit, so long content can spill; plus forces a page break before Notices
. .claude/goals/weekly-briefing-attacks/00-lib.inc
ref src/moshari/briefing.py src/moshari/briefing_pdf.py
sed -i 's/from reportlab.platypus import KeepInFrame, Paragraph, SimpleDocTemplate/from reportlab.platypus import KeepInFrame, PageBreak, Paragraph, SimpleDocTemplate/; s/    story += \[P("Notices", "Heading2")/    story += [PageBreak(), P("Notices", "Heading2")/; s/doc.build(\[KeepInFrame(doc.width, doc.height - 2, story, mode="shrink")\])/doc.build(story)/' src/moshari/briefing_pdf.py
