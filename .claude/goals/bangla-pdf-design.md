# Design: bangla-pdf

Goal 2 of 2. Runs AFTER goal 1 (`bangla-ui`) is committed and its recheck says DONE. In Bangla
mode the Weekly briefing page's "Download briefing (PDF)" gives a one-page A4 PDF written in
Bangla, drawn with a bundled Bangla font so joined letters (যুক্তাক্ষর) render correctly. English
mode keeps giving the exact same PDF bytes as today.

## Approach
Chosen: reportlab (already used) + bundled Noto Sans Bengali TTF + `uharfbuzz`. With
`uharfbuzz` installed, reportlab 4.x/5.x shapes complex scripts when a TTF font is registered and
the ParagraphStyle has `shaping=1`. Pre-flight on 2026-11-27: "লক্ষ্যভিত্তিক মশা নিয়ন্ত্রণ" rendered
with correct conjuncts and vowel signs (checked visually).
Rejected: HTML page printed by the browser - not one click, and the English PDF already exists.
Rejected: system fonts - not on every laptop, not offline-safe, licence unclear.
Rejected: image of the text - not searchable, blurry when printed.
Rejected: translating the commissioner briefs made by `scripts/export_dispatch.py` - they are not
downloaded from the dashboard and `exports/` must not change (user decision).

## Components
- NEW `src/moshari/fonts/NotoSansBengali-Regular.ttf` and `NotoSansBengali-Bold.ttf`: the
  official Google Fonts v33 files. Download (the only allowed network besides pip):
  `curl -sS "https://fonts.googleapis.com/css2?family=Noto+Sans+Bengali:wght@400;700"` (no browser
  User-Agent, so it lists .ttf URLs; first URL = 400, second = 700), then `curl -sSL -o ...`.
  SHA-256 must be 89e77fc7... (Regular) and fffa71fb... (Bold), as pinned in the verifier.
- NEW `src/moshari/fonts/OFL.txt`: the SIL Open Font License from
  `https://raw.githubusercontent.com/notofonts/bengali/main/OFL.txt` (the licence requires it to
  travel with the font).
- EDIT `requirements.txt`: add one line `uharfbuzz>=0.39` (nothing else).
- EDIT `src/moshari/briefing.py`: `build(..., lang: str = "en")`. With "en" the dict is identical
  to today. With "bn" the human-readable strings in it (decision sentences, alert text, labels
  the PDF prints) are the Bangla versions from goal 1's catalog (`moshari.i18n.t`) with Bangla
  digits and month names. Numbers stay numbers. If goal 1 already added `lang`, reuse it.
- EDIT `src/moshari/briefing_pdf.py`: `briefing_pdf(brief, lang: str = "en")`. With "en":
  byte-identical output to today (Helvetica, same layout). With "bn": registers the two TTFs
  once (`TTFont("NotoSansBengali", ...)`, `TTFont("NotoSansBengali-Bold", ...)`), every
  ParagraphStyle uses them with `shaping=1`; every text on the page is a Paragraph (no plain
  string table cells, no `canvas.drawString` with Bangla); all labels, headings, table headers,
  footer and sign-off through `t(..., lang="bn")`; ward names via goal 1's `ward()` helper;
  digits Bangla. Same layout and same number of paragraphs as English; still one A4 page
  (shrink, never a second page); `invariant=1`, deterministic bytes.
- EDIT `src/moshari/i18n.py`, `src/moshari/locales/bn.json`: only to add the PDF's strings.
- EDIT `ui/views/briefing.py` (and `ui/i18n.py` if needed): `make()` takes `lang` (it is part of
  the cache key) and calls `B.build(..., lang=lang)` and `briefing_pdf(brief, lang=lang)`.
  File name stays `moshari_briefing_<date>.pdf`.
- NEW `tests/test_briefing_pdf_bn.py`: at least 8 tests.
- EDIT `README.md` (optional): one sentence that the briefing PDF follows the language switch.

## Data flow
sidebar language -> `ui/views/briefing.py` `make(..., lang)` -> `briefing.build(..., lang)` ->
`briefing_pdf(brief, lang)` -> reportlab + uharfbuzz + bundled TTF -> bytes -> download button.

## Error handling
- `uharfbuzz` missing at runtime (old install): `briefing_pdf(..., lang="bn")` raises
  `RuntimeError("Bangla PDF needs uharfbuzz: pip install -r requirements.txt")`; the page catches
  exactly that error, shows it translated (`st.error`), and still offers the English PDF. No bare
  `except`.
- Font file missing: raise `FileNotFoundError` with the path (it ships in the repo).
- Too much text for one page: shrink as today, never split.

## Tests -> criteria
Verifier V2 = `python .claude/goals/bangla-pdf-verify.py` (pinned).
- `V2 fonts` -> criterion 1 - catches: wrong or edited font file, missing licence, uharfbuzz
  missing from requirements.txt or not installed.
- `V2 bn` -> criterion 2 - catches: Helvetica (boxes instead of letters) or unshaped Bangla
  (broken conjuncts), any English word or Latin digit left, content dropped in Bangla (paragraph
  count), decision sentences not Bangla or missing from the PDF, two pages, not A4, font not
  embedded, non-deterministic bytes, `build`/`briefing_pdf` without `lang`.
- `V2 page` -> criterion 3 - catches: page still serving the English PDF in Bangla mode, cache
  key without `lang` (en -> bn -> en in one process), English download changed.
- `V2 en` -> criterion 4 (invariant) - catches: any byte change to the English PDF in 4 scenarios.
- `V2 tests` + pytest -> criterion 5 - catches: hollow tests that pass when the Bangla font
  cannot be registered; skips; fewer than 8.
- goal 1 proofs `V1 en`, `V1 bn`, `V1 switch` -> criterion 6 (invariant) - catches: screens
  broken while doing the PDF.
- full suite -> criterion 7 (invariant).
- `V2 git` -> criterion 8 - catches: out-of-scope files, requirements beyond one uharfbuzz line,
  edited tests, wrong author, swallowed errors, network code.
Not checkable by a script: whether the joined letters LOOK right and read naturally.
`V2 review` writes the 4 Bangla PDFs to `.claude/goals/bangla-pdf-review/` for a person.

## Steps
1. Download fonts + OFL, add uharfbuzz to requirements.txt, `pip install -r requirements.txt` -
   fast check: `V2 fonts`
2. `briefing.build(lang)` - fast check: `python -c` printing `build(..., lang="bn")["decision"]`
3. `briefing_pdf(brief, lang)` with the Bangla font - fast check: `V2 bn` and `V2 en`
4. Briefing page passes `lang` - fast check: `V2 page`
5. `tests/test_briefing_pdf_bn.py` - fast check: `V2 tests`
6. Goal 1 proofs, full suite, commit as Ananya, `V2 git`
