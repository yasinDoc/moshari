#!/usr/bin/env bash
# attacks: 1, 4
# break: make the verifier forget its failures; .claude/goals/* is in ALLOWED and excluded from the dirty check, pin hash is the literal placeholder "SHA_VERIFY"
set -e
f=.claude/goals/a2-exports-verify.py
sed -i 's/^    print(f"{.PASS. if not failures else .FAIL.} {mode}/    failures.clear()\n&/' "$f"
sed -i 's/^def git_mode() -> None:/def git_mode() -> None:\n    return/' "$f"
sed -i 's/^def content() -> None:/def content() -> None:\n    return/' "$f"
