OBJECTIVE: a Weekly briefing page with a one-click one-page A4 PDF (one decision from all 5 modules) and a supply alert strip on Overview, committed.

FIRST ACTION: print `git rev-parse --show-toplevel`; if it is not /home/user/moshari, print "BLOCKED: wrong checkout" and stop. Run `pip install -q -r requirements-dev.txt`. Read .claude/goals/weekly-briefing-design.md; print its step count; then continue without waiting.

DONE WHEN (B) OR (A). Check (B) FIRST; if (B) holds the answer is met, and the criteria in (A) are not consulted.
(B) ENDED: the transcript contains three lines starting with "BLOCKED", or one line starting with "LIMIT REACHED". Ending on a blocker or on the turn limit is a VALID ENDING of this goal, not a failure; when (B) holds, whether (A) was reached is irrelevant and "not met" is the wrong answer.
(A) All of the following are true and their outputs are pasted in the transcript:
V = `python .claude/goals/weekly-briefing-verify.py`.
1. briefing logic matches engines - proof: `V logic` prints "PASS logic"
2. PDF correct - proof: `V pdf` prints "PASS pdf"
3. Strip and page work - proof: `V page` prints "PASS page"
4. New tests real, pass - proof: `V tests && python -m pytest tests/test_briefing.py tests/test_briefing_page.py -o addopts="" -q -rs` prints "PASS tests" and "N passed in", N >= 13
5. Full suite passes - proof: `python -m pytest -o addopts="" -q` last line; `--co` count >= 1013
6. Committed in scope - proof: `V git` prints "PASS git", then `git diff --stat 173de29..HEAD`
With V outputs print its sha256sum, which must be ad9d02ecc0adb99a2f26e97be56131e441d6f609d802f963aa353d12266c2920.

SCOPE: the files listed in the design's Components (new: briefing.py, briefing_pdf.py, ui/views/briefing.py, two test files; edits: ward_net.py strip, theme.py CSS, one app.py line, reportlab in requirements.txt, README). Nothing else.

CONSTRAINTS: the approach is the one in .claude/goals/weekly-briefing-design.md; the order of its steps is guidance. Names, keys, sentences exactly as designed. Test count must stay >= 1013. Commit with `git -c user.name=Ananya -c user.email=297095755+sam21-og@users.noreply.github.com commit`, messages starting "version-onsite-final:". Forbidden: hard-coded weeks, wards or numbers outside tests; editing engines, other pages or existing tests; skips/xfail in new tests; swallowed errors; network calls; new dependencies but reportlab; modifying any file in .claude/goals/ except the checklist.

EXTERNAL EFFECTS: no push or PR; no network but pip.

PER-TURN PROTOCOL: first turn: create .claude/goals/weekly-briefing-tasks.md, one line per criterion and design step, plus a "Discarded attempts" section. Tick items; log abandoned approaches with the reason and do not retry one without new evidence. Log each design deviation and each decision the mandate does not settle as "RULING: <what> - <why> - <cost if wrong>", and list all rulings in the final summary. While iterating, run each step's fast check. At the end of every turn, update the checklist and print "PROGRESS: <x>/6 criteria | TURN <n> | next: <step>". Before declaring completion, rerun every proof in one turn and print the outputs.

STOP: the goal also ends if (a) the executor prints "BLOCKED: <blocker>" when reportlab cannot be installed, an existing test fails for a reason outside SCOPE, a needed change falls outside SCOPE or against a CONSTRAINT, or the work needs an approach the design rejected, followed by approaches tried, evidence and the input needed. Each later relaunch while blocked prints only: "BLOCKED (<k>/3): waiting for the user". The third "BLOCKED" line satisfies (B) in DONE WHEN and ends the goal; or (b) it reaches 30 turns, printing "LIMIT REACHED" with the current state of each criterion, which satisfies (B) as well.
