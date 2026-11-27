OBJECTIVE: in Bangla mode the Weekly briefing download is a one-page A4 PDF in Bangla with correctly joined letters; the English PDF stays byte-identical; committed.

FIRST ACTION: print `git rev-parse --show-toplevel`; if it is not /home/user/moshari, print "BLOCKED: wrong checkout" and stop. Run `python .claude/goals/bangla-ui-verify.py bn`; if it does not print "PASS bn", print "BLOCKED: goal 1 (bangla-ui) is not done" and stop. Run `pip install -q -r requirements-dev.txt`. Read .claude/goals/bangla-pdf-design.md; print its step count; then continue without waiting.

DONE WHEN (B) OR (A). Check (B) FIRST; if (B) holds the answer is met, and the criteria in (A) are not consulted.
(B) ENDED: the transcript contains three lines starting with "BLOCKED", or one line starting with "LIMIT REACHED". Ending on a blocker or on the turn limit is a VALID ENDING of this goal, not a failure; when (B) holds, whether (A) was reached is irrelevant and "not met" is the wrong answer.
(A) All of the following are true and their outputs are pasted in the transcript:
V2 = `python .claude/goals/bangla-pdf-verify.py`, V1 = `python .claude/goals/bangla-ui-verify.py`.
1. Font, licence, uharfbuzz - proof: `V2 fonts` prints "PASS fonts"
2. Bangla PDF correct - proof: `V2 bn` prints "PASS bn"
3. Page serves it - proof: `V2 page` prints "PASS page"
4. English PDF unchanged - proof: `V2 en` prints "PASS en"
5. New tests real, pass - proof: `V2 tests && python -m pytest tests/test_briefing_pdf_bn.py -o addopts="" -q` prints "PASS tests" and "N passed in", N >= 8
6. Screens still right - proof: `V1 en && V1 bn && V1 switch` print the three PASS lines
7. Full suite passes - proof: `python -m pytest -o addopts="" -q` last line; `--co` count >= __TESTS__
8. Committed in scope - proof: `V2 git` prints "PASS git", then `git diff --stat __BASE__..HEAD`
With V2 outputs print `sha256sum .claude/goals/bangla-pdf-verify.py`, which must be __VERIFY_SHA__.

SCOPE: the files in the design's Components: two TTFs and OFL.txt in src/moshari/fonts/, one uharfbuzz line in requirements.txt, src/moshari/briefing.py, briefing_pdf.py, i18n.py, locales/bn.json, ui/views/briefing.py, ui/i18n.py, new tests/test_briefing_pdf_bn.py, README.md. Nothing else.

CONSTRAINTS: the approach is the one in .claude/goals/bangla-pdf-design.md; the order of its steps is guidance. Fonts are the official Google Fonts files with the pinned hashes. Bangla PDF has the same paragraphs as the English one. Test count must stay >= __TESTS__. Commit with `git -c user.name=Ananya -c user.email=297095755+sam21-og@users.noreply.github.com commit`, messages starting "version-onsite-final:". Forbidden: editing existing tests; skips/xfail; swallowed errors; network calls in code; dependencies other than uharfbuzz; touching exports/ or scripts/; images of text; modifying any file in .claude/goals/ except the checklist.

EXTERNAL EFFECTS: no push or PR; network only for pip and the two font downloads and OFL.txt named in the design.

PER-TURN PROTOCOL: first turn: create .claude/goals/bangla-pdf-tasks.md, one line per criterion and design step, plus a "Discarded attempts" section. Tick items; log abandoned approaches with the reason and do not retry one without new evidence. Log each design deviation and each decision the mandate does not settle as "RULING: <what> - <why> - <cost if wrong>", and list all rulings in the final summary. While iterating, run each step's fast check. At the end of every turn, update the checklist and print "PROGRESS: <x>/8 criteria | TURN <n> | next: <step>". Before declaring completion, rerun every proof in one turn and print the outputs.

STOP: the goal also ends if (a) the executor prints "BLOCKED: <blocker>" when goal 1 is not done, a font download fails or its hash differs, uharfbuzz cannot be installed, the Bangla text cannot fit one page, an existing test fails for a reason outside SCOPE, a needed change falls outside SCOPE or against a CONSTRAINT, or the work needs an approach the design rejected, followed by approaches tried, evidence and the input needed. Each later relaunch while blocked prints only: "BLOCKED (<k>/3): waiting for the user". The third "BLOCKED" line satisfies (B) in DONE WHEN and ends the goal; or (b) it reaches 25 turns, printing "LIMIT REACHED" with the current state of each criterion, which satisfies (B) as well.
