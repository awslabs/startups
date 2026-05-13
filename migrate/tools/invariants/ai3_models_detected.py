#!/usr/bin/env python3
"""AI3: At least one model detected in ai-workload-profile.json.

Invariant
---------
When the app code discovery creates ai-workload-profile.json (AI confidence
>= 70%), the "models" array must contain at least one entry. An empty models
array means the profile was created but no actual AI models were identified,
which is contradictory — the confidence threshold should have prevented
profile creation.

Skill file reference
--------------------
  references/shared/schema-discover-ai.md (line 33)
    "models: Each distinct AI model/service detected, with evidence and
     capabilities."

  references/phases/discover/discover-app-code.md (line 3)
    "If AI confidence >= 70%, extracts detailed AI workload information and
     generates ai-workload-profile.json."

  references/phases/discover/discover-app-code.md (lines 93-100)
    Step 3: Flag AI Signals — defines the patterns that trigger model detection
    (OpenAI SDK imports, Vertex AI SDK, etc.).

Examples
--------
  PASS: {"models": [{"model_id": "gpt-4o", "service": "openai", ...}]}
        At least one model detected.

  FAIL: {"models": []}
        Profile exists but no models — contradicts the 70% confidence threshold.

  FAIL: ai-workload-profile.json not found (but this fixture expects it).
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
    models = data.get("models", [])

    if len(models) == 0:
        print(json.dumps({"status": "fail", "details": "No models detected in AI profile"}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
