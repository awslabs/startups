#!/usr/bin/env python3
"""NEG1: Auth resources (google_identity_platform_*) excluded from inventory.

Invariant
---------
Authentication resources (Firebase Auth, Identity Platform) are explicitly
excluded from classification, clustering, and migration. They must NOT appear
in gcp-resource-inventory.json at all. Users should keep their existing auth
provider — the skill does not recommend migrating to AWS Cognito or any AWS
auth service.

Skill file reference
--------------------
  references/clustering/terraform/classification-rules.md (lines 7-18)
    "Priority 0: Excluded Resources (Skip Entirely)"
    "These resource types are excluded from classification, clustering, and
     migration. Do not classify them as PRIMARY or SECONDARY. Do not create
     clusters for them. Do not include them in gcp-resource-inventory.json."

  references/clustering/terraform/classification-rules.md (line 13)
    "Third-party and GCP-adjacent authentication resources. Users should keep
     their existing auth provider — do not recommend migrating to AWS Cognito."

  references/clustering/terraform/classification-rules.md (line 18)
    "If encountered: log as 'Auth provider detected — excluded from migration
     scope. Keep your existing auth solution.' and skip."

  references/design-refs/fast-path.md (lines 67-68)
    "google_identity_platform_* | Auth provider — keep existing solution"
    "google_firebase_auth_*     | Auth provider — keep existing solution"

Examples
--------
  PASS: gcp-resource-inventory.json has 3 resources, none with type starting
        with "google_identity_platform_" or "google_firebase_auth_".

  FAIL: gcp-resource-inventory.json contains
        {"type": "google_identity_platform_config", "address": "..."}
        Auth resource incorrectly included in inventory.
"""

import json
import sys
from pathlib import Path

AUTH_PREFIXES = [
    "google_identity_platform_",
    "google_firebase_auth_",
]


def main():
    migration_dir = Path(sys.argv[1])
    inv_file = migration_dir / "gcp-resource-inventory.json"

    if not inv_file.exists():
        print(json.dumps({"status": "fail", "details": "gcp-resource-inventory.json not found"}))
        return

    data = json.loads(inv_file.read_text(encoding="utf-8"))
    violations = []

    for r in data.get("resources", []):
        rtype = r.get("type", "")
        for prefix in AUTH_PREFIXES:
            if rtype.startswith(prefix):
                violations.append(f"{r.get('address')}: auth resource in inventory ({rtype})")

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
