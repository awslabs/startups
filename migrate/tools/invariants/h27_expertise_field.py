#!/usr/bin/env python3
"""H27: Every resource in aws-design.json has human_expertise_required (boolean).

Invariant
---------
Every resource mapping in aws-design.json must include "human_expertise_required"
as a boolean field. This flag indicates whether the migration requires human
review beyond what the skill can automate (e.g., BigQuery → specialist,
complex stateful migrations). The Design phase sets this based on the confidence
level and service complexity.

Skill file reference
--------------------
  references/phases/design/design-infra.md (lines 164-165)
    Design output schema requires human_expertise_required for every mapped
    resource. Set to true for deferred/specialist resources, false for
    deterministic fast-path mappings.

  references/design-refs/fast-path.md
    Deterministic mappings (Cloud Run → Fargate, Cloud SQL → Aurora, etc.)
    set human_expertise_required to false.

Examples
--------
  PASS: {"gcp_address": "google_cloud_run_v2_service.api",
         "aws_service": "Fargate", "human_expertise_required": false}
        Boolean field present.

  FAIL: {"gcp_address": "google_cloud_run_v2_service.api",
         "aws_service": "Fargate"}
        Missing human_expertise_required field entirely.

  FAIL: {"gcp_address": "google_bigquery_dataset.analytics",
         "aws_service": "Deferred", "human_expertise_required": "yes"}
        Field is a string, not a boolean — must be true or false.

Note: aws-design.json uses nested structure: {"clusters": [{"resources": [...]}]}.
      This handler walks all clusters to check every resource.
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
    clusters = data.get("clusters", [])

    violations = []
    for cluster in clusters:
        for resource in cluster.get("resources", []):
            addr = resource.get("gcp_address", "unknown")
            if "human_expertise_required" not in resource:
                violations.append(f"{addr}: missing human_expertise_required")
            elif not isinstance(resource["human_expertise_required"], bool):
                violations.append(
                    f"{addr}: human_expertise_required is {type(resource['human_expertise_required']).__name__}, not bool"
                )

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
