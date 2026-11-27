# Design: a2-exports

Task A2 in TASKS.md: `scripts/export_dispatch.py` writes sample dispatch notices for the
demo week into `exports/`, and the generated files are committed for the judges.

## Approach
Chosen (by Ananya, 2026-11-27): thin CLI over the existing `moshari.dispatch` templates for SMS,
WhatsApp and HTML; the PDF brief is drawn with reportlab in a new module that mirrors the HTML
brief section by section, using the same `moshari.dispatch` helpers for every value and sentence.
Why: works with no browser installed, PDFs are byte-identical on rerun (`invariant=1`), and the
PDF text can be checked mechanically (`pageCompression=0`).
Rejected: printing the HTML brief with headless Chrome/Edge - not chosen by the user.
Rejected: Playwright - heavy dependency and a browser download for a few sample files.
Rejected: new notice wording, or changes to dispatch.py / allocation.py / routing.py / app.py / ui/
- A2 is an exporter; those files are owned by others or already merged (PR 16).

## Components
- NEW `src/moshari/dispatch_pdf.py` (Ananya's module 4, next to dispatch.py):
  - `write_brief_pdf(rows, path, sender=dispatch.SENDER) -> Path`: one A4 page per row, in the
    given order. Imports reportlab inside the function, so importing the module (and the app)
    never needs reportlab. `SimpleDocTemplate(..., pagesize=A4, invariant=1, pageCompression=0,
    title=..., author="Moshari")`. Built-in Helvetica fonts only (no font files, offline).
  - Page content, same order and wording as `dispatch._brief_page`: kicker "Commissioner brief ·
    dengue response"; title `ward_label(ward)`; "<city> · Week of DD Month YYYY"; "<tier> risk"
    badge in the tier colour (`risk.TIERS[tier].color`); KPI row "Expected cases", "Outbreak
    chance", "Spraying crews", "Priority" with the same values and sub-lines; "Supplies" table
    with "Supply / Required / Allocated / Gap / Filled" from `dispatch.supply_lines`; "Deficit:
    <deficit_text>." or "Fully supplied for the planned caseload."; "Hospital beds and overflow"
    with the same bullet sentences (capacity, send, receive, unplaced, or "No transfers needed:
    ..."); "Actions" numbered from `dispatch.actions`; two signature lines; footer. One page per
    ward: if content overflows, shrink, never spill onto a second page.
  - Reuses dispatch helpers read-only, including private ones (`_crews`, `_transfers`, `_int`,
    `_plural`); does not copy their logic.
- NEW `scripts/export_dispatch.py` (style of `scripts/train.py`: `sys.path` insert of `src/`,
  UTF-8 stdout reconfigure, argparse with the module docstring as help):
  - `build_rows(issue, horizon, stock, crews, select) -> list[dict]`: ForecastService(
    load_dataset(), ForecastBundle.load()) -> forecast_all(issue, horizon, None,
    DEFAULT_ALERT_POLICY) -> allocation.allocate(fc, svc.wards, stock, crews) ->
    routing.route_overflow(alloc, routing.load_bed_capacity()) -> dispatch.dispatch_table ->
    dispatch.select_rows(table, select). Same chain as ui/views/dispatch.py `build_table`.
  - `write_exports(rows, out_dir, settings, pdf_mode) -> dict`: `sms/<ward>.txt`
    (`dispatch.sms(row) + "\n"`), `whatsapp/<ward>.txt` (`dispatch.whatsapp(row) + "\n"`),
    `briefs/<ward>.html` (`dispatch.brief_html(row)`), `briefs/all_briefs.html`
    (`dispatch.briefs_html(rows)`), PDFs, and `README.md` (index). Same names and bytes as
    `dispatch.export_zip`. UTF-8, `newline="\n"`.
  - CLI defaults = the app's defaults: `--issue` = `svc.default_issue_date()` (2025-06-02 for the
    bundled data), `--horizon 3`, `--stock 70` (percent), `--crews 40`, `--select high`
    (high|deficit|all), `--out exports`, `--pdf top` (top|all|none: `top` = the highest-priority
    ward's `<ward>.pdf` plus `all_briefs.pdf`; `all` = every ward plus `all_briefs.pdf`),
    `--require-pdf`.
- NEW `tests/test_export_dispatch.py`.
- NEW committed folder `exports/` (generated, never hand-edited).
- EDIT `requirements-dev.txt`: add `reportlab>=4.0` (CI installs this file). requirements.txt
  (the deployed app) is not changed.
- EDIT `README.md`: one short "Exports" section: install line for reportlab, the command, the
  flags, what lands where.

## Data flow
args -> build_rows (offline: bundled CSV + trained model) -> rows in the table's priority order
-> write_exports into a fresh temp dir next to `out` -> PDFs drawn from the same rows -> the temp
dir replaces `out/sms`, `out/whatsapp`, `out/briefs` and `out/README.md` (old files in those
folders removed, so a ward that left the selection does not linger) -> summary printed: settings,
ward count, files per folder, PDF paths or why PDFs were skipped.
exports/README.md lists the exact command and settings, the target week (YYYY-MM-DD), the ward
list with tier and deficit flag, and file counts. No timestamps: a rerun is byte-identical,
PDFs included.

## Error handling
- `--issue` not among `svc.issue_dates` -> message naming the nearest valid dates, exit 2.
- `--horizon` not in the model's horizons, `--stock` outside 30-100, `--crews` < 0 -> exit 2.
- Empty selection -> message ("no ward is High or Critical for these settings"), exit 1, `out`
  untouched.
- Any error while writing -> temp dir removed, `out` untouched, exit 1. No bare `except`, no
  `except Exception: pass`.
- reportlab not installed (ImportError) -> warning naming reportlab and the install command; text
  and HTML still written; exit 0. With `--require-pdf` -> exit 1, `out` untouched.
- Never calls the network; works with `MOSHARI_OFFLINE=1`.

## Tests -> criteria
- `.claude/goals/a2-exports-verify.py content` -> criterion 1 - catches: files hand-written or
  copied instead of generated; text differing from `dispatch.sms/whatsapp/brief_html`; wrong
  wards or settings; SMS over 160 GSM-7 chars; missing all_briefs.html or README index; README
  without the command, `--pdf` and the reportlab install; a PDF that is not reportlab, not A4,
  not one page per ward, or whose page i is not ward i's full brief (header, week, tier, KPI
  labels and values, supply table cells, deficit or fully-supplied sentence, bed and transfer
  sentences, every action, signatures, footer; headings and sentences in brief order); PDFs not
  byte-identical on rerun; a script that copies exports/ (rechecked at issue 2023-08-07, 100%
  stock, 10 crews, all 60 wards, `--pdf all`, which has transfers in, out and unplaced); stale
  wards or PDFs after a narrower rerun; empty selection, bad `--issue/--horizon/--stock/--crews`
  or missing reportlab not handled as specified; `dispatch_pdf` not importable without
  reportlab; the script or module reading `.claude/` (the verifier).
- `.claude/goals/a2-exports-verify.py tests` then `pytest tests/test_export_dispatch.py` ->
  criterion 2 - catches: fewer than 8 distinct test functions; a test that calls nothing or
  asserts nothing; a file that never touches export_dispatch, dispatch_pdf or a ward with
  transfers; skipped or failing tests. Test intent (write them for): layout, rerun identical,
  empty selection exits 1 and writes nothing, failure mid-write leaves `out` untouched, stale
  ward files removed, invalid flags exit 2, missing reportlab warns, one PDF page per ward, a
  synthetic ward with transfers in/out shows them in the PDF, `import moshari.dispatch_pdf`
  without reportlab.
- `{python} -m pytest -o addopts="" -q` -> criterion 3 (invariant) - full suite still passes.
- `.claude/goals/a2-exports-verify.py git` -> criterion 4 - catches: work left uncommitted;
  commits without the `version-onsite-final:` prefix or not authored by Ananya; files changed
  outside SCOPE; work commits editing `.claude/` files other than the checklist;
  requirements-dev.txt gaining anything but reportlab.
- Recheck guards: test counter >= 976; pins on dispatch.py, allocation.py, routing.py,
  service.py, data.py, config.py, `ui/`, `app.py`, `tests/conftest.py`, `data/`, `models/`,
  requirements.txt, this design file and the verifier.
- Not checked mechanically (human review): PDF visual layout (colours, spacing, tier badge).

## Steps
1. `build_rows` + `write_exports` + `main` with `--pdf none` - fast check:
   `python scripts/export_dispatch.py --pdf none --out /tmp/x && ls /tmp/x/sms | wc -l` (26)
2. Temp-dir swap, validation, exit codes - fast check:
   `python scripts/export_dispatch.py --issue 1999-01-01; echo $?` (2)
3. `src/moshari/dispatch_pdf.py` and the `--pdf` modes - fast check: `python scripts/export_dispatch.py --out /tmp/x && ls /tmp/x/briefs/*.pdf`
4. `tests/test_export_dispatch.py` - fast check:
   `python -m pytest tests/test_export_dispatch.py -o addopts="" -q -rs`
5. `requirements-dev.txt`, generate the real `exports/`, README section - fast check:
   `python .claude/goals/a2-exports-verify.py content`
6. Commit with the `version-onsite-final:` prefix (no push); run every proof.
