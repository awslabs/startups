#!/usr/bin/env python3
"""Layer 1 structural check: required-phrase presence scanner.

Validates that critical directives (FORBIDDEN blocks, CRITICAL rules, etc.)
still exist in prompt files. Catches the most dangerous regression: accidental
deletion of safety directives.

Usage:
    python tools/eval_check_phrases.py [--skill-dir PATH]

Exit codes:
    0 - All required phrases found
    1 - One or more required phrases missing
"""

import argparse
import json
import sys
from pathlib import Path

# Required phrases: each entry specifies a file (relative to skill dir) and
# a phrase that MUST appear in that file. If the phrase is missing, the check fails.
#
# These are the highest-value structural checks -- they guard against accidental
# deletion of safety directives that prevent the plugin from producing dangerous output.

REQUIRED_PHRASES = [
    # Discover phase scope boundaries
    {
        "file": "references/phases/discover/discover.md",
        "phrase": "FORBIDDEN",
        "description": "Discover phase FORBIDDEN block (scope boundary)",
        "source": "discover.md:180",
    },
    {
        "file": "references/phases/discover/discover-iac.md",
        "phrase": "FORBIDDEN",
        "description": "Discover-IAC FORBIDDEN block (scope boundary)",
        "source": "discover-iac.md:304",
    },
    {
        "file": "references/phases/discover/discover-app-code.md",
        "phrase": "FORBIDDEN",
        "description": "Discover-app-code FORBIDDEN block (scope boundary)",
        "source": "discover-app-code.md:361",
    },
    {
        "file": "references/phases/discover/discover-billing.md",
        "phrase": "FORBIDDEN",
        "description": "Discover-billing FORBIDDEN block (scope boundary)",
        "source": "discover-billing.md:120",
    },
    # Clarify phase scope boundary
    {
        "file": "references/phases/clarify/clarify.md",
        "phrase": "FORBIDDEN",
        "description": "Clarify phase FORBIDDEN block (scope boundary)",
        "source": "clarify.md:374",
    },
    # Design phase scope boundary
    {
        "file": "references/phases/design/design.md",
        "phrase": "FORBIDDEN",
        "description": "Design phase FORBIDDEN block (scope boundary)",
        "source": "design.md:89",
    },
    # Estimate phase scope boundaries
    {
        "file": "references/phases/estimate/estimate.md",
        "phrase": "FORBIDDEN",
        "description": "Estimate phase FORBIDDEN block (scope boundary)",
        "source": "estimate.md:122",
    },
    {
        "file": "references/phases/estimate/estimate-ai.md",
        "phrase": "FORBIDDEN",
        "description": "Estimate-AI FORBIDDEN block (scope boundary)",
        "source": "estimate-ai.md:209",
    },
    # BigQuery specialist gate
    {
        "file": "references/phases/design/design-infra.md",
        "phrase": "Deferred \u2014 specialist engagement",
        "description": "BigQuery specialist gate directive",
        "source": "design-infra.md:164-165",
    },
    # Security: no hardcoded credentials
    {
        "file": "references/phases/generate/generate-artifacts-infra.md",
        "phrase": "hardcoded credentials",
        "description": "No hardcoded credentials rule in generate-infra",
        "source": "generate-artifacts-infra.md:147",
    },
    # Security: no wildcard IAM
    {
        "file": "references/phases/generate/generate-artifacts-infra.md",
        "phrase": "wildcard",
        "description": "No wildcard IAM policy rule",
        "source": "generate-artifacts-infra.md:145",
    },
    # Security: dry-run default
    {
        "file": "references/phases/generate/generate-artifacts-scripts.md",
        "phrase": "dry-run",
        "description": "Scripts must default to dry-run mode",
        "source": "generate-artifacts-scripts.md:60-64",
    },
    # Discover: no AWS service names in outputs
    {
        "file": "references/phases/discover/discover.md",
        "phrase": "AWS service names",
        "description": "Discover must not mention AWS service names",
        "source": "discover.md:180-188",
    },
]


def check_phrases(skill_dir: Path) -> list[dict]:
    """Check all required phrases exist in their target files.

    Returns a list of results, one per phrase check.
    """
    results = []

    for entry in REQUIRED_PHRASES:
        file_path = skill_dir / entry["file"]
        result = {
            "file": entry["file"],
            "phrase": entry["phrase"],
            "description": entry["description"],
            "source": entry["source"],
        }

        if not file_path.exists():
            result["status"] = "fail"
            result["details"] = f"File not found: {file_path}"
        else:
            content = file_path.read_text(encoding="utf-8")
            if entry["phrase"] in content:
                result["status"] = "pass"
            else:
                result["status"] = "fail"
                result["details"] = (
                    f"Required phrase '{entry['phrase']}' not found in {entry['file']}"
                )

        results.append(result)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Layer 1: Required-phrase presence scanner"
    )
    parser.add_argument(
        "--skill-dir",
        type=Path,
        default=None,
        help="Path to the skill directory (default: auto-detect from repo root)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    # Auto-detect skill directory
    if args.skill_dir:
        skill_dir = args.skill_dir
    else:
        # Walk up from this script to find repo root
        repo_root = Path(__file__).resolve().parent.parent
        skill_dir = repo_root / "features" / "migration-to-aws" / "skills" / "gcp-to-aws"

    if not skill_dir.exists():
        print(f"Error: Skill directory not found: {skill_dir}", file=sys.stderr)
        sys.exit(1)

    results = check_phrases(skill_dir)

    # Summarize
    failures = [r for r in results if r["status"] == "fail"]
    passes = [r for r in results if r["status"] == "pass"]

    if args.json:
        output = {
            "check": "required_phrases",
            "total": len(results),
            "passed": len(passes),
            "failed": len(failures),
            "results": results,
        }
        print(json.dumps(output, indent=2))
    else:
        if failures:
            print(f"\n{'='*60}")
            print(f"PHRASE CHECK FAILED: {len(failures)} missing directive(s)")
            print(f"{'='*60}\n")
            for f in failures:
                print(f"  FAIL: {f['description']}")
                print(f"        {f.get('details', '')}")
                print(f"        Source: {f['source']}")
                print()
        else:
            print(f"Phrase check passed: {len(passes)}/{len(results)} directives present")

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
