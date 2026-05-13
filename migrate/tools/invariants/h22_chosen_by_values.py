#!/usr/bin/env python3
"""H22: chosen_by is one of the valid values.

Invariant
---------
Every preference entry's "chosen_by" field must be one of exactly four values:
  - "user"      — user explicitly answered the question
  - "default"   — no user input; documented default applied
  - "extracted" — value was extracted from discovery data (e.g., billing region)
  - "derived"   — value was computed from other preferences or discovery context

Skill file reference
--------------------
  references/phases/clarify/clarify.md (lines 299-310 — preference schema)
    Defines the four valid chosen_by values and when each is used.

  references/phases/clarify/clarify-global.md
    Shows how each question resolves to a chosen_by value depending on whether
    the user answers, skips, or the answer is extracted from discovery data.

Examples
--------
  PASS: {"target_region": {"value": "us-east-1", "chosen_by": "default"},
         "availability": {"value": "multi-az", "chosen_by": "user"}}
        Both chosen_by values are in the valid set.

  FAIL: {"target_region": {"value": "us-east-1", "chosen_by": "auto"}}
        "auto" is not a valid chosen_by value.

  FAIL: {"target_region": {"value": "us-east-1", "chosen_by": "system"}}
        "system" is not a valid chosen_by value — use "default" or "derived".
"""

import json
import sys
from pathlib import Path

VALID_CHOSEN_BY = {"user", "default", "extracted", "derived"}


def main():
    migration_dir = Path(sys.argv[1])
    prefs_file = migration_dir / "preferences.json"

    if not prefs_file.exists():
        print(json.dumps({"status": "fail", "details": "preferences.json not found"}))
        return

    data = json.loads(prefs_file.read_text(encoding="utf-8"))
    constraints = data.get("design_constraints", {})
    violations = []

    for key, entry in constraints.items():
        if not isinstance(entry, dict):
            continue
        chosen_by = entry.get("chosen_by")
        if chosen_by not in VALID_CHOSEN_BY:
            violations.append(f"{key}: chosen_by='{chosen_by}' not in {sorted(VALID_CHOSEN_BY)}")

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:10])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
