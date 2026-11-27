# Design: bangla-ui

Goal 1 of 2. An English / বাংলা switch in the sidebar that turns every one of the 11 dashboard
pages into Bangla, while English mode stays byte-for-byte what it is on main 0cf943d. Goal 2
(`bangla-pdf`, later) makes the Weekly briefing PDF Bangla; it is NOT part of this goal.

## Approach
Chosen: one translation catalog with the English text as the key. Every user-visible string in
the pages goes through `t("English text", **args)`. In English mode `t()` returns the English
text formatted exactly as today, so English output cannot drift; in Bangla mode it returns the
catalog's Bangla template with Bangla digits in the numbers. One file holds all translations, so
a Bangla reader can review them in one place.
Rejected: gettext .po/.mo files - adds a compile step and a format the team does not use, no
gain at about 1,500 strings.
Rejected: online machine translation at runtime - breaks "works with the internet off" and the
wording cannot be controlled.
Rejected: duplicate Bangla copies of the page files - two copies drift apart.
Rejected: one single goal for screens and PDF - about 50 turns; split by the user's choice.

## Decisions already taken with the user (do not reopen)
1. The switch is at the TOP of the sidebar (above the page links). Widget key `lang`, values
   `"en"` and `"bn"`, label exactly `ভাষা / Language`, options displayed exactly `English` and
   `বাংলা`, default `"en"`. Use `st.segmented_control` or `st.radio(horizontal=True)`; it must never
   end with no value (restore the previous value if the user deselects).
2. The choice stays while moving between pages (session state) and travels in links: a
   `?lang=bn` query parameter opens the app in Bangla; `state.link_params()` adds `"lang": "bn"`
   only in Bangla mode (English links stay exactly as today).
3. Bangla mode uses Bangla digits (০-৯) and Bangla month names everywhere on screen: text,
   tables, chart ticks, hover labels, the issue-week slider options. Dates read `২৩ জুন ২০২৫`.
4. Ward names read `DNCC ওয়ার্ড ১২` (as `dispatch_bn`), city corporations use `dispatch_bn.CITY_BN`,
   tiers `dispatch_bn.TIER_BN`. Short codes (`DNCC`, `W12`, `DNCC-W12`), the name `Moshari`,
   and product names (Open-Meteo, LightGBM, WhatsApp, SMS, PDF, CSV...) stay Latin.
5. Dispatch keeps its own notice-language picker (`disp_lang`); it starts on the sidebar
   language (`"bn"` in Bangla mode, `"en"` in English mode) and can still be changed.
6. CSV / ZIP downloads keep their English column names and file contents. Their button labels
   and help texts are translated.
7. README gets one short paragraph about the switch; other docs stay English.

## Components
- NEW `src/moshari/i18n.py` (no Streamlit import): loads `src/moshari/locales/bn.json` once;
  `digits(x) -> str` (ASCII 0-9 to ০-৯ in any text); `t(text, lang="en", **kw) -> str`
  (en: `text.format(**kw)` if kw else `text`, i.e. today's exact output; bn: the catalog
  template formatted with the same kw, where every int / float / numpy number / Timestamp value
  is formatted with the template's own format spec and then passed through `digits()`; string
  values are inserted unchanged, so callers pass already-translated words); `month_bn`, `week(d,
  lang)` (`%d %b %Y` in en, `২৩ জুন ২০২৫` in bn), `short(d, lang)`, `ward(ward_id, lang)`,
  `city(code, lang)`, `tier(name, lang)`, `num(x, spec, lang)`, `plural_en` helpers as needed.
  Missing Bangla entry: `t()` returns the English text and adds it to `i18n.MISSING` (no
  exception, so a forgotten string never crashes a page; the `bn` proof catches it).
- NEW `src/moshari/locales/bn.json`: `{English template: Bangla template}`, UTF-8, sorted keys,
  `ensure_ascii=False`, 2-space indent. Placeholders `{name}` / `{name:.1f}` identical on both
  sides. Reuse the vocabulary of `src/moshari/dispatch_bn.py` so words match the notices.
- NEW `ui/i18n.py`: `lang()` = `st.session_state.get("lang", "en")`; `t(text, lang=None, **kw)`,
  `digits`, `week`, `short`, `ward`, `city`, `tier`, `num` wrapping the core with the session
  language; Plotly helpers `bn_axis(fig, axis, values, fmt)` (sets `tickmode="array"`,
  `tickvals`, Bangla `ticktext`) and `bn_hover` (pre-formatted Bangla strings in `customdata`,
  `hovertemplate` uses only `%{customdata[i]}` / `%{text}`), applied ONLY in Bangla mode so the
  English figures stay identical.
- EDIT `app.py`: the switch at the top of the sidebar; `page_link` labels, brand, status box and
  settings through `t()`. Page titles stay the English keys in `st.Page(title=...)` if needed
  for routing; the visible labels are translated.
- EDIT `ui/state.py`: settings panel labels, help, format_funcs (Bangla dates in the slider
  options, Bangla tips), `?lang=` in `_apply_query_params` (read BEFORE the switch renders),
  `link_params` adds `lang` in Bangla only, `fmt_week`/`fmt_short` keep their English output.
- EDIT `ui/theme.py`: `inject_css()` in Bangla mode imports Hind Siliguri weights 400;500;600;700
  and puts `FONT_BN` first in the body font stack; English CSS unchanged. `header`, `card_title`,
  `footer`, `badge` take already-translated text.
- EDIT `ui/components.py`, `ui/wardmap.py`, all 11 `ui/views/*.py`: every visible string through
  `t()` / helpers; tables in Bangla mode get Bangla column labels and string cells with Bangla
  digits (numeric columns become pre-formatted text in Bangla mode only; read-only tables);
  charts get Bangla titles, names, ticks and hovers.
- EDIT (only if a displayed sentence is composed there) `src/moshari/briefing.py`, `risk.py`,
  `dispatch.py` etc.: a function may gain an optional keyword `lang: str = "en"`; with `"en"` its
  output stays identical (existing tests prove it). Prefer translating fixed engine strings at
  display time with `t()`.
- EDIT `README.md`: one paragraph.
- NEW `tests/test_i18n.py`: at least 12 tests (see Tests).

## Data flow
sidebar switch -> `st.session_state["lang"]` -> every `t()` / helper call in app.py, state.py,
components, views reads it -> English: unchanged strings and figures; Bangla: catalog template
+ Bangla digits, Bangla Plotly ticks/hover, text tables -> Streamlit elements. `?lang=bn` sets
the session value on the first run; ward links carry it on.

## Error handling
- Missing catalog entry: English text shown, recorded in `i18n.MISSING`; never an exception.
- Unknown `lang` value (bad link): falls back to `"en"`.
- Catalog file missing or invalid JSON: raise at import with a clear message (it is shipped in
  the repo; failing loudly is correct).
- Placeholder mismatch between English and Bangla: a test in `tests/test_i18n.py` fails.
- Offline: no network code is added; the Google Fonts CSS import already exists and falls back
  to system Bangla fonts (Noto Sans Bengali, Vrinda) offline.

## Known limits (not checked, tell the user)
Texts drawn by Streamlit's own front end cannot be translated from Python: the file uploader's
"Drag and drop file here / Limit 200MB", the dataframe toolbar tooltips, and the digits inside
`st.number_input` / `st.slider` value boxes. They stay as Streamlit draws them.

## Tests -> criteria
Verifier V = `python .claude/goals/bangla-ui-verify.py` (pinned, written before the work).
- `V catalog` -> criterion 1 - catches: Bangla values left English or empty, copied English,
  placeholders dropped or renamed (numbers vanish in Bangla), Latin digits inside translations,
  one Bangla word reused for everything, `t()` not reading the catalog or not converting digits,
  made-up Bangla (e.g. letter-by-letter transliteration): a glossary requires the team's words
  from `dispatch_bn` for tiers and city corporations exactly, and in at least 90% of entries
  ward -> ওয়ার্ড, dengue -> ডেঙ্গু, saline -> স্যালাইন, forecast -> পূর্বাভাস, crew -> দল.
- `V bn` -> criterion 2 - catches: any English word or Latin digit left on any of the 11 pages
  (default week and Peak week, plus Live outlook with saved weather), numeric table columns and
  Plotly ticks / hovers that the browser would draw in Latin digits, hollow pages (Bangla text
  much shorter than the English), untranslated page titles or sidebar links, crashes in Bangla,
  network calls, and a Bangla page BUILT DIFFERENTLY from the English one (an element, table
  column or row, chart trace, hover or axis dropped or hidden in Bangla to dodge a check).
  Rule for the executor: Bangla mode changes only text, never which elements exist.
- `V switch` -> criterion 3 - catches: switch missing / wrong key or label, default not English,
  `?lang=bn` ignored, language lost when moving between pages, ward links dropping `lang=bn`,
  English links changed, Dispatch notices not starting in Bangla, no Bangla body font.
- `V en` -> criterion 4 (invariant) - catches: any change to English text on any page and state
  (word, number, order, chart text), including changes made by refactoring strings into `t()`.
- `V tests` + `pytest tests/test_i18n.py` -> criterion 5 - catches: hollow tests (they must fail
  when the catalog is emptied and when `t()` ignores Bangla), skips/xfail, fewer than 12 tests.
- full suite -> criterion 6 (invariant) - catches: broken engines, edited old tests.
- `V git` + `git diff --stat` -> criterion 7 - catches: uncommitted work, files out of scope,
  existing tests modified, wrong author / message, swallowed errors, network code.

Required tests in `tests/test_i18n.py` (at least 12): `t()` English identity with and without
args; Bangla lookup; Bangla digits in formatted numbers (int, float with spec, negative, percent);
`digits()`; week/short dates in both languages (all 12 Bangla months); `ward()` both languages;
missing key falls back to English and is recorded; every catalog entry has Bangla letters and the
same placeholders as its key (the catalog has at least one entry whose only placeholder is a plain `{n}`, e.g. "{n} wards"); unknown lang falls back to English; `link_params` carries `lang`
only in Bangla (via AppTest or by setting session state); one AppTest page opened in Bangla shows
the Bangla title.

## Steps
1. `src/moshari/i18n.py`, `src/moshari/locales/bn.json` seeded with dispatch_bn vocabulary,
   `ui/i18n.py`, `tests/test_i18n.py` - fast check: `python -m pytest tests/test_i18n.py -o addopts="" -q`
2. Switch in `app.py`, query param + links in `ui/state.py`, Bangla CSS in `ui/theme.py`, sidebar
   and settings translated - fast check: `V switch`
3. Overview (`ward_net.py`, `components.py`) and Ward map (`ward_map.py`, `wardmap.py`) - fast
   check: `V en` and `V bn 2>&1 | grep -E "ward_net|ward_map|PASS"`
4. Resources, Hospital beds, Simulator - same fast check filtered on those pages
5. Dispatch (notice language default), Weekly briefing - same
6. Live outlook, Ward forecast - same
7. Model accuracy, Data - same
8. `V catalog`, full `V bn`, `V en`, `V tests`, full suite; README paragraph
9. Commit(s) as Ananya; `V git`
