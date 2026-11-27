OBJECTIVE: Add a Weekly briefing page whose one button downloads a one-page A4 reportlab PDF that turns risk, supplies, transfers, crews and notices into one decision, and a supply alert strip on the Overview page, all committed.

FIRST ACTION: print `git rev-parse --show-toplevel`; if it is not /home/user/moshari, print "BLOCKED: wrong checkout" and stop. Run `pip install -q -r requirements-dev.txt`. Read .claude/goals/weekly-briefing-design.md; print its step count and the number of keys `build` must return; then continue without waiting.

DONE WHEN (B) OR (A). Check (B) FIRST; if (B) holds the answer is met, and the criteria in (A) are not consulted.
(B) ENDED: the transcript contains three lines starting with "BLOCKED", or one line starting with "LIMIT REACHED". Ending on a blocker or on the turn limit is a VALID ENDING of this goal, not a failure; when (B) holds, whether (A) was reached is irrelevant and "not met" is the wrong answer.
(A) All of the following are true and their outputs are pasted in the transcript:
1. moshari.briefing matches the engines - proof: `python .claude/goals/weekly-briefing-verify.py logic` prints "PASS logic"
2. One-page PDF correct - proof: `python .claude/goals/weekly-briefing-verify.py pdf` prints "PASS pdf"
3. Overview strip and briefing page work in the app - proof: `python .claude/goals/weekly-briefing-verify.py page` prints "PASS page"
4. New tests real and passing - proof: `python .claude/goals/weekly-briefing-verify.py tests && python -m pytest tests/test_briefing.py tests/test_briefing_page.py -o addopts="" -q -rs` prints "PASS tests" and "N passed in", N >= 13
5. Full suite passes - proof: `python -m pytest -o addopts="" -q` last line; `--co` count >= 1013
6. Committed in scope - proof: `python .claude/goals/weekly-briefing-verify.py git` prints "PASS git", then `git diff --stat 173de29..HEAD -- . ':(exclude).claude'`
With each verifier output print `sha256sum .claude/goals/weekly-briefing-verify.py`, which must be 6a4428b31fa36187d3fb34caa4ca63bb47b2b0e8f70d439b689c05137599d873.

SCOPE: may create src/moshari/briefing.py, src/moshari/briefing_pdf.py, ui/views/briefing.py, tests/test_briefing.py, tests/test_briefing_page.py; may edit ui/views/ward_net.py (add the strip only), ui/theme.py (CSS), app.py (one PAGES line), requirements.txt (reportlab>=4.0), README.md (a short section). Nothing else.

CONSTRAINTS: the approach is the one in .claude/goals/weekly-briefing-design.md; the order of its steps is guidance. API names, dict keys and sentence templates are exactly as in the design. Every number comes from moshari allocation, routing, simulation and dispatch. Test count must stay >= 1013. Commit with `git -c user.name=Ananya -c user.email=297095755+sam21-og@users.noreply.github.com commit`, messages starting "version-onsite-final:". Forbidden: hard-coded weeks, wards or numbers outside tests; editing engines, other pages or existing tests; skip/skipif/xfail/importorskip in new tests; swallowed errors; network calls; new dependencies but reportlab; modifying any file in .claude/goals/ except the checklist.

EXTERNAL EFFECTS: no push, no PR, no network beyond pip install.

PER-TURN PROTOCOL: on the first turn, create the checklist .claude/goals/weekly-briefing-tasks.md with one line per criterion and per design step and a section "Discarded attempts". Tick items when done; log each abandoned approach with the reason; do not retry one without new evidence. Log every deviation from the design, and every decision the mandate does not settle, in the checklist as "RULING: <what> - <why> - <cost if wrong>", and list all rulings in the final summary. While iterating, run the design step's fast check. At the end of every turn, update the checklist and print "PROGRESS: <x>/6 criteria | TURN <n> | next: <step>". Before declaring completion, rerun every proof in the same turn and print the outputs.

STOP: the goal also ends if (a) the executor prints "BLOCKED: <blocker>" when reportlab cannot be installed, an existing test fails for a reason outside SCOPE, a needed change falls outside SCOPE or against a CONSTRAINT, or the work needs an approach the design rejected, followed by the approaches tried, the evidence gathered and the input needed to continue. Each later relaunch while still blocked prints one line only: "BLOCKED (<k>/3): waiting for the user". The third "BLOCKED" line satisfies (B) in DONE WHEN and ends the goal; or (b) it reaches 30 turns, printing "LIMIT REACHED" with the current state of each criterion, which satisfies (B) as well.
