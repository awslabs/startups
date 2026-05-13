#!/usr/bin/env python3
"""AI-S1: GPT-4o maps to a Bedrock model (soft observation).

Invariant
---------
When the source app uses OpenAI GPT-4o, the AI estimation should map it to
an Amazon Bedrock model (e.g., Claude Sonnet 4.6, Nova Lite). The mapping
should not keep GPT-4o as-is on AWS — the migration should propose a Bedrock
alternative with pricing comparison.

This is a soft observation, not a hard invariant — the specific Bedrock model
chosen may vary depending on user preferences (cost vs quality).

Skill file reference
--------------------
  references/design-refs/ai-openai-to-bedrock.md (lines 24-35)
    GPT-4o model mapping table showing Bedrock alternatives:
    "GPT-4o | $2.50/$10.00 | Claude Sonnet 4.6 | $3.00/$15.00"

  references/phases/estimate/estimate-ai.md
    AI estimation produces model_mappings with recommended_model targeting
    Bedrock model IDs.

Examples
--------
  PASS: estimation-ai.json contains both "gpt-4o" and "bedrock" references.

  FAIL: estimation-ai.json mentions "gpt-4o" but no Bedrock mapping.

  SKIP: estimation-ai.json doesn't exist (not an AI migration).
"""

import json
import sys
from pathlib import Path


def main():
    migration_dir = Path(sys.argv[1])
    est_ai = migration_dir / "estimation-ai.json"

    if not est_ai.exists():
        print(json.dumps({"status": "skip", "details": "estimation-ai.json not found"}))
        return

    content = est_ai.read_text(encoding="utf-8").lower()

    if "gpt-4o" in content and "bedrock" in content:
        print(json.dumps({"status": "pass"}))
    elif "gpt-4o" in content:
        print(json.dumps({"status": "fail", "details": "GPT-4o found but no Bedrock mapping"}))
    else:
        print(json.dumps({"status": "skip", "details": "GPT-4o not found in estimation"}))


if __name__ == "__main__":
    main()
