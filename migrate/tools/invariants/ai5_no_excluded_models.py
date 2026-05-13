#!/usr/bin/env python3
"""AI5: No excluded (EOL <=90 days) models recommended as primary.

Invariant
---------
Models within 90 days of their end-of-life date must NOT appear in any
recommendation or "Best Bedrock Match" column. A migration takes weeks or
months — recommending a model that will be unavailable before go-live is
harmful. Excluded models may still exist in the pricing cache for reference
but must be marked "excluded".

Excluded models as of April 2026 (from ai-model-lifecycle.md):
  - Claude 3.7 Sonnet     (EOL Apr 28, 2026 — 9 days)
  - Claude Opus 4          (EOL May 31, 2026 — 42 days)
  - Claude 3.5 Haiku       (EOL Jun 19, 2026 — 61 days)
  - Titan Image Gen v2     (EOL Jun 30, 2026 — 72 days)
  - Llama 3.2 all sizes    (EOL Jul 7, 2026 — 79 days)
  - Llama 3.1 405B         (EOL Jul 7, 2026 — 79 days)

Skill file reference
--------------------
  references/shared/ai-model-lifecycle.md (lines 31-34)
    "Models within 90 days of their EOL date must be excluded from all
     recommendation and comparison tables."

  references/shared/ai-model-lifecycle.md (lines 44-46)
    Decision tree: days_to_eol <= 90 → Exclusion zone → Remove from
    recommendation/comparison tables.

  references/shared/ai-model-lifecycle.md (lines 57-62)
    Table of excluded models with exact EOL dates.

  references/design-refs/ai-openai-to-bedrock.md (line 11)
    "Do not recommend Legacy models as primary selections for new migrations."

Examples
--------
  PASS: estimation-ai.json recommends "Claude Sonnet 4.6" — Active model.

  FAIL: estimation-ai.json recommends "Claude 3.5 Haiku" — excluded (EOL Jun 19).

  FAIL: aws-design.json contains "Llama 3.2 90B" as a mapping — excluded.
"""

import json
import sys
from pathlib import Path

EXCLUDED_FRAGMENTS = [
    "claude-3-7-sonnet",
    "claude-3.7-sonnet",
    "claude-opus-4-2025",
    "claude-3-5-haiku",
    "claude-3.5-haiku",
    "titan-image-generator-v2",
    "llama3-2-",
    "llama-3.2-",
    "llama3-1-405b",
    "llama-3.1-405b",
]


def main():
    migration_dir = Path(sys.argv[1])

    for filename in ("estimation-ai.json", "aws-design.json"):
        filepath = migration_dir / filename
        if not filepath.exists():
            continue

        content = filepath.read_text(encoding="utf-8").lower()
        violations = []

        for fragment in EXCLUDED_FRAGMENTS:
            if fragment.lower() in content:
                violations.append(f"Found excluded model fragment '{fragment}' in {filename}")

        if violations:
            print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
            return

    print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
