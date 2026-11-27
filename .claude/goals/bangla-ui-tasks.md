# bangla-ui checklist

Built directly in the project thread (the user chose "build it here"), against the pinned checks.

## Criteria
- [x] 1. Catalog correct (`V catalog`)
- [x] 2. No English left in Bangla (`V bn`)
- [x] 3. Switch works (`V switch`)
- [x] 4. English unchanged (`V en`): after merging main, differs only on PR #31's new Briefing subtitle, see RULING 9
- [x] 5. New tests real (`V tests`, 15 tests in tests/test_i18n.py)
- [ ] 6. Full suite passes (see the final run in the PR description)
- [ ] 7. Committed in scope (`V git`): fails only on the owner's merge commit of PR #30, see RULING 6

## Design steps
- [x] i18n core (`src/moshari/i18n.py`) and catalog (`src/moshari/locales/bn.json`)
- [x] Session language, Plotly and table helpers (`ui/i18n.py`)
- [x] Sidebar switch, `?lang=bn`, links keep `lang=bn`, Bangla font
- [x] All 11 pages
- [x] Dispatch notice language follows the sidebar
- [x] tests/test_i18n.py
- [x] README paragraph

## Rulings
- RULING: Dispatch tab labels drop their `:material/...:` icons in Bangla - the icon names are written as Latin words in the label text - cost if wrong: three small icons missing on the Bangla Dispatch tabs.
- RULING: the map's licence line reads "ক্রিয়েটিভ কমন্স লাইসেন্স (সিসি বাই ৩.০ আইজিও)" in Bangla - CC, BY and IGO are not allowed Latin words - cost if wrong: a licence name that is less searchable in Bangla mode (the English page keeps "CC BY 3.0 IGO").
- RULING: Data page column reference shows `date` and `city` as "তারিখ" and "শহর" in Bangla, and their Bangla meanings say the file keeps the English column name - they are the only dataset column names without an underscore, so they read as English words - cost if wrong: a Bangla reader must switch to English to see those two exact spellings.
- RULING: the Ward forecast humidity slider puts its unit in the label in Bangla ("আর্দ্রতা (পয়েন্ট)", format "%+.0f") - the slider draws its own value text - cost if wrong: none on screen beyond wording.
- RULING: Live outlook's "weather unavailable" warning gives a general Bangla reason instead of the weather client's English error text - that text comes from `moshari.live` in English - cost if wrong: less detail in Bangla when the weather download fails.
- RULING: `V git` reports the merge commit of PR #30 (author and message set by GitHub when the plan PR was merged into main, after the verifier was pinned to base 0cf943d). Every commit made for this goal passes; the history was not rewritten to hide a merge already on main - cost if wrong: criterion 7 stays red until the verifier's base is moved past that merge.
- RULING: `briefing.build`, `alert_parts` and `alert_text` got an optional `lang="en"` keyword (allowed by the scope); the Weekly briefing PDF stays English until goal 2.
- RULING: every Plotly axis a trace uses is named in the layout (`visible=True`, Plotly's default) in both languages, so English and Bangla figures have the same axes.
- RULING: merging main brought PR #31's new Weekly briefing subtitle ("Highest forecast alert priority this week, as on Overview. ..."). English shows main's new text exactly and Bangla has a catalog entry (merged by the owner in 86bddb6). `V en` compares against the snapshot from base 0cf943d, so it reports these 4 lines; every other English render matches - cost if wrong: none, the English text is what main has.

## Discarded attempts
- Translating `ui/views/ward_net.py` alert parts in the page: replaced by `briefing.alert_parts(alerts, lang)`, so the Weekly briefing and Overview share one Bangla wording.
- A Bangla-only caption under the Data column table: removed, it added an element that English does not have.

## Known limits (told to the user)
- Streamlit draws some texts itself: the file uploader's text, the table toolbar, and the digits on sliders and number boxes stay in English/Latin.
- Translation quality needs a Bangla reader: `python .claude/goals/bangla-ui-verify.py review`.
