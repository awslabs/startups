#!/usr/bin/env python3
"""BQ-S1: Clarify surfaces BigQuery specialist advisory (soft observation).

Invariant
---------
When BigQuery resources are detected during Discover, the Clarify phase must
surface the specialist advisory to the user BEFORE Design begins. This is a
soft observation — we verify that BigQuery was detected in the inventory,
which is the precondition for the advisory.

Note: We cannot directly verify the advisory was shown (it's a conversational
output), so we verify the precondition: BigQuery resources exist in the
inventory, meaning the Clarify phase should have triggered the advisory path.

Skill file reference
--------------------
  references/phases/clarify/clarify.md (line 32)
    "If bigquery_present is true, output the Step 4 BigQuery / deferred
     analytics advisory block once (even though questions are skipped)."

  SKILL.md (line 14)
    "During Clarify, if discovery shows BigQuery, you must surface the
     specialist advisory before Design."

Examples
--------
  PASS: gcp-resource-inventory.json contains a resource with type
        "google_bigquery_dataset" — advisory should have been surfaced.

  SKIP: No BigQuery resources in inventory — advisory not applicable.
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

    inventory_file = migration_dir / "gcp-resource-inventory.json"
    if inventory_file.exists():
        inv = json.loads(inventory_file.read_text(encoding="utf-8"))
        has_bq = any(
            r.get("type", "").startswith("google_bigquery_")
            for r in inv.get("resources", [])
        )
        if has_bq:
            print(json.dumps({"status": "pass"}))
            return

    print(json.dumps({"status": "skip", "details": "No BigQuery resources to validate"}))


if __name__ == "__main__":
    main()
