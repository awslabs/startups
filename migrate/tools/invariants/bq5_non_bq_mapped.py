#!/usr/bin/env python3
"""BQ5: Non-BigQuery resources still get normal mappings (not Deferred).

Invariant
---------
The BigQuery specialist gate must NOT "leak" into non-BigQuery resources.
Resources that are not google_bigquery_* must receive a concrete AWS service
mapping (e.g., "Fargate", "RDS Aurora PostgreSQL"), not "Deferred — specialist
engagement". The deferral is exclusively for BigQuery.

Skill file reference
--------------------
  references/phases/design/design-infra.md (lines 164-165)
    The specialist gate applies only to google_bigquery_* resources.
    All other resources follow the normal fast-path or rubric mapping.

  references/design-refs/fast-path.md
    Lists deterministic mappings for non-BigQuery resources (Cloud Run → Fargate,
    Cloud SQL → Aurora, etc.).

Examples
--------
  PASS: {"gcp_type": "google_cloud_run_v2_service",
         "aws_service": "Fargate"}
        Non-BigQuery resource gets a concrete mapping.

  FAIL: {"gcp_type": "google_cloud_run_v2_service",
         "aws_service": "Deferred — specialist engagement"}
        Cloud Run should never be deferred — it has a deterministic fast-path.

  PASS (vacuous): All resources are google_bigquery_* — nothing to check.
"""

import json
import sys
from pathlib import Path


def main():
    migration_dir = Path(sys.argv[1])
    design_file = migration_dir / "aws-design.json"

    if not design_file.exists():
        print(json.dumps({"status": "fail", "details": "aws-design.json not found"}))
        return

    data = json.loads(design_file.read_text(encoding="utf-8"))
    violations = []

    for cluster in data.get("clusters", []):
        for resource in cluster.get("resources", []):
            if resource.get("gcp_type", "").startswith("google_bigquery_"):
                continue
            aws_service = resource.get("aws_service", "")
            if "deferred" in aws_service.lower():
                violations.append(
                    f"{resource.get('gcp_address')}: non-BigQuery resource mapped to '{aws_service}'"
                )

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
