#!/usr/bin/env python3
"""H34: migration_cost_considerations.categories contains no human labor costs.

Invariant
---------
The skill must never present human labor, professional services, engineering
hours, training, or other people-time work as dollar estimates or cost
categories. The categories array in estimation-infra.json may contain vendor
charges (e.g., "Data transfer (GCP egress fees)") but must never contain
human labor terms.

This is a core philosophy rule: the skill estimates infrastructure costs, not
professional services costs.

Skill file reference
--------------------
  SKILL.md (line 12)
    "No human one-time migration costs: Do not present human labor, professional
     services, or people-time work as dollar estimates or 'one-time migration
     cost' budget categories. Vendor charges grounded in data (for example GCP
     data transfer egress in the infra estimate when billing exists) are allowed."

  references/phases/estimate/estimate-infra.md (line 173)
    "GCP data transfer egress fees (if estimated) are vendor one-time charges
     excluded from recurring ROI calculations — not human migration costs."

  references/phases/estimate/estimate-ai.md (line 90)
    "Populate migration_cost_considerations.categories as an empty array [].
     Use note to state that human costs are intentionally excluded."

Examples
--------
  PASS: {"categories": []}
        Empty array — no cost categories at all (typical for IaC-only).

  PASS: {"categories": ["Data transfer (GCP egress fees based on migration volume)"]}
        Vendor charge — allowed because it's grounded in billing data.

  FAIL: {"categories": ["Professional services engagement ($50K-$100K)"]}
        Human labor cost — violates the "no human one-time migration costs" rule.

  FAIL: {"categories": ["Training cost for AWS certifications"]}
        People-time work — not allowed as a cost category.
"""

import json
import sys
from pathlib import Path

FORBIDDEN_TERMS = [
    "human labor",
    "professional services",
    "consulting",
    "engineering hours",
    "people-time",
    "staff cost",
    "one-time migration cost",
    "training cost",
    "discovery effort",
    "design effort",
]


def main():
    migration_dir = Path(sys.argv[1])
    est_file = migration_dir / "estimation-infra.json"

    if not est_file.exists():
        print(json.dumps({"status": "fail", "details": "estimation-infra.json not found"}))
        return

    data = json.loads(est_file.read_text(encoding="utf-8"))
    categories = data.get("migration_cost_considerations", {}).get("categories", [])

    violations = []
    for cat in categories:
        cat_lower = cat.lower()
        for term in FORBIDDEN_TERMS:
            if term in cat_lower:
                violations.append(f"'{cat}' contains forbidden term '{term}'")

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
