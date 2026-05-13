#!/usr/bin/env python3
"""H10: Every SECONDARY resource has secondary_role and serves fields.

Invariant
---------
In gcp-resource-inventory.json, every resource with classification "SECONDARY"
must include "secondary_role" (string — what role this resource plays, e.g.,
"identity", "network_path", "secret") and "serves" (array — list of PRIMARY
resource addresses this SECONDARY supports).

Skill file reference
--------------------
  references/phases/discover/discover-iac.md (lines 241-274 — inventory schema)
    Defines the resource object schema. SECONDARY resources require these fields
    to establish the dependency graph for clustering.

  references/clustering/terraform/classification-rules.md
    Defines SECONDARY classification: resources that exist only to support a
    PRIMARY resource (e.g., service accounts, IAM bindings, secrets).

Examples
--------
  PASS: {"address": "google_service_account.api_sa", "classification": "SECONDARY",
         "secondary_role": "identity", "serves": ["google_cloud_run_v2_service.api"]}
        Both secondary_role and serves present.

  FAIL: {"address": "google_service_account.api_sa", "classification": "SECONDARY",
         "serves": ["google_cloud_run_v2_service.api"]}
        Missing "secondary_role" field.

  FAIL: {"address": "google_secret_manager_secret.db_url", "classification": "SECONDARY",
         "secondary_role": "secret"}
        Missing "serves" field — must list which PRIMARY resource(s) it supports.
"""

import json
import sys
from pathlib import Path


def main():
    migration_dir = Path(sys.argv[1])
    inv_file = migration_dir / "gcp-resource-inventory.json"

    if not inv_file.exists():
        print(json.dumps({"status": "fail", "details": "gcp-resource-inventory.json not found"}))
        return

    data = json.loads(inv_file.read_text(encoding="utf-8"))
    violations = []

    for r in data.get("resources", []):
        if r.get("classification") != "SECONDARY":
            continue
        addr = r.get("address", "unknown")
        for field in ("secondary_role", "serves"):
            if field not in r:
                violations.append(f"{addr}: missing '{field}'")

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:10])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
