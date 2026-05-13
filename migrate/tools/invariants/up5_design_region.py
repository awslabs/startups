#!/usr/bin/env python3
"""UP5: Design aws_region matches user-chosen target region.

Invariant
---------
When the user explicitly sets target_region in preferences.json (chosen_by="user"),
the Design phase must honor that choice. Every cluster in aws-design.json must
have aws_region matching the user's chosen region. If the user chose "us-west-2",
no cluster should use "us-east-1" or any other region.

This validates the end-to-end flow: Clarify captures user preference → Design
reads preferences.json → Design output reflects the preference.

Skill file reference
--------------------
  references/phases/clarify/clarify.md (lines 342-358)
    preferences.json schema: design_constraints.target_region.value is consumed
    by the Design phase.

  references/phases/design/design-infra.md
    Design reads preferences.json and applies design_constraints.target_region.value
    as the aws_region for all cluster mappings.

  references/phases/clarify/clarify-global.md
    Q1 (target region): user selects an AWS region. Default is us-east-1.

Examples
--------
  PASS: User chose "us-west-2". All clusters in aws-design.json have
        aws_region="us-west-2".

  FAIL: User chose "us-west-2" but cluster "compute_cloudrun_001" has
        aws_region="us-east-1" — Design ignored the user preference.

  SKIP: No target_region in preferences (shouldn't happen after Clarify).
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

    prefs_file = migration_dir / "preferences.json"
    if not prefs_file.exists():
        print(json.dumps({"status": "fail", "details": "preferences.json not found"}))
        return

    prefs = json.loads(prefs_file.read_text(encoding="utf-8"))
    user_region = prefs.get("design_constraints", {}).get("target_region", {}).get("value")

    if not user_region:
        print(json.dumps({"status": "skip", "details": "No target_region in preferences"}))
        return

    data = json.loads(design_file.read_text(encoding="utf-8"))
    wrong_regions = []

    for cluster in data.get("clusters", []):
        aws_region = cluster.get("aws_region", "")
        if aws_region and aws_region != user_region:
            wrong_regions.append(f"{cluster.get('cluster_id')}: aws_region='{aws_region}'")

    if wrong_regions:
        print(json.dumps({
            "status": "fail",
            "details": f"Expected '{user_region}': " + "; ".join(wrong_regions[:5]),
        }))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
