#!/usr/bin/env python3
"""Validate heroku-to-aws migration-report.html (thin stakeholder report).

Required sections: decision-summary, exec-costs, next-steps.
Conditional: what-if-scenarios when scenarios/index.json has ≥2 entries.
Footer must contain "draft for review".

Exit 0 on PASS, 1 on FAIL.

Usage:
  python3 validate-heroku-migration-report.py /path/to/migration-report.html \\
      --migration-dir "$MIGRATION_DIR"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_SECTION_IDS = [
    "decision-summary",
    "exec-costs",
    "next-steps",
]

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


def _normalize_money(text: str) -> str | None:
    """'$1,415/mo' -> '1415'; '$112' -> '112'. None when no dollar amount present.
    Cents are truncated (the artifacts store whole-dollar monthly figures)."""
    m = re.search(r"\$\s*([0-9][0-9,]*)(?:\.[0-9]+)?", text)
    return m.group(1).replace(",", "") if m else None


# data-cost-key anchor -> estimation-infra.json path. Heroku asserts the recommended
# AWS monthly (Balanced) figure only; the current-spend comparator is a follow-up
# (Heroku's current_costs key is not yet settled — heroku_monthly_baseline vs _estimated).
_COST_ANCHORS = {
    "aws_monthly_balanced": ("projected_costs", "aws_monthly_balanced"),
}
# Load-bearing key: when its JSON value exists AND exec-costs is present, the anchor
# MUST be present (a missing anchor is a FAIL, not a skip — otherwise an un-anchored
# wrong figure passes, the bug P1-C exists to catch).
_REQUIRED_COST_KEYS = ("aws_monthly_balanced",)

# Capture inner HTML up to the close tag so a figure wrapped in nested markup
# (<span data-cost-key=...><strong>$112</strong></span>) is read, not just a text node.
_ANCHOR_RE = re.compile(
    r'data-cost-key=["\']([a-z_]+)["\'][^>]*>(.*?)</', re.IGNORECASE | re.DOTALL
)


def _dig(d: dict, path: tuple[str, ...]):
    cur = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _validate_cost_figures(html: str, migration_dir: Path | None) -> list[str]:
    """Assert the report's cost figures match estimation-infra.json (P1-C).

    Fail direction:
    - No estimation-infra.json / corrupt / not a dict -> skip (fail open on absence).
    - aws_monthly_balanced present in JSON + exec-costs present -> its anchor MUST
      exist; a missing anchor FAILs (an un-anchored wrong figure must not pass).
    - Anchor present + JSON value present but rendered dollars differ -> FAIL.
    - Anchored element with a real JSON value but no $ rendered -> FAIL.
    - Non-numeric / non-whole-dollar JSON value -> FAIL (named), never a crash.
    - Unknown anchor key -> skip.
    """
    if migration_dir is None:
        return []
    est_path = migration_dir / "estimation-infra.json"
    if not est_path.is_file():
        return []
    try:
        est = json.loads(est_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []  # fail open on ambiguity: a corrupt estimate does not gate the report
    if not isinstance(est, dict):
        return []
    errors: list[str] = []
    seen_keys: set[str] = set()
    for match in _ANCHOR_RE.finditer(html):
        key = match.group(1).lower()
        path = _COST_ANCHORS.get(key)
        if path is None:
            continue
        seen_keys.add(key)
        expected = _dig(est, path)
        if expected is None:
            continue
        try:
            expected_dollars = str(int(expected))
        except (TypeError, ValueError):
            errors.append(
                f'estimation-infra.json {".".join(path)} is not a whole-dollar '
                f"number: {expected!r}"
            )
            continue
        rendered = _normalize_money(re.sub(r"<[^>]+>", "", match.group(2)))
        if rendered is None:
            errors.append(
                f'data-cost-key="{key}" element renders no dollar amount '
                f"(expected ${expected_dollars} from {'.'.join(path)})"
            )
            continue
        if expected_dollars != rendered:
            errors.append(
                f'cost figure mismatch: data-cost-key="{key}" renders "${rendered}" '
                f'but estimation-infra.json {".".join(path)} = ${expected_dollars}'
            )

    if _section_counts(html).get("exec-costs", 0) >= 1:
        for key in _REQUIRED_COST_KEYS:
            if key in seen_keys:
                continue
            path = _COST_ANCHORS[key]
            if _dig(est, path) is None:
                continue
            errors.append(
                f'missing data-cost-key="{key}" anchor in the report; cannot '
                f"confirm the rendered figure matches estimation-infra.json "
                f'{".".join(path)} (wrap that figure in '
                f'<span data-cost-key="{key}">...</span>)'
            )
    return errors


def validate(html: str, migration_dir: Path | None) -> list[str]:
    errors: list[str] = []
    counts = _section_counts(html)

    for sid in REQUIRED_SECTION_IDS:
        n = counts.get(sid, 0)
        if n == 0:
            errors.append(f'missing required <section id="{sid}">')
        elif n > 1:
            errors.append(f'duplicate <section id="{sid}"> ({n} occurrences)')

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

    errors.extend(_validate_cost_figures(html, migration_dir))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_path", type=Path)
    parser.add_argument("--migration-dir", type=Path, default=None)
    args = parser.parse_args()

    if not args.report_path.is_file():
        print(f"REPORT_FAIL | file={args.report_path} | reason=not_found", file=sys.stderr)
        return 1

    html = args.report_path.read_text(encoding="utf-8")
    errors = validate(html, args.migration_dir)
    if errors:
        print(f"REPORT_FAIL | file={args.report_path} | errors={len(errors)}", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    counts = _section_counts(html)
    optional = []
    if counts.get("what-if-scenarios", 0) >= 1:
        optional.append("what-if-scenarios")
    print(
        "REPORT_OK | structure=complete | sections="
        f"{len(REQUIRED_SECTION_IDS)}/{len(REQUIRED_SECTION_IDS)}"
        + (f" | optional={','.join(optional)}" if optional else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
