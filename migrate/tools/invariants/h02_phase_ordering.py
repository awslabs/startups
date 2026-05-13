#!/usr/bin/env python3
"""H02: Phase statuses only progress forward (pending -> in_progress -> completed).

Invariant
---------
Every phase status in .phase-status.json must be one of the three valid values:
"pending", "in_progress", or "completed". The state machine never allows a phase
to move backward (e.g., from "completed" back to "in_progress").

Skill file reference
--------------------
  SKILL.md (lines 73, 102)
    Line 73: "If any phases.* value is not in {pending, in_progress, completed}, STOP."
    Line 102: "Status values: pending → in_progress → completed. Never goes backward."

Examples
--------
  PASS: {"discover": "completed", "clarify": "in_progress", "design": "pending"}
        All statuses are valid enum values.

  FAIL: {"discover": "done", "clarify": "in_progress"}
        "done" is not a valid status — must be "completed".

  FAIL: {"discover": "skipped", "clarify": "pending"}
        "skipped" is not a valid status.
"""

import json
import sys
from pathlib import Path

VALID_STATUSES = ["pending", "in_progress", "completed"]


def main():
    migration_dir = Path(sys.argv[1])
    status_file = migration_dir / ".phase-status.json"

    if not status_file.exists():
        print(json.dumps({"status": "fail", "details": ".phase-status.json not found"}))
        return

    data = json.loads(status_file.read_text(encoding="utf-8"))
    phases = data.get("phases", {})

    violations = []
    for phase, status in phases.items():
        if status not in VALID_STATUSES:
            violations.append(f"{phase}: invalid status '{status}'")

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations)}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
