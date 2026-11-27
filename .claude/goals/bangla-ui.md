OBJECTIVE: a sidebar switch English / বাংলা turning all 11 dashboard pages into Bangla, English output unchanged, committed.

FIRST ACTION: print `git rev-parse --show-toplevel`; if it is not /home/user/moshari, print "BLOCKED: wrong checkout" and stop. Run `pip install -q -r requirements-dev.txt`. Read .claude/goals/bangla-ui-design.md and src/moshari/dispatch_bn.py; print the design step count and the ui/views/*.py count; then continue without waiting.

DONE WHEN (B) OR (A). Check (B) FIRST; if (B) holds the answer is met, and the criteria in (A) are not consulted.
(B) ENDED: the transcript contains three lines starting with "BLOCKED", or one line starting with "LIMIT REACHED". Ending on a blocker or on the turn limit is a VALID ENDING of this goal, not a failure; when (B) holds, whether (A) was reached is irrelevant and "not met" is the wrong answer.
(A) All of the following are true and their outputs are pasted in the transcript:
V = `python .claude/goals/bangla-ui-verify.py`.
1. Catalog correct - proof: `V catalog` prints "PASS catalog"
2. No English left in Bangla - proof: `V bn` prints "PASS bn"
3. Switch works - proof: `V switch` prints "PASS switch"
4. English unchanged - proof: `V en` prints "PASS en"
5. New tests real - proof: `V tests && python -m pytest tests/test_i18n.py -o addopts="" -q -rs` prints "PASS tests", "N passed in", N >= 12
6. Full suite passes - proof: `python -m pytest -o addopts="" -q` last line; `--co` count >= 1374
7. Committed in scope - proof: `V git` prints "PASS git", then `git diff --stat 0cf943d..HEAD`
With V outputs print `sha256sum .claude/goals/bangla-ui-verify.py`, which must be 07f4ca108a0354e46d7937c5ef62f8d1f9f25ec6e89fc1e96036450a31b833a1.

SCOPE: the design's Components only (new i18n modules, catalog, tests/test_i18n.py; app.py, ui/, README.md; src/moshari/*.py only for an optional lang="en" keyword).

CONSTRAINTS: the approach is the one in .claude/goals/bangla-ui-design.md; the order of its steps is guidance. Its 7 user decisions are fixed. Bangla mode changes only text, never which elements exist. Test count must stay >= 1374. Commit via `git -c user.name=Ananya -c user.email=297095755+sam21-og@users.noreply.github.com commit`, messages starting "version-onsite-final:". Forbidden: editing existing tests; skips/xfail; swallowed errors; network calls; new dependencies; machine translation; touching models/, data/, artifacts/, exports/, scripts/, requirements*.txt; modifying any file in .claude/goals/ except the checklist.

EXTERNAL EFFECTS: no push, no PR; no network but pip.

PER-TURN PROTOCOL: first turn: create .claude/goals/bangla-ui-tasks.md (one line per criterion and design step, + "Discarded attempts"). Tick items; log abandoned approaches with the reason; never retry one without new evidence. Log each design deviation or unsettled decision as "RULING: <what> - <why> - <cost if wrong>", and list all rulings in the final summary. While iterating, run each step's fast check. At each turn end, update the checklist and print "PROGRESS: <x>/7 criteria | TURN <n> | next: <step>". Before declaring completion, rerun every proof in one turn and print the outputs.

STOP: the goal also ends if (a) the executor prints "BLOCKED: <blocker>" when a text cannot be translated without changing English, an existing test fails for a reason outside SCOPE, a needed change falls outside SCOPE or against a CONSTRAINT, or the work needs an approach the design rejected, followed by approaches tried, evidence, input needed. Each later relaunch while blocked prints only: "BLOCKED (<k>/3): waiting for the user". The third "BLOCKED" line satisfies (B) in DONE WHEN and ends the goal; or (b) it reaches 40 turns, printing "LIMIT REACHED" with the current state of each criterion, which satisfies (B) as well.
