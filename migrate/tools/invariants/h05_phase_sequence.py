#!/usr/bin/env python3
"""H05: No later phase is completed while an earlier phase is not.

Invariant
---------
The six phases must complete in strict order: discover → clarify → design →
estimate → generate → feedback. If phase N is "completed", every phase before
it must also be "completed". This prevents impossible states like Design
completing before Clarify.

Skill file reference
--------------------
  SKILL.md (lines 37-49 — State Machine table)
    Each row specifies a precondition: e.g., Design requires clarify == "completed".
  SKILL.md (line 102)
    "Status values: pending → in_progress → completed. Never goes backward."

Examples
--------
  PASS: discover=completed, clarify=completed, design=completed,
        estimate=in_progress, generate=pending, feedback=pending
        All completed phases precede all incomplete phases.

  FAIL: discover=completed, clarify=pending, design=completed
        Design is completed but Clarify is still pending — violates ordering.

  FAIL: discover=completed, clarify=completed, design=pending,
        estimate=completed
        Estimate completed before Design — impossible per state machine.
"""

import json
import sys
from pathlib import Path

PHASE_ORDER = ["discover", "clarify", "design", "estimate", "generate", "feedback"]


def main():
    migration_dir = Path(sys.argv[1])
    status_file = migration_dir / ".phase-status.json"

    if not status_file.exists():
        print(json.dumps({"status": "fail", "details": ".phase-status.json not found"}))
        return

    data = json.loads(status_file.read_text(encoding="utf-8"))
    phases = data.get("phases", {})

    seen_incomplete = None
    for phase in PHASE_ORDER:
        status = phases.get(phase, "pending")
        if status != "completed" and seen_incomplete is None:
            seen_incomplete = phase
        elif status == "completed" and seen_incomplete is not None:
            print(json.dumps({
                "status": "fail",
                "details": f"'{phase}' is completed but earlier phase '{seen_incomplete}' is not",
            }))
            return

    print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
