#!/usr/bin/env python3
"""UP6: Design does not use multi-AZ when user chose single-az.

Invariant
---------
When the user explicitly sets availability="single-az" in preferences.json,
the Design phase must NOT configure multi-AZ deployments. Specifically:
  - No aws_config.multi_az = true
  - No aws_config.availability_zones with more than 1 AZ

This validates that Design respects the "dev sizing unless specified" philosophy
and the user's explicit single-AZ preference.

Skill file reference
--------------------
  SKILL.md (line 11)
    "Dev sizing unless specified: Default to development-tier capacity
     (e.g., db.t4g.micro, single AZ). Upgrade only on user direction."

  references/phases/clarify/clarify-global.md
    Q3 (availability): user chooses between "multi-az" and "single-az".
    Default is "multi-az" for production workloads.

  references/phases/design/design-infra.md
    Design reads preferences.json availability constraint to determine
    whether to deploy across multiple AZs.

Examples
--------
  PASS: User chose "single-az". aws_config has no multi_az=true and
        availability_zones contains at most 1 AZ.

  FAIL: User chose "single-az" but database has multi_az=true — Design
        ignored the user preference and deployed multi-AZ anyway.

  FAIL: User chose "single-az" but subnets span ["us-west-2a", "us-west-2b"]
        — two AZs configured despite single-az preference.

  SKIP: availability is not "single-az" — check not applicable.
"""

import json
import sys
from pathlib import Path


def main():
    migration_dir = Path(sys.argv[1])
    design_file = migration_dir / "aws-design.json"
    prefs_file = migration_dir / "preferences.json"

    if not design_file.exists():
        print(json.dumps({"status": "fail", "details": "aws-design.json not found"}))
        return

    if not prefs_file.exists():
        print(json.dumps({"status": "fail", "details": "preferences.json not found"}))
        return

    prefs = json.loads(prefs_file.read_text(encoding="utf-8"))
    availability = prefs.get("design_constraints", {}).get("availability", {}).get("value")

    if availability != "single-az":
        print(json.dumps({"status": "skip", "details": f"Availability is '{availability}', not single-az"}))
        return

    data = json.loads(design_file.read_text(encoding="utf-8"))
    violations = []

    for cluster in data.get("clusters", []):
        for resource in cluster.get("resources", []):
            aws_config = resource.get("aws_config", {})
            if not isinstance(aws_config, dict):
                continue
            if aws_config.get("multi_az") is True:
                violations.append(f"{resource.get('gcp_address')}: multi_az=true")
            azs = aws_config.get("availability_zones", [])
            if isinstance(azs, list) and len(azs) > 1:
                violations.append(f"{resource.get('gcp_address')}: {len(azs)} AZs configured")

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
