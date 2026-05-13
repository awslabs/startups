#!/usr/bin/env python3
"""H28: confidence values are only 'deterministic' or 'inferred'.

Invariant
---------
Every resource mapping in aws-design.json must have a "confidence" field set
to exactly one of two values:
  - "deterministic" — 1:1 mapping from the fast-path table (e.g., Cloud Run → Fargate)
  - "inferred" — mapping required rubric evaluation with multiple candidates

No other values (e.g., "high", "low", "medium", numeric scores) are allowed
in the Design output.

Skill file reference
--------------------
  references/phases/design/design-infra.md (lines 164-165)
    Design output schema specifies confidence as an enum: deterministic | inferred.

  references/design-refs/fast-path.md
    Lists all deterministic (1:1) mappings. Resources not in this table get
    "inferred" after rubric evaluation.

  references/design-refs/index.md
    Describes the rubric evaluation process that produces "inferred" mappings.

Examples
--------
  PASS: {"gcp_address": "google_cloud_run_v2_service.api",
         "aws_service": "Fargate", "confidence": "deterministic"}
        Cloud Run → Fargate is a documented fast-path mapping.

  PASS: {"gcp_address": "google_compute_network.main",
         "aws_service": "VPC", "confidence": "inferred"}
        VPC mapping used rubric evaluation.

  FAIL: {"gcp_address": "google_cloud_run_v2_service.api",
         "aws_service": "Fargate", "confidence": "high"}
        "high" is not a valid value — must be "deterministic" or "inferred".
"""

import json
import sys
from pathlib import Path

VALID_CONFIDENCE = {"deterministic", "inferred"}


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
            confidence = resource.get("confidence")
            if confidence not in VALID_CONFIDENCE:
                violations.append(
                    f"{resource.get('gcp_address')}: confidence='{confidence}'"
                )

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
