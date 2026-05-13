#!/usr/bin/env python3
"""H09: Every PRIMARY resource has depth and tier fields.

Invariant
---------
In gcp-resource-inventory.json, every resource with classification "PRIMARY"
must include both a "depth" field (integer — creation order in the dependency
graph) and a "tier" field (string — functional category like "compute",
"database", "storage").

Skill file reference
--------------------
  references/phases/discover/discover-iac.md (lines 241-274 — inventory schema)
    Defines the resource object schema. PRIMARY resources require depth and tier
    because they drive the clustering algorithm and Design phase mapping.

  references/clustering/terraform/depth-calculation.md
    Explains how depth is computed from Terraform dependency edges.

  references/clustering/terraform/classification-rules.md
    Defines PRIMARY vs SECONDARY classification and required fields per class.

Examples
--------
  PASS: {"address": "google_cloud_run_v2_service.api", "classification": "PRIMARY",
         "tier": "compute", "depth": 2, ...}
        Both depth and tier present.

  FAIL: {"address": "google_sql_database_instance.db", "classification": "PRIMARY",
         "tier": "database"}
        Missing "depth" field.

  FAIL: {"address": "google_cloud_run_v2_service.api", "classification": "PRIMARY",
         "depth": 2}
        Missing "tier" field.
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
        if r.get("classification") != "PRIMARY":
            continue
        addr = r.get("address", "unknown")
        for field in ("depth", "tier"):
            if field not in r:
                violations.append(f"{addr}: missing '{field}'")

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:10])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
