#!/usr/bin/env python3
"""H21: Every preference entry has value and chosen_by fields.

Invariant
---------
Each entry in preferences.json design_constraints must be a dict containing
at minimum "value" (the resolved answer) and "chosen_by" (how it was determined).
These two fields are the contract consumed by the Design and Estimate phases.

Skill file reference
--------------------
  references/phases/clarify/clarify.md (lines 299-310 — preference schema)
    Defines the preference entry format: {value: <any>, chosen_by: <method>}.
    Design reads value directly; chosen_by is metadata for traceability.

  references/phases/design/design-infra.md
    Design phase reads preferences.json and applies design_constraints.*.value
    to determine AWS service configuration.

Examples
--------
  PASS: {"target_region": {"value": "us-east-1", "chosen_by": "default"},
         "availability": {"value": "multi-az", "chosen_by": "user"}}
        Every entry has both fields.

  FAIL: {"target_region": {"value": "us-east-1"}}
        Missing "chosen_by" — Design can still read the value but traceability
        is lost.

  FAIL: {"target_region": "us-east-1"}
        Entry is a bare string, not a dict — violates the schema entirely.
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
    violations = []

    for key, entry in constraints.items():
        if not isinstance(entry, dict):
            violations.append(f"{key}: not a dict")
            continue
        for field in ("value", "chosen_by"):
            if field not in entry:
                violations.append(f"{key}: missing '{field}'")

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:10])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
