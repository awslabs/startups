#!/usr/bin/env python3
"""UP1: At least one preference has chosen_by 'user'.

Invariant
---------
In the user-preferences fixture, the pre-seeded preferences.json contains
entries with chosen_by="user" (target_region, availability, cutover_strategy).
After the Clarify phase completes, at least one preference must retain
chosen_by="user" — proving that user answers are preserved and not overwritten
by defaults.

Skill file reference
--------------------
  references/phases/clarify/clarify.md (lines 299-310)
    Preference schema: each entry has {value, chosen_by}. chosen_by="user"
    indicates the user explicitly answered the question.

  references/phases/clarify/clarify-global.md
    Question flow: when user provides an answer, chosen_by is set to "user".
    When skipped, it falls back to "default".

Examples
--------
  PASS: {"target_region": {"value": "us-west-2", "chosen_by": "user"},
         "availability": {"value": "single-az", "chosen_by": "user"}}
        Two preferences have chosen_by="user".

  FAIL: All entries have chosen_by="default" — no user choices preserved.
        This would mean Clarify ignored the pre-seeded user answers.
"""

import json
import sys
from pathlib import Path


def main():
    migration_dir = Path(sys.argv[1])
    prefs_file = migration_dir / "preferences.json"

    if not prefs_file.exists():
        print(json.dumps({"status": "fail", "details": "preferences.json not found"}))
        return

    data = json.loads(prefs_file.read_text(encoding="utf-8"))
    constraints = data.get("design_constraints", {})

    user_choices = [
        k for k, v in constraints.items()
        if isinstance(v, dict) and v.get("chosen_by") == "user"
    ]

    if user_choices:
        print(json.dumps({"status": "pass"}))
    else:
        print(json.dumps({
            "status": "fail",
            "details": "No preference has chosen_by='user'",
        }))


if __name__ == "__main__":
    main()
