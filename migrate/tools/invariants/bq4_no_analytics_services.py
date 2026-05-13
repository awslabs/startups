#!/usr/bin/env python3
"""BQ4/NEG6: No Athena, Glue, EMR, or Redshift in Design for BigQuery resources.

Invariant
---------
When google_bigquery_* resources appear in aws-design.json, their aws_service
must not contain any of the four forbidden analytics services: Athena, Glue,
EMR, or Redshift. The skill defers all BigQuery mapping to specialist
engagement — it never picks an AWS analytics stack.

Skill file reference
--------------------
  references/phases/estimate/estimate-infra.md (line 87)
    "Do not apply Athena, Redshift, Glue, or EMR rates as the plugin's
     'projected' analytics stack."

  references/phases/design/design-infra.md (lines 164-165)
    BigQuery specialist gate: all google_bigquery_* → "Deferred — specialist
    engagement".

  SKILL.md (line 14)
    "The skill does not recommend a specific AWS analytics or warehouse
     service [for BigQuery]."

Examples
--------
  PASS: {"gcp_type": "google_bigquery_dataset",
         "aws_service": "Deferred — specialist engagement"}

  FAIL: {"gcp_type": "google_bigquery_dataset",
         "aws_service": "Amazon Athena + AWS Glue"}
        Contains "athena" and "glue" — both forbidden for BigQuery.

  FAIL: {"gcp_type": "google_bigquery_table",
         "aws_service": "Amazon EMR"}
        EMR is forbidden for BigQuery resources.
"""

import json
import sys
from pathlib import Path

FORBIDDEN_SERVICES = ["athena", "glue", "emr", "redshift"]


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
            if not resource.get("gcp_type", "").startswith("google_bigquery_"):
                continue
            aws_service = resource.get("aws_service", "").lower()
            for forbidden in FORBIDDEN_SERVICES:
                if forbidden in aws_service:
                    violations.append(
                        f"{resource.get('gcp_address')}: mapped to '{resource.get('aws_service')}' (contains '{forbidden}')"
                    )

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
