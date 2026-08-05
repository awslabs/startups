#!/usr/bin/env python3
"""Model-ID drift lint (CI).

Fails when a known-bad Bedrock model ID appears in the plugin outside the
files whose JOB is to catalog it. Two classes today:

1. EOL-as-target: `claude-sonnet-4-20250514` — Claude Sonnet 4 is excluded
   (EOL Oct 14, 2026 per ai-model-lifecycle.md). It may appear in the model
   catalog / pricing rate card (that's what a lifecycle table is for), but
   nowhere else: an example or script carrying it becomes a rewrite target.

2. Fabricated hybrids: `claude-sonnet-4-6-<date>` / `claude-opus-4-8-<date>`
   — Sonnet 4.6 and Opus 4.8 IDs are UNDATED; the dated forms graft a newer
   model name onto an older model's date stamp and have never existed. One
   allowlisted exception: the resolve-bedrock-model-id helper, whose input
   example is intentionally invalid (repairing broken IDs is its purpose).

Grep-once hygiene doesn't stick; this makes the sweep permanent. Extend
BAD_PATTERNS when a model is EOL'd. Stdlib only. Exit 0 = clean.
"""

import re
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
EXTS = {".md", ".py", ".json", ".ts", ".tf", ".sh", ".template"}

BAD_PATTERNS = [
    (
        re.compile(r"claude-sonnet-4-20250514"),
        "Claude Sonnet 4 (EOL Oct 14, 2026, excluded) used outside the model catalog",
        {  # allowlist: catalog files whose job is recording the model + its EOL status
            "skills/gcp-to-aws/references/shared/pricing-cache.md",
            "skills/gcp-to-aws/references/shared/ai-model-lifecycle.md",
        },
    ),
    (
        re.compile(r"claude-(?:sonnet-4-6|opus-4-8)-\d{8}"),
        "fabricated dated ID — Sonnet 4.6 / Opus 4.8 Bedrock IDs are undated; this form never existed",
        {  # allowlist: the broken-ID-repair helper's intentionally-invalid example
            "skills/llm-to-bedrock/references/helpers/resolve-bedrock-model-id/resolve-bedrock-model-id.md",
        },
    ),
]

SELF = Path(__file__).resolve()


def main() -> int:
    failures = []
    for path in sorted(PLUGIN.rglob("*")):
        if not path.is_file() or path.suffix not in EXTS or path.resolve() == SELF:
            continue
        rel = str(path.relative_to(PLUGIN))
        if "node_modules" in rel:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern, why, allow in BAD_PATTERNS:
            if rel in allow:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    failures.append(f"{rel}:{i}: {why}")
    if failures:
        print(f"model-id lint: {len(failures)} problem(s)", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("model-id lint: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
