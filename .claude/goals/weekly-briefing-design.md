# Design: weekly-briefing

Two features for the city health officer, built on the existing engines with no engine changes:
(1) a **Weekly briefing** page whose one button downloads a one-page A4 PDF that turns all five
modules into one decision; (2) a **supply alert strip** on the Overview page.

## Approach
Chosen: a small pure-logic module (`moshari.briefing`) computes every number and sentence once; a
reportlab module draws the PDF from that dict (same pattern as `dispatch_pdf.py`: lazy import,
`invariant=1`, `pageCompression=0`, built-in Helvetica, offline); the Streamlit page and the
Overview strip only display what `moshari.briefing` returns. One source of truth, testable without
Streamlit, and the PDF and page cannot drift apart.
Rejected: printable HTML only - two clicks to a PDF, weaker for the video ending.
Rejected: PDF with HTML fallback - a third more code and tests for a case (reportlab missing) that
adding reportlab to requirements.txt removes.
Rejected: computing the numbers inside the page files - untestable without AppTest, and the
Overview strip and briefing would duplicate logic.

## Components
- NEW `src/moshari/briefing.py` (no Streamlit import, no network):
  - `plural(n, word) -> str`: `"1 ward"`, `"2 wards"`, `"0 wards"` (adds "s" when n != 1).
  - `OVERVIEW_STOCK = 0.70`, `OVERVIEW_CREWS = 40`, `OVERVIEW_SURGE = 0` (the defaults of the
    Resources and Hospital pages).
  - `beds_routing(svc, fc, surge_pct=0)`: exactly the Hospital page:
    `R.route_overflow(A.allocate(fc, svc.wards), R.with_surge(R.load_bed_capacity(), surge_pct))`.
  - `supply_alerts(alloc, ward_summary) -> dict` with int keys
    `saline_wards` (wards with saline_bags_allocated < saline_bags_needed), `kits_wards` (same
    for diagnostic kits), `crews_short` (sum of crews_needed - crews_assigned, floored at 0),
    `out_of_beds_wards` (ward_summary rows with net_deficit > 0).
  - `alert_text(alerts) -> str`: the non-zero parts, in this order, joined by `" · "`:
    `plural(saline_wards,"ward") + " short on saline"`, `plural(kits_wards,"ward") + " short on test kits"`,
    `plural(crews_short,"crew") + " short"`, `plural(out_of_beds_wards,"ward") + " out of beds"`.
    All zero: `"All wards supplied"`.
  - `build(svc, issue_date, horizon, cities=(), policy=DEFAULT_ALERT_POLICY, stock_pct=0.70,
    crews=40, surge_pct=0) -> dict` (keys and values in Data flow).
- NEW `src/moshari/briefing_pdf.py`: `briefing_pdf(brief: dict) -> bytes`. reportlab imported
  inside the function. One A4 page always (shrink, never a second page); deterministic bytes.
- NEW `ui/views/briefing.py`: page "Weekly briefing". Controls (keys fixed, the verifier sets them): `st.slider` `brief_stock` (30-100,
  step 5, default 70, percent), `st.number_input` `brief_crews` (0-300, step 5, default 40),
  `st.slider` `brief_surge` (0-100, step 10, default 0, percent). The PDF follows the controls. Shows the decision
  sentences at the top, then Risk, Supplies, Patient transfers, Crew plan, Notices sections, and
  `st.download_button("Download briefing (PDF)", data=<bytes>, file_name=
  f"moshari_briefing_{target:%Y-%m-%d}.pdf", mime="application/pdf")` with the bytes passed
  eagerly (not a callable), cached with `st.cache_data`.
- EDIT `ui/views/ward_net.py`: below the header, before the stat tiles, one strip rendered with
  `st.html` whose text, with tags removed and entities unescaped, contains
  `alert_text(supply_alerts(...))` for OVERVIEW_STOCK / OVERVIEW_CREWS / OVERVIEW_SURGE, plus the
  line `"At 70% stock and 40 crews."`; red style when any part is non-zero, green otherwise;
  page links to Resources, Hospital beds and Weekly briefing. Nothing else on the page is removed.
- EDIT `app.py`: one added line in PAGES after Dispatch:
  `st.Page("ui/views/briefing.py", title="Weekly briefing", icon=":material/summarize:")`.
- EDIT `requirements.txt`: one added line `reportlab>=4.0` (the deployed app needs it).
- EDIT `ui/theme.py` (optional): CSS for the strip only.
- EDIT `README.md` (optional): a short "Weekly briefing" paragraph.
- NEW `tests/test_briefing.py`, `tests/test_briefing_page.py`.

## Data flow
`fc = svc.forecast_all(issue_date, horizon, list(cities) or None, policy)`
`alloc = A.allocate(fc, svc.wards, stock_pct, crews)`; `summ = A.summarize(alloc, crews)`
`rr = beds_routing(svc, fc, surge_pct)`
`table = S.build_effect_table(svc, issue_date, cities=list(cities) or None)`;
`plan = {ward: crews_assigned for crews_assigned > 0}`; `by_h = S.simulate(table, plan)[1]`
`notices = D.select_rows(D.dispatch_table(alloc, R.route_overflow(alloc, R.load_bed_capacity())), "high")`

`build` returns: `issue_date` (Timestamp), `target_week` (issue + horizon weeks), `horizon`,
`cities` (sorted unique fc cities), `stock_pct`, `crews`, `surge_pct`, `wards` (len fc),
`high_wards` (tier_idx >= 2), `critical_wards` (tier_idx == 3), `expected_cases` (float sum),
`top_wards` (first 5 fc ward ids, fc order), `saline_short_bags` and `kits_short`
(summ resources "saline bags"/"test kits" short), `deficit_wards` (summ deficit_wards),
`alerts` (supply_alerts(alloc, rr.ward_summary)), `transfers` (rr.transfers as list of dicts),
`patients_moved` (sum of transfer patients), `unplaced` (sum ward_summary net_deficit),
`crews_needed`, `crews_assigned`, `crews_unmet` (summ crews), `cases_prevented`
(round(by_h.cases_prevented.sum(), 1)), `notices_ready` (len notices), `decision` (list of 4 str):

1. `f"{high} of {plural(wards,'ward')} are High or Critical risk for the week of {target:%d %b %Y}."`
2. needed == 0: `"No spraying crews are needed this week."`; unmet > 0:
   `f"Approve {plural(unmet,'more spraying crew')}: {needed} needed, {assigned} assigned."`;
   else `f"All {needed} crews needed are assigned."`
3. deficit_wards > 0: `f"Release {plural(saline,'more saline bag')} and {plural(kits,'more test kit')} to cover {plural(deficit_wards,'short ward')}."`;
   else `"Every ward is fully supplied."`
4. moved and unplaced: `f"Move {plural(moved,'patient')} between wards in the same city; beds are still missing for {plural(unplaced,'patient')}."`;
   moved only: `f"Move {plural(moved,'patient')} between wards in the same city; every patient has a bed."`;
   unplaced only: `f"No transfer can help: beds are still missing for {plural(unplaced,'patient')}."`;
   neither: `"No patient transfers are needed."`

The PDF shows, in this order: "Weekly briefing", the week, the 4 decision sentences, and sections
headed exactly "Risk", "Supplies", "Patient transfers", "Crew plan", "Notices"; the top wards by
`ward_label`; up to 8 transfers as "<from label> to <to label>: <n>"; cases prevented; notices
ready; footer "Made offline by Moshari". ASCII only in drawn text (Helvetica has no "·").

## Error handling
- `stock_pct` outside (0, 1] -> the ValueError from `allocate` propagates (page sliders prevent it).
- Week with no High wards (2016-02-29): crews needed 0, sentence 2 "No spraying crews...", PDF and
  page still render; Overview strip still shows the saline/kit parts (18 wards at 70%).
- Empty transfers: "No patient transfers are needed." and the PDF section says "None".
- City filter: every number covers only the filtered cities (forecast, effect table, routing).
- No network: no import of requests/urllib/httpx/socket in the new modules.

## Tests -> criteria
- verify `logic`: `build` equals the engine-recomputed dict on 4 settings (demo week; 2024-07-01
  h4 with transfers and 4 unplaced; 2016-02-29 empty; Dhaka North at 30%/10 crews/+20%) and
  `alert_text` on synthetic singular/zero cases -> criterion 1 - catches: wrong stock or bed
  source, Hospital vs Dispatch routing mixed up, cities filter ignored, hard-coded demo numbers,
  wrong plural or sentence branch, "All wards supplied" missing.
- verify `pdf`: one A4 page, deterministic, %PDF from reportlab, contains every decision sentence,
  section heading, top ward and transfer, differs between settings -> criterion 2 - catches: two
  pages, compressed or image-only text, static PDF, missing section, stale numbers.
- verify `page`: AppTest Overview shows the exact alert text for 2025-06-02 h3 and 2024-07-01 h4
  and keeps "Expected high risk"; briefing page shows every decision sentence and its download
  button serves `application/pdf` bytes equal to `briefing_pdf(build(...))`; 2016-02-29 renders
  -> criterion 3 - catches: strip missing or stale, page not in app.py, button serving HTML or a
  different scenario, crash on an empty week, Overview gutted.
- verify `tests` + pytest of the two new files (>= 13 passed) -> criterion 4 - catches: missing,
  hollow or skipped tests.
- full suite -> criterion 5 (invariant), counter >= 1013 - catches: broken existing pages/tests.
- verify `git` -> criterion 6 - catches: uncommitted work, wrong author/prefix, files out of
  scope, existing tests or engines edited, app.py/requirements.txt changed beyond one line.

## Steps
1. `briefing.py`: plural, supply_alerts, alert_text, beds_routing, build - fast check:
   `python .claude/goals/weekly-briefing-verify.py logic`
2. `tests/test_briefing.py` (logic + PDF tests) - fast check: `python -m pytest tests/test_briefing.py -o addopts="" -q`
3. `briefing_pdf.py` - fast check: `python .claude/goals/weekly-briefing-verify.py pdf`
4. `requirements.txt` + `app.py` lines, `ui/views/briefing.py` - fast check: verify `page`
5. Overview strip in `ward_net.py` (+ theme CSS) - fast check: verify `page`
6. `tests/test_briefing_page.py` (AppTest) - fast check: pytest of that file
7. Full suite, README paragraph, commits, final rerun of every proof.
