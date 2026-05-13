#!/usr/bin/env python3
"""NEG2: No Cognito in Design output.

Invariant
---------
AWS Cognito must never appear as an aws_service mapping in aws-design.json.
Auth resources are excluded from migration scope entirely (see NEG1). Even
if an auth resource somehow leaked into the inventory, Design must not
recommend Cognito as the target.

Skill file reference
--------------------
  references/clustering/terraform/classification-rules.md (line 13)
    "Third-party and GCP-adjacent authentication resources. Users should keep
     their existing auth provider — do not recommend migrating to AWS Cognito
     or any AWS auth service."

  references/design-refs/fast-path.md (lines 67-68)
    "google_identity_platform_* | Auth provider — keep existing solution,
     do not migrate to AWS Cognito or any AWS auth"

Examples
--------
  PASS: No resource in aws-design.json has aws_service containing "Cognito".

  FAIL: {"gcp_address": "google_identity_platform_config.auth",
         "aws_service": "Amazon Cognito"}
        Auth mapped to Cognito — violates exclusion rule.

  FAIL: {"gcp_address": "google_firebase_auth.config",
         "aws_service": "Cognito User Pool"}
        Firebase Auth mapped to Cognito — violates exclusion rule.
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
            if "cognito" in aws_service:
                violations.append(
                    f"{resource.get('gcp_address')}: mapped to '{resource.get('aws_service')}'"
                )

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
