#!/usr/bin/env python3
"""Validate heroku-to-aws migration report HTML (thin stakeholder report).

Two modes, sharing the decision-core sections (see
skills/heroku-to-aws/references/shared/report-decision-core.md):

  full     (default) migration-report.html — decision-summary, exec-costs,
           next-steps required; decision-basis / what-if-scenarios conditional.
  decision decision-report.html — decision-summary, exec-costs required;
           decision-cta required instead of next-steps; decision-basis /
           what-if-scenarios conditional (same triggers as full mode).

Exit 0 on PASS, 1 on FAIL.

Usage:
  python3 validate-heroku-migration-report.py /path/to/migration-report.html \\
      --migration-dir "$MIGRATION_DIR"
  python3 validate-heroku-migration-report.py /path/to/decision-report.html \\
      --mode decision
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Required in both modes.
COMMON_REQUIRED_SECTION_IDS = [
    "decision-summary",
    "exec-costs",
]

# The one structural difference between modes: decision mode ends on a CTA
# pointing at Generate instead of the full report's next-steps list (which
# assumes MIGRATION_GUIDE.md / terraform/ already exist — they don't yet in
# decision mode).
MODE_REQUIRED_SECTION_ID = {
    "full": "next-steps",
    "decision": "decision-cta",
}

SECTION_OPEN = re.compile(
    r'<section\b[^>]*\bid=["\']([^"\']+)["\'][^>]*>',
    re.IGNORECASE,
)


def _section_counts(html: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in SECTION_OPEN.finditer(html):
        sid = match.group(1)
        counts[sid] = counts.get(sid, 0) + 1
    return counts


def validate(html: str, migration_dir: Path | None, mode: str = "full") -> list[str]:
    errors: list[str] = []
    counts = _section_counts(html)

    required = [*COMMON_REQUIRED_SECTION_IDS, MODE_REQUIRED_SECTION_ID[mode]]
    for sid in required:
        n = counts.get(sid, 0)
        if n == 0:
            errors.append(f'missing required <section id="{sid}">')
        elif n > 1:
            errors.append(f'duplicate <section id="{sid}"> ({n} occurrences)')

    # The other mode's terminal section must NOT appear — decision-report.html
    # must not carry a next-steps pointer into an execution pack that does not
    # exist yet, and migration-report.html should not carry the pre-execution
    # decision-cta once the real thing (next-steps) exists.
    other_mode = "decision" if mode == "full" else "full"
    other_terminal = MODE_REQUIRED_SECTION_ID[other_mode]
    if counts.get(other_terminal, 0) >= 1:
        errors.append(
            f'--mode {mode} report must not contain <section id="{other_terminal}"> '
            f"(that is the {other_mode}-mode terminal section)"
        )

    if "draft for review" not in html.lower():
        errors.append('footer must contain "draft for review" disclaimer')

    if migration_dir is not None:
        index_path = migration_dir / "scenarios" / "index.json"
        if index_path.is_file():
            try:
                index = json.loads(index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                index = None
            scenarios = (index or {}).get("scenarios") or []
            if len(scenarios) >= 2 and counts.get("what-if-scenarios", 0) < 1:
                errors.append(
                    'scenarios/index.json has ≥2 scenarios but no '
                    '<section id="what-if-scenarios">'
                )

    if mode == "decision":
        # Decision mode is pre-execution: these must not exist yet on disk (the
        # report-decision-core.md contract). Only checked when a migration dir
        # was supplied — the fixture/unit-test path may validate HTML in
        # isolation without one.
        if migration_dir is not None:
            if (migration_dir / "terraform").exists():
                errors.append("decision mode: terraform/ must not exist on a decide run")
            if any(migration_dir.glob("generation-*.json")):
                errors.append(
                    "decision mode: generation-*.json must not exist on a decide run"
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_path", type=Path)
    parser.add_argument("--migration-dir", type=Path, default=None)
    parser.add_argument(
        "--mode",
        choices=["full", "decision"],
        default="full",
        help="full = migration-report.html (default); decision = decision-report.html",
    )
    args = parser.parse_args()

    if not args.report_path.is_file():
        print(f"REPORT_FAIL | file={args.report_path} | reason=not_found", file=sys.stderr)
        return 1

    html = args.report_path.read_text(encoding="utf-8")
    errors = validate(html, args.migration_dir, args.mode)
    if errors:
        print(f"REPORT_FAIL | file={args.report_path} | mode={args.mode} | errors={len(errors)}", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    counts = _section_counts(html)
    optional = []
    if counts.get("what-if-scenarios", 0) >= 1:
        optional.append("what-if-scenarios")
    if counts.get("decision-basis", 0) >= 1:
        optional.append("decision-basis")
    required_count = len(COMMON_REQUIRED_SECTION_IDS) + 1
    print(
        "REPORT_OK | structure=complete | mode="
        f"{args.mode} | sections={required_count}/{required_count}"
        + (f" | optional={','.join(optional)}" if optional else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
