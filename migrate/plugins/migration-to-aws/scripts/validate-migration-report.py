#!/usr/bin/env python3
"""Validate migration-report.html completeness after Generate phase.

Checks required section IDs, minimum appendix content, and artifact-derived
cost markers. Exit 0 on PASS, 1 on FAIL. Used by generate-artifacts-report.md
Step 4 and CI.

Usage:
  python3 validate-migration-report.py /path/to/migration-report.html
  python3 validate-migration-report.py /path/to/migration-report.html \\
      --estimation-infra /path/to/estimation-infra.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_SECTION_IDS = [
    "decision-summary",
    "exec-services",
    "exec-costs",
    "exec-timeline",
    "exec-risks",
    "appendix-services",
    "appendix-costs",
    "appendix-steps",
    "appendix-artifacts",
]

OPTIONAL_SECTION_IDS = [
    "exec-tco",
    "exec-architecture",
    "exec-security-teaser",
    "appendix-ai",
    "appendix-config",
    "appendix-security",
    "appendix-security-gap",
    "appendix-assumptions",
]

FORBIDDEN_PATTERNS = [
    (r"\[placeholder\]", "placeholder text"),
    (r"\bTODO\b", "TODO marker"),
]

# Appendix must not be a stub that only links to JSON files.
APPENDIX_STUB_PATTERNS = [
    re.compile(
        r'<section[^>]*id="appendix-costs"[^>]*>.*?Full artifacts:\s*<code>estimation-infra\.json</code>',
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(
        r'<section[^>]*id="appendix-services"[^>]*>\s*<p>\s*See\s*<code>aws-design\.json</code>',
        re.DOTALL | re.IGNORECASE,
    ),
]

MIN_TABLE_ROWS = {
    "appendix-costs": 3,
    "appendix-services": 2,
    "appendix-steps": 2,
}


def _section_html(html: str, section_id: str) -> str | None:
    pattern = re.compile(
        rf'<section[^>]*\bid="{re.escape(section_id)}"[^>]*>(.*?)</section>',
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(html)
    return match.group(1) if match else None


def _count_table_rows(section_html: str) -> int:
    tbody = re.search(r"<tbody>(.*?)</tbody>", section_html, re.DOTALL | re.IGNORECASE)
    if not tbody:
        return 0
    return len(re.findall(r"<tr\b", tbody.group(1), re.IGNORECASE))


def _section_content_depth(section_id: str, section_html: str) -> int:
    rows = _count_table_rows(section_html)
    if section_id == "appendix-services":
        clusters = len(re.findall(r'class="cluster-block"', section_html))
        return max(rows, clusters)
    if section_id == "appendix-steps":
        phases = len(re.findall(r"<h3>Phase\s+\d", section_html, re.IGNORECASE))
        return max(rows, phases)
    return rows


def _has_guardduty_or_baseline(html: str, estimation_infra: dict | None) -> tuple[bool, str]:
    if re.search(r"GuardDuty", html, re.IGNORECASE):
        return True, "GuardDuty mentioned in report"
    if estimation_infra:
        breakdown = estimation_infra.get("projected_costs", {}).get("breakdown", {})
        baseline = breakdown.get("security_baseline")
        if baseline and estimation_infra.get("projected_costs", {}).get("aws_monthly_balanced"):
            mid = baseline.get("mid")
            if mid is not None and str(mid) in html.replace(",", ""):
                return True, "security_baseline mid cost present"
    return False, "missing GuardDuty or security_baseline cost from estimation-infra.json"


def validate_report(html: str, estimation_infra: dict | None = None) -> list[str]:
    errors: list[str] = []

    for section_id in REQUIRED_SECTION_IDS:
        if not re.search(rf'\bid="{re.escape(section_id)}"', html, re.IGNORECASE):
            errors.append(f"missing required section id={section_id}")

    for pattern, label in FORBIDDEN_PATTERNS:
        if re.search(pattern, html, re.IGNORECASE):
            errors.append(f"forbidden content: {label}")

    for section_id, min_rows in MIN_TABLE_ROWS.items():
        section = _section_html(html, section_id)
        if section is None:
            continue
        depth = _section_content_depth(section_id, section)
        if depth < min_rows:
            errors.append(
                f"appendix section id={section_id} has insufficient content ({depth}), need >= {min_rows}"
            )

    for stub in APPENDIX_STUB_PATTERNS:
        if stub.search(html):
            errors.append("appendix appears to be a stub (links to JSON only) — expand per generate-artifacts-report.md")

    if "draft for review" not in html.lower():
        errors.append('footer must contain "draft for review" disclaimer')

    if estimation_infra and estimation_infra.get("projected_costs", {}).get("breakdown", {}).get("security_baseline"):
        ok, msg = _has_guardduty_or_baseline(html, estimation_infra)
        if not ok:
            errors.append(msg)

    if re.search(r'\bid="appendix-ai"', html, re.IGNORECASE):
        if not re.search(r'\bid="exec-tco"', html, re.IGNORECASE):
            errors.append(
                'when appendix-ai present, include section id="exec-tco" with combined infra+AI TCO'
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate migration-report.html")
    parser.add_argument("report_path", type=Path, help="Path to migration-report.html")
    parser.add_argument(
        "--estimation-infra",
        type=Path,
        default=None,
        help="Optional estimation-infra.json for cost/security cross-checks",
    )
    args = parser.parse_args()

    if not args.report_path.is_file():
        print(f"REPORT_FAIL | file={args.report_path} | reason=not_found", file=sys.stderr)
        return 1

    html = args.report_path.read_text(encoding="utf-8")
    estimation_infra = None
    if args.estimation_infra and args.estimation_infra.is_file():
        estimation_infra = json.loads(args.estimation_infra.read_text(encoding="utf-8"))

    errors = validate_report(html, estimation_infra)
    if errors:
        print("REPORT_FAIL | migration-report.html", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    optional_present = [sid for sid in OPTIONAL_SECTION_IDS if re.search(rf'\bid="{sid}"', html, re.I)]
    print(
        "REPORT_OK | sections="
        + str(len(REQUIRED_SECTION_IDS))
        + f"/{len(REQUIRED_SECTION_IDS)}"
        + (f" | optional={','.join(optional_present)}" if optional_present else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
