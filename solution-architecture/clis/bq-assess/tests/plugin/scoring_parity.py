#!/usr/bin/env python3
"""Verify scoring-rules.md matches scorer.py complexity-point constants.

Parses the complexity flags and point values from both:
- src/bq_assess/scoring/complexity.py  (source of truth)
- features/bq-assess/skills/bq-assess/references/scoring-rules.md

Fails if any flag or point value has drifted.

Validates: Requirement 8.5, Property 9
"""

import re
import sys
from pathlib import Path


def parse_scorer_py(path: Path) -> dict[str, int]:
    """Extract flag -> points mapping from scorer.py.

    Matches the pattern used in ComplexityScorer.score():
        points += N
        flags.append("flag_name")
    """
    content = path.read_text()
    # The scorer consistently uses: points += N\n ... flags.append("name")
    # We match across possible whitespace/comments between the two lines.
    pattern = r'points\s*\+=\s*(\d+)\s*\n\s*flags\.append\("(\w+)"\)'
    matches = re.findall(pattern, content)

    flags: dict[str, int] = {}
    for points_str, flag_name in matches:
        flags[flag_name] = int(points_str)

    return flags


def parse_scoring_rules_md(path: Path) -> dict[str, int]:
    """Extract flag -> points mapping from scoring-rules.md table rows.

    Matches table rows like:
        | `deeply_nested_structs` | ... | **+2** |
        | `array_of_struct`       | ... | +1     |
    """
    content = path.read_text()
    flags: dict[str, int] = {}

    for line in content.splitlines():
        # Match: | `flag_name` | ... | [**]+N[**] |
        match = re.search(
            r"\|\s*`(\w+)`\s*\|.*?\|\s*\*{0,2}\+?(\d+)\*{0,2}\s*\|", line
        )
        if match:
            flag_name = match.group(1)
            points = int(match.group(2))
            flags[flag_name] = points

    return flags


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    scorer_path = repo_root / "src" / "bq_assess" / "scoring" / "complexity.py"
    rules_path = (
        repo_root
        / "features"
        / "bq-assess"
        / "skills"
        / "bq-assess"
        / "references"
        / "scoring-rules.md"
    )

    if not scorer_path.exists():
        print(f"FAIL: scorer.py not found at {scorer_path}")
        return 1
    if not rules_path.exists():
        print(f"FAIL: scoring-rules.md not found at {rules_path}")
        return 1

    scorer_flags = parse_scorer_py(scorer_path)
    rules_flags = parse_scoring_rules_md(rules_path)

    if not scorer_flags:
        print("FAIL: No flags parsed from scorer.py — regex may need updating")
        return 1
    if not rules_flags:
        print("FAIL: No flags parsed from scoring-rules.md — regex may need updating")
        return 1

    errors = 0

    # Check all scorer flags are documented in scoring-rules.md
    for flag, points in sorted(scorer_flags.items()):
        if flag not in rules_flags:
            print(f"FAIL: Flag '{flag}' in scorer.py but missing from scoring-rules.md")
            errors += 1
        elif rules_flags[flag] != points:
            print(
                f"FAIL: Flag '{flag}' has {points} points in scorer.py "
                f"but {rules_flags[flag]} in scoring-rules.md"
            )
            errors += 1
        else:
            print(f"PASS: {flag} = +{points}")

    # Check for extra flags in scoring-rules.md not in scorer.py
    for flag in sorted(rules_flags):
        if flag not in scorer_flags:
            print(f"FAIL: Flag '{flag}' in scoring-rules.md but not in scorer.py")
            errors += 1

    print()
    if errors > 0:
        print(f"FAILED: {errors} parity error(s)")
        return 1

    print(f"ALL {len(scorer_flags)} FLAGS MATCH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
