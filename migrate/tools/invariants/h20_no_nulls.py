#!/usr/bin/env python3
"""H20: No null values in preferences.json design_constraints.

Invariant
---------
After the Clarify phase completes, every field in preferences.json
design_constraints must have a non-null value. Nulls indicate the Clarify
phase failed to resolve a question — either by collecting a user answer,
applying a documented default, or extracting from discovery data.

Skill file reference
--------------------
  references/phases/clarify/clarify.md (line 302)
    "Every design constraint must be resolved before Clarify completes.
     No null values are permitted in the final preferences.json."

  references/phases/clarify/clarify.md (lines 299-310 — preference schema)
    Each preference entry must have {value: <non-null>, chosen_by: <method>}.

Examples
--------
  PASS: {"target_region": {"value": "us-east-1", "chosen_by": "default"},
         "availability": {"value": "multi-az", "chosen_by": "user"}}
        All values are non-null.

  FAIL: {"target_region": {"value": null, "chosen_by": "default"}}
        value is null — Clarify failed to resolve this constraint.

  FAIL: {"availability": {"value": "multi-az", "chosen_by": null}}
        chosen_by is null — must specify how the value was determined.
"""

import json
import sys
from pathlib import Path


def find_nulls(obj, path="$"):
    """Recursively find null values, returning their paths."""
    nulls = []
    if obj is None:
        nulls.append(path)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            nulls.extend(find_nulls(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            nulls.extend(find_nulls(v, f"{path}[{i}]"))
    return nulls


def main():
    migration_dir = Path(sys.argv[1])
    prefs_file = migration_dir / "preferences.json"

    if not prefs_file.exists():
        print(json.dumps({"status": "fail", "details": "preferences.json not found"}))
        return

    data = json.loads(prefs_file.read_text(encoding="utf-8"))
    constraints = data.get("design_constraints", {})
    nulls = find_nulls(constraints, "$.design_constraints")

    if nulls:
        print(json.dumps({"status": "fail", "details": f"Null values at: {', '.join(nulls[:5])}"}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
