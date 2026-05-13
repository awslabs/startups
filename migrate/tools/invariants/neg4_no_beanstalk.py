#!/usr/bin/env python3
"""NEG4: No Elastic Beanstalk in Design output.

Invariant
---------
AWS Elastic Beanstalk must never appear as an aws_service mapping in
aws-design.json. The skill uses a re-platform approach that maps to
modern AWS container/serverless services (Fargate, EKS, Lambda, App Runner),
not legacy PaaS. Elastic Beanstalk is an older deployment model that doesn't
match GCP's container-native approach.

Skill file reference
--------------------
  SKILL.md (line 10)
    "Re-platform by default: Select AWS services that match GCP workload
     types (e.g., Cloud Run → Fargate, Cloud SQL → RDS)."

  references/design-refs/fast-path.md (lines 37-56)
    Fast-path mapping table — Elastic Beanstalk does not appear as a target
    for any GCP resource type.

  references/design-refs/compute.md
    Compute mapping rubric — evaluates ECS Fargate, EKS, Lambda, App Runner.
    Elastic Beanstalk is not a candidate in the rubric.

Examples
--------
  PASS: Cloud Run maps to "Fargate" — correct modern target.

  FAIL: Cloud Run maps to "Elastic Beanstalk" — legacy PaaS, not in the
        skill's mapping table or rubric.

  FAIL: Any GCP resource maps to "AWS Elastic Beanstalk" — not a valid target.
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
            aws_service = resource.get("aws_service", "").lower()
            if "beanstalk" in aws_service:
                violations.append(
                    f"{resource.get('gcp_address')}: mapped to '{resource.get('aws_service')}'"
                )

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
