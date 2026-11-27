OBJECTIVE: TASKS.md A2: scripts/export_dispatch.py writes the demo week's SMS, WhatsApp, HTML and reportlab PDF briefs into exports/, committed.

FIRST ACTION: print `git rev-parse --show-toplevel`; if it is not /home/user/moshari, print "BLOCKED: wrong checkout" and stop. Read .claude/goals/a2-exports-design.md, src/moshari/dispatch.py; print the design step count; then continue without waiting.

DONE WHEN (B) OR (A). Check (B) FIRST; if (B) holds the answer is met, and the criteria in (A) are not consulted.
(B) ENDED: the transcript contains three lines starting with "BLOCKED", or one line starting with "LIMIT REACHED". Ending on a blocker or on the turn limit is a VALID ENDING of this goal, not a failure; when (B) holds, whether (A) was reached is irrelevant and "not met" is the wrong answer.
(A) All of the following are true and their outputs are pasted in the transcript:
1. exports/ is generated and correct - proof: `python .claude/goals/a2-exports-verify.py content` prints "PASS content", with `sha256sum .claude/goals/a2-exports-verify.py` = 4104ca7615388bad01dff1b9196e6d191b23ea0319988aea8070519f0ae25d5c
2. New tests real and passing - proof: `python .claude/goals/a2-exports-verify.py tests && python -m pytest tests/test_export_dispatch.py -o addopts="" -q -rs` prints "PASS tests" and "N passed in", N >= 8
3. Full suite passes - proof: `python -m pytest -o addopts="" -q` last line; `--co` count >= 984
4. Committed in scope - proof: `python .claude/goals/a2-exports-verify.py git` prints "PASS git", then `git diff --stat cc0f514..HEAD -- . ':(exclude).claude'`

SCOPE: may create scripts/export_dispatch.py, src/moshari/dispatch_pdf.py, tests/test_export_dispatch.py, exports/ (script output); may edit README.md (an Exports section), requirements-dev.txt (reportlab>=4.0). Nothing else.

CONSTRAINTS: the approach is the one in .claude/goals/a2-exports-design.md; the order of its steps is guidance. Notice text comes only from moshari.dispatch. Test count must stay >= 976. Commit with `git -c user.name=Ananya -c user.email=297095755+sam21-og@users.noreply.github.com commit`, messages starting "version-onsite-final:". Forbidden: hand-made files in exports/; hardcoded wards or notice text; skip/skipif/xfail/importorskip in new tests; swallowed errors; network calls; new dependencies but reportlab; modifying any file in .claude/goals/ except the checklist.

EXTERNAL EFFECTS: no push, no network, no PR.

PER-TURN PROTOCOL: on the first turn, create the checklist .claude/goals/a2-exports-tasks.md with one line per criterion and per design step and a section "Discarded attempts". Tick items when done; log each abandoned approach with the reason; do not retry one without new evidence. Log every deviation from the design, and every decision the mandate does not settle, in the checklist as "RULING: <what> - <why> - <cost if wrong>", and list all rulings in the final summary. While iterating, run the design step's fast check. At the end of every turn, update the checklist and print "PROGRESS: <x>/4 criteria | TURN <n> | next: <step>". Before declaring completion, rerun every proof in the same turn and print the outputs.

STOP: the goal also ends if (a) the executor prints "BLOCKED: <blocker>" when reportlab cannot be installed, an existing test fails for a reason outside SCOPE, a needed change falls outside SCOPE or against a CONSTRAINT, or the work needs an approach the design rejected, followed by the approaches tried, the evidence gathered and the input needed to continue. Each later relaunch while still blocked prints one line only: "BLOCKED (<k>/3): waiting for the user". The third "BLOCKED" line satisfies (B) in DONE WHEN and ends the goal; or (b) it reaches 25 turns, printing "LIMIT REACHED" with the current state of each criterion, which satisfies (B) as well.
