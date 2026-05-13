#!/usr/bin/env python3
"""AI4: overall_confidence >= 0.7 (threshold for AI profile creation).

Invariant
---------
If ai-workload-profile.json exists, its summary.overall_confidence must be
>= 0.70 (70%). This is the creation threshold — the Discover phase should
NOT create the profile if confidence is below 70%. A profile with confidence
< 70% means the threshold gate was bypassed.

Skill file reference
--------------------
  references/phases/discover/discover-app-code.md (line 3)
    "If AI confidence >= 70%, extracts detailed AI workload information and
     generates ai-workload-profile.json."

  references/phases/discover/discover-app-code.md (line 6)
    "If this file exits without producing artifacts (no source code found,
     or AI confidence < 70%), report to the parent orchestrator."

  references/shared/schema-discover-ai.md (line 26-27)
    "overall_confidence: Combined detection confidence from all signals."

Examples
--------
  PASS: {"summary": {"overall_confidence": 0.95}}
        Well above the 70% threshold.

  PASS: {"summary": {"overall_confidence": 0.70}}
        Exactly at threshold — allowed.

  FAIL: {"summary": {"overall_confidence": 0.55}}
        Below threshold — profile should not have been created.
"""

import json
import sys
from pathlib import Path


def main():
    migration_dir = Path(sys.argv[1])
    profile_file = migration_dir / "ai-workload-profile.json"

    if not profile_file.exists():
        print(json.dumps({"status": "fail", "details": "ai-workload-profile.json not found"}))
        return

    data = json.loads(profile_file.read_text(encoding="utf-8"))
    confidence = data.get("summary", {}).get("overall_confidence", 0)

    if confidence < 0.7:
        print(json.dumps({
            "status": "fail",
            "details": f"overall_confidence is {confidence}, below 0.7 threshold",
        }))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
