#!/usr/bin/env python3
"""BQ3: No Redshift in Design output for BigQuery resources.

Invariant
---------
When google_bigquery_* resources appear in aws-design.json, their aws_service
must NEVER be "Amazon Redshift" or any Redshift variant. BigQuery resources
are deferred to specialist engagement — the skill does not pick an AWS
analytics target.

Skill file reference
--------------------
  references/phases/estimate/estimate-infra.md (line 87)
    "Do not apply Athena, Redshift, Glue, or EMR rates as the plugin's
     'projected' analytics stack."

  references/phases/design/design-infra.md (lines 164-165)
    BigQuery specialist gate: set aws_service to "Deferred — specialist
    engagement" for all google_bigquery_* resources.

Examples
--------
  PASS: {"gcp_type": "google_bigquery_dataset",
         "aws_service": "Deferred — specialist engagement"}
        Correctly deferred, no Redshift.

  FAIL: {"gcp_type": "google_bigquery_dataset",
         "aws_service": "Amazon Redshift Serverless"}
        Redshift recommended for BigQuery — violates specialist gate.

  PASS (vacuous): No google_bigquery_* resources in Design.
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
            if not resource.get("gcp_type", "").startswith("google_bigquery_"):
                continue
            aws_service = resource.get("aws_service", "").lower()
            if "redshift" in aws_service:
                violations.append(
                    f"{resource.get('gcp_address')}: mapped to '{resource.get('aws_service')}'"
                )

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
