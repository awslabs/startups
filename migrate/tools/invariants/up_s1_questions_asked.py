#!/usr/bin/env python3
"""UP-S1: questions_asked includes at least one question (soft observation).

Invariant
---------
In the user-preferences fixture, the pre-seeded preferences.json has
questions_asked: ["Q1", "Q3", "Q5"]. After Clarify completes, this list
should still contain entries — proving the skill tracked which questions
were actually asked to the user (vs defaulted or skipped).

This is a soft observation: it verifies metadata completeness, not functional
correctness.

Skill file reference
--------------------
  references/phases/clarify/clarify.md (lines 299-310)
    preferences.json metadata includes questions_asked (array of question IDs
    the user was prompted for), questions_defaulted (resolved via defaults),
    and questions_skipped_not_applicable.

Examples
--------
  PASS: metadata.questions_asked = ["Q1", "Q3", "Q5"]
        Three questions were asked to the user.

  FAIL: metadata.questions_asked = []
        No questions were asked — all were defaulted or skipped.
"""

import json
import sys
from pathlib import Path


def main():
    migration_dir = Path(sys.argv[1])
    prefs_file = migration_dir / "preferences.json"

    if not prefs_file.exists():
        print(json.dumps({"status": "skip", "details": "preferences.json not found"}))
        return

    data = json.loads(prefs_file.read_text(encoding="utf-8"))
    asked = data.get("metadata", {}).get("questions_asked", [])

    if asked:
        print(json.dumps({"status": "pass"}))
    else:
        print(json.dumps({"status": "fail", "details": "No questions in questions_asked list"}))


if __name__ == "__main__":
    main()
