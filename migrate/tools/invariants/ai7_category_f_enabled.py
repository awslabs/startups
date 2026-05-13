#!/usr/bin/env python3
"""AI7: Category F (AI/Bedrock) questions enabled when AI workload detected.

Invariant
---------
When the ai-workload-openai fixture is used, AI workloads are present (the app
code imports openai SDK). The Clarify phase must enable Category F (AI/Bedrock
questions Q14-Q22). This is verified by checking that AI questions appear in
either questions_asked or questions_defaulted in preferences.json metadata —
they must NOT all be in questions_skipped_not_applicable.

Skill file reference
--------------------
  references/phases/clarify/clarify.md (line 18 — Category Reference table)
    "clarify-ai.md | F — AI/Bedrock | Q14-Q22 | ai-workload-profile.json exists"
    Category F fires when the AI profile exists.

  references/phases/clarify/clarify-ai.md
    Contains questions Q14-Q22 covering: AI provider preference, model quality
    requirements, latency targets, context window needs, cost priority, etc.

Examples
--------
  PASS: metadata.questions_defaulted includes "Q14", "Q15", etc.
        Category F was enabled and questions were resolved (defaulted).

  PASS: metadata.questions_asked includes "Q16", "Q18"
        Category F was enabled and user answered some questions.

  FAIL: metadata.questions_skipped_not_applicable includes ALL of Q14-Q22
        Category F was skipped despite AI workload being detected.
"""

import json
import sys
from pathlib import Path


def main():
    migration_dir = Path(sys.argv[1])
    prefs_file = migration_dir / "preferences.json"

    if not prefs_file.exists():
        print(json.dumps({"status": "fail", "details": "preferences.json not found"}))
        return

    data = json.loads(prefs_file.read_text(encoding="utf-8"))
    metadata = data.get("metadata", {})

    category_e = metadata.get("category_e_enabled", False)

    ai_questions = {f"Q{i}" for i in range(14, 23)}
    asked = set(metadata.get("questions_asked", []))
    defaulted = set(metadata.get("questions_defaulted", []))
    skipped_na = set(metadata.get("questions_skipped_not_applicable", []))

    ai_engaged = bool(ai_questions & (asked | defaulted))
    ai_all_skipped = ai_questions.issubset(skipped_na)

    if category_e or ai_engaged:
        print(json.dumps({"status": "pass"}))
    elif ai_all_skipped:
        print(json.dumps({
            "status": "fail",
            "details": "AI questions Q14-Q22 all skipped as not applicable, but AI workload was detected",
        }))
    else:
        print(json.dumps({
            "status": "fail",
            "details": "Category F not enabled despite AI workload detection",
        }))


if __name__ == "__main__":
    main()
