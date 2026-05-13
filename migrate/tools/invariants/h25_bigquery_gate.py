#!/usr/bin/env python3
"""H25: Every google_bigquery_* resource maps to 'Deferred — specialist engagement'.

Invariant
---------
The skill does NOT recommend a specific AWS analytics or warehouse service for
BigQuery. Any google_bigquery_* resource in aws-design.json must have
aws_service set to "Deferred — specialist engagement" (or similar containing
both "deferred" and "specialist"). The user is directed to their AWS account
team and/or a data analytics migration partner.

Skill file reference
--------------------
  SKILL.md (line 14)
    "BigQuery / google_bigquery_*: The skill does not recommend a specific AWS
     analytics or warehouse service. Design output uses 'Deferred — specialist
     engagement'."

  references/phases/design/design-infra.md (lines 164-165 — BigQuery specialist gate)
    "If gcp_type starts with google_bigquery_*, set aws_service to
     'Deferred — specialist engagement'. Do not apply Redshift, Athena, Glue,
     or EMR."

  references/phases/clarify/clarify.md (line 32)
    Clarify must surface the specialist advisory before Design if BigQuery is
    detected.

Examples
--------
  PASS: {"gcp_type": "google_bigquery_dataset", "aws_service": "Deferred — specialist engagement"}
        BigQuery resource correctly deferred.

  FAIL: {"gcp_type": "google_bigquery_dataset", "aws_service": "Amazon Redshift"}
        BigQuery resource mapped to a specific analytics service — violates the gate.

  PASS (vacuous): No google_bigquery_* resources in Design — check passes trivially.
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
            gcp_type = resource.get("gcp_type", "")
            if not gcp_type.startswith("google_bigquery_"):
                continue
            aws_service = resource.get("aws_service", "")
            if "deferred" not in aws_service.lower() or "specialist" not in aws_service.lower():
                violations.append(
                    f"{resource.get('gcp_address')}: mapped to '{aws_service}' instead of deferred specialist"
                )

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
