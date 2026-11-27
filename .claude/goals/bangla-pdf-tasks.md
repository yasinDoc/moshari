# bangla-pdf checklist

Built in the project thread after goal 1 (PR #32) merged. Base 5c533fb, test floor 1389.

## Criteria
- [x] 1. Font, licence, uharfbuzz (`V2 fonts`)
- [x] 2. Bangla PDF correct (`V2 bn`)
- [x] 3. Page serves it (`V2 page`)
- [x] 4. English PDF unchanged (`V2 en`)
- [x] 5. New tests real, pass (`V2 tests`, 11 tests in tests/test_briefing_pdf_bn.py)
- [x] 6. Screens still right: `V1 bn` and `V1 switch` PASS; `V1 en` reports only PR #31's Briefing subtitle, see the ruling
- [x] 7. Full suite passes (1400 passed, 1400 collected >= 1389)
- [ ] 8. Committed in scope (`V2 git`): fails only on the two URLs inside the official OFL.txt, see the ruling

## Design steps
- [x] 1. Fonts (hashes match the pins), OFL.txt, `uharfbuzz>=0.39` in requirements.txt
- [x] 2. `briefing.build(lang)`: already added in goal 1, reused unchanged
- [x] 3. `briefing_pdf(brief, lang)` with the bundled font, `shaping=1`, every text through `i18n.t`
- [x] 4. Briefing page: `make(..., lang)` and `make_pdf(..., lang)`, both cached per language
- [x] 5. tests/test_briefing_pdf_bn.py
- [x] 6. README sentence, goal 1 proofs, full suite, commit

## Rulings
- RULING: the goal's placeholders were filled at the start: base 5c533fb (goal 1 merged on main), test floor 1389, verifier sha256 97659ab5... - they were left open until goal 1 ended - cost if wrong: the git check measures from the wrong commit.
- RULING: the uharfbuzz check uses `importlib.util.find_spec` instead of `import uharfbuzz` - an unused import would need a `# noqa`, which the scope forbids - cost if wrong: none, reportlab imports it itself when shaping.
- RULING: the page has two cached functions, `make` (the brief) and `make_pdf` (its PDF), both keyed on the language - so a missing uharfbuzz can fall back to the English PDF without rebuilding the Bangla screen - cost if wrong: none on screen.
- RULING: the fallback message shows the RuntimeError's English text (with the install command) after the Bangla sentence - the catalog check forbids Latin command words in Bangla text - cost if wrong: one English line in an error that only shows on a broken install.
- RULING: "Available" in the Supplies table reads "বরাদ্দ" (allocated) - the English column shows the allocated amount - cost if wrong: a Bangla reader may prefer "মজুত".
- RULING: the PDF's document title metadata stays "Moshari weekly briefing" in both languages - it is not printed on the page - cost if wrong: a Bangla PDF viewer shows an English window title.
- RULING: `V2 git` reports "network code added" only because the official SIL licence (src/moshari/fonts/OFL.txt, which the design requires) contains two URLs: the Noto project's copyright line and scripts.sil.org/OFL. The licence is kept word for word, since the OFL requires its notice to travel unchanged; no code makes a network call - cost if wrong: criterion 8 stays red until the verifier skips OFL.txt.
- RULING: `V1 en` reports 4 lines, all for the Weekly briefing subtitle that PR #31 changed on main after goal 1's English snapshot was taken (same as goal 1's ruling 9). Every other English screen matches - cost if wrong: none, the English text is what main has.

## Discarded attempts
- `import uharfbuzz` inside try/except ImportError: needed `# noqa: F401`, replaced by `find_spec`.
- Bangla fallback message with `pip install -r requirements.txt` inside the catalog text: the catalog check flagged the Latin words; the command now comes only from the error text.

## Known limits (told to the user)
- Whether the Bangla reads naturally needs a Bangla reader: `python .claude/goals/bangla-pdf-verify.py review` writes the 4 PDFs to `.claude/goals/bangla-pdf-review/`.
