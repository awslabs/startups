#!/usr/bin/env python3
"""NEG3: No Lightsail in Design output.

Invariant
---------
AWS Lightsail must never appear as an aws_service mapping in aws-design.json.
The skill follows a "re-platform by default" philosophy, selecting AWS services
that match GCP workload types at the same tier (e.g., Cloud Run → Fargate,
not Cloud Run → Lightsail). Lightsail is a simplified service that doesn't
match the operational model of any GCP compute resource.

Skill file reference
--------------------
  SKILL.md (line 10)
    "Re-platform by default: Select AWS services that match GCP workload
     types (e.g., Cloud Run → Fargate, Cloud SQL → RDS)."

  references/design-refs/fast-path.md (lines 37-56)
    Fast-path mapping table — Lightsail does not appear as a target for any
    GCP resource type.

  references/design-refs/compute.md
    Compute mapping rubric — evaluates ECS Fargate, EKS, Lambda, App Runner.
    Lightsail is not a candidate in the rubric.

Examples
--------
  PASS: Cloud Run maps to "Fargate" — correct re-platform target.

  FAIL: Cloud Run maps to "Amazon Lightsail" — wrong tier, Lightsail is a
        simplified service not suitable for containerized microservices.

  FAIL: Any resource maps to "Lightsail Containers" — not in the rubric.
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
            if "lightsail" in aws_service:
                violations.append(
                    f"{resource.get('gcp_address')}: mapped to '{resource.get('aws_service')}'"
                )

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
