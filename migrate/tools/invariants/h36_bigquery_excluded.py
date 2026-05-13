#!/usr/bin/env python3
"""H36: BigQuery excluded from numeric cost totals.

Invariant
---------
If BigQuery resources exist in the Design output, they must NOT appear in
projected_costs line items with numeric dollar amounts. BigQuery costs are
unknown until the AWS account team defines the target analytics architecture,
so including them in totals would be misleading.

BigQuery resources should appear in a "deferred_services" or
"excluded_from_totals" section with reason "pending specialist engagement".

Skill file reference
--------------------
  references/phases/estimate/estimate-infra.md (lines 85-89)
    "For any resource where aws_service is 'Deferred — specialist engagement'
     OR gcp_type starts with google_bigquery_*:
     - Do not apply Athena, Redshift, Glue, or EMR rates.
     - Exclude these resources from Premium / Balanced / Optimized numeric totals.
     - In the user-facing summary, state that AWS analytics costs are unknown."

  SKILL.md (line 14)
    BigQuery handling: "Design output uses 'Deferred — specialist engagement';
     keep directing the user to their AWS account team."

Examples
--------
  PASS: No BigQuery resources in Design — check passes trivially (not applicable).

  PASS: BigQuery exists in Design but estimation has no BigQuery line items in
        projected_costs — costs correctly excluded.

  FAIL: projected_costs contains {"service": "BigQuery (Redshift equivalent)",
        "monthly_cost": 450.00} — BigQuery should never have a numeric cost.
"""

import json
import sys
from pathlib import Path


def has_bigquery(design_data):
    """Check if any BigQuery resources exist in the design."""
    for cluster in design_data.get("clusters", []):
        for resource in cluster.get("resources", []):
            if resource.get("gcp_type", "").startswith("google_bigquery_"):
                return True
    return False


def main():
    migration_dir = Path(sys.argv[1])
    design_file = migration_dir / "aws-design.json"
    est_file = migration_dir / "estimation-infra.json"

    if not design_file.exists() or not est_file.exists():
        print(json.dumps({"status": "pass"}))
        return

    design_data = json.loads(design_file.read_text(encoding="utf-8"))

    if not has_bigquery(design_data):
        print(json.dumps({"status": "pass"}))
        return

    est_data = json.loads(est_file.read_text(encoding="utf-8"))
    violations = []

    projected = est_data.get("projected_costs", {})
    for section_name, section in projected.items():
        if not isinstance(section, dict):
            continue
        items = section.get("items", section.get("line_items", []))
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("service", item.get("name", ""))).lower()
            if "bigquery" in name or "big_query" in name:
                cost = item.get("monthly_cost", item.get("cost"))
                if cost is not None and cost != 0 and cost != "Deferred":
                    violations.append(f"BigQuery in cost totals: {name} = {cost}")

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
