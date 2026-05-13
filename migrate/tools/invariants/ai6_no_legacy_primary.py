#!/usr/bin/env python3
"""AI6: No Legacy models recommended as primary when Active alternative exists.

Invariant
---------
Legacy models (>90 days to EOL) may appear in comparison tables with an
annotation like "(Legacy — EOL YYYY-MM-DD)", but they must NEVER be used as
the "recommended_model" or "Best Bedrock Match" when an Active alternative
exists. All legacy models listed below have Active successors.

Legacy models as of April 2026 (from ai-model-lifecycle.md):
  - Claude 3.5 Sonnet v2   (EOL Jul 30, 2026) → successor: Claude Sonnet 4.5/4.6
  - Nova Premier v1         (EOL Sep 14, 2026) → successor: Nova 2 Pro
  - Nova Canvas v1          (EOL Sep 30, 2026) → successor: Nova Canvas v2
  - Nova Reel v1            (EOL Sep 30, 2026) → successor: Nova Reel v2

Skill file reference
--------------------
  references/shared/ai-model-lifecycle.md (lines 38, 46)
    "Legacy models with >90 days until EOL may appear in comparison tables
     with annotation, but never as recommended_model or 'Best Bedrock Match'
     when an Active alternative exists."

  references/shared/ai-model-lifecycle.md (lines 63, 88-90)
    Legacy model table and annotation rules.

  references/design-refs/ai-openai-to-bedrock.md (line 11)
    "Do not recommend Legacy models as primary selections for new migrations."

  references/shared/pricing-cache.md (line 627)
    "Nova Canvas v1 is Legacy (EOL Sep 30, 2026). Do not recommend for new
     migrations."

Examples
--------
  PASS: recommended_model = "Claude Sonnet 4.6" — Active model.

  FAIL: recommended_model = "Claude 3.5 Sonnet v2" — Legacy, has Active
        successor (Claude Sonnet 4.5/4.6).

  PASS: "Claude 3.5 Sonnet v2 (Legacy — EOL Jul 30, 2026)" appears in
        comparison notes but NOT as recommended_model — acceptable.
"""

import json
import sys
from pathlib import Path

LEGACY_FRAGMENTS = [
    "claude-3-5-sonnet",
    "claude-3.5-sonnet",
    "nova-premier-v1",
    "nova-canvas-v1",
    "nova-reel-v1",
]


def main():
    migration_dir = Path(sys.argv[1])

    est_ai = migration_dir / "estimation-ai.json"
    if not est_ai.exists():
        print(json.dumps({"status": "pass"}))
        return

    data = json.loads(est_ai.read_text(encoding="utf-8"))
    violations = []

    for mapping in data.get("model_mappings", data.get("mappings", [])):
        if not isinstance(mapping, dict):
            continue
        recommended = str(mapping.get("recommended_model", "")).lower()
        for fragment in LEGACY_FRAGMENTS:
            if fragment.lower() in recommended:
                violations.append(
                    f"Legacy model '{fragment}' used as recommended_model"
                )

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
