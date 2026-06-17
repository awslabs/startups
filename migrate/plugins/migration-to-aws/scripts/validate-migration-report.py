#!/usr/bin/env python3
"""Validate migration-report.html completeness after Generate phase.

Checks required section IDs, TOC anchor integrity, minimum appendix content,
and artifact-derived cost markers. Exit 0 on PASS, 1 on FAIL.

Usage:
  python3 validate-migration-report.py /path/to/migration-report.html
  python3 validate-migration-report.py report.html \\
      --estimation-infra estimation-infra.json \\
      --estimation-ai estimation-ai.json

Script location: this file lives at
  migrate/plugins/migration-to-aws/scripts/validate-migration-report.py
Agents should invoke it via Path(__file__) resolution or:
  python3 "$(dirname ...)/scripts/validate-migration-report.py" ...
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Plugin root: migrate/plugins/migration-to-aws/
PLUGIN_ROOT = Path(__file__).resolve().parent.parent

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

MIN_CONTENT_DEPTH = {
    "appendix-costs": 3,
    "appendix-services": 2,
    "appendix-steps": 2,
}

SECTION_OPEN = re.compile(
    r"<section\b[^>]*\bid=(['\"])([^'\"]+)\1",
    re.IGNORECASE,
)

# NOTE: _section_html uses non-greedy match to first </section>. This assumes
# sections are NOT nested. Do not nest <section> elements in migration reports.


def plugin_script_path() -> Path:
    """Return absolute path to this validator (for agent invocation)."""
    return Path(__file__).resolve()


def _section_html(html: str, section_id: str) -> str | None:
    pattern = re.compile(
        rf"<section\b[^>]*\bid=\"{re.escape(section_id)}\"[^>]*>(.*?)</section>",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(html)
    return match.group(1) if match else None


def _section_id_counts(html: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in SECTION_OPEN.finditer(html):
        sid = match.group(2)
        counts[sid] = counts.get(sid, 0) + 1
    return counts


def _validate_required_sections(html: str) -> list[str]:
    errors: list[str] = []
    counts = _section_id_counts(html)
    for section_id in REQUIRED_SECTION_IDS:
        n = counts.get(section_id, 0)
        if n == 0:
            errors.append(f"missing required <section id=\"{section_id}\">")
        elif n > 1:
            errors.append(f"duplicate <section id=\"{section_id}\"> ({n} occurrences)")
    return errors


def _toc_hrefs(html: str) -> list[str]:
    nav_match = re.search(
        r"<nav\b[^>]*\bclass=[\"'][^\"']*toc[^\"']*[\"'][^>]*>(.*?)</nav>",
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not nav_match:
        return []
    return re.findall(r'href="#([^"]+)"', nav_match.group(1), re.IGNORECASE)


def _validate_toc(html: str) -> list[str]:
    errors: list[str] = []
    hrefs = _toc_hrefs(html)
    if not hrefs:
        return errors  # TOC optional if nav.toc absent; spec requires it in generated reports

    section_ids = set(_section_id_counts(html).keys())
    for href in hrefs:
        if href not in section_ids:
            errors.append(f"TOC broken link href=\"#{href}\" — no matching <section id=\"{href}\">")

    # Every TOC target must be reachable; also warn on orphan required sections not in TOC
    for section_id in REQUIRED_SECTION_IDS:
        if section_id in section_ids and section_id not in hrefs and hrefs:
            errors.append(
                f"TOC missing link to required section id=\"{section_id}\" "
                f"(add <a href=\"#{section_id}\">)"
            )
    return errors


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


def _security_scoped_html(html: str) -> str:
    chunks: list[str] = []
    for sid in ("appendix-security", "appendix-costs", "exec-security-teaser"):
        part = _section_html(html, sid)
        if part:
            chunks.append(part)
    return "\n".join(chunks)


def _dollar_amount_present(amount: float | int, text: str) -> bool:
    """True when a dollar-formatted value appears in text with numeric boundaries."""
    normalized = text.replace(",", "")
    v = float(amount)
    if v == int(v):
        i = int(v)
        patterns = [
            rf"(?<![0-9.])\${i}(?:\.00)?(?![0-9])",
            rf"(?<![0-9.])\${i}\.0(?![0-9])",
        ]
    else:
        whole, frac = f"{v:.2f}".split(".")
        patterns = [rf"(?<![0-9.])\${whole}\.{frac}(?![0-9])"]
    return any(re.search(p, normalized) for p in patterns)


def _has_guardduty_or_baseline(html: str, estimation_infra: dict | None) -> tuple[bool, str]:
    scope = _security_scoped_html(html)
    if not scope:
        return False, "missing security content in appendix-security or appendix-costs sections"

    if re.search(r"GuardDuty", scope, re.IGNORECASE):
        return True, ""

    if not estimation_infra:
        return False, "missing GuardDuty mention in security/cost appendix sections"

    breakdown = estimation_infra.get("projected_costs", {}).get("breakdown", {})
    baseline = breakdown.get("security_baseline")
    if not baseline:
        return True, ""  # no baseline in estimate — nothing to cross-check

    components = baseline.get("components") or {}
    for _key, val in components.items():
        if val is not None and float(val) > 0 and _dollar_amount_present(val, scope):
            return True, ""

    return False, (
        "appendix-security/appendix-costs must mention GuardDuty or include dollar-formatted "
        "security_baseline component costs from estimation-infra.json "
        "(e.g. GuardDuty $13.00, CloudTrail $1.50)"
    )


def validate_report(
    html: str,
    estimation_infra: dict | None = None,
    estimation_ai: dict | None = None,
    *,
    require_toc: bool = True,
) -> list[str]:
    errors: list[str] = []

    errors.extend(_validate_required_sections(html))

    if require_toc:
        if not _toc_hrefs(html):
            errors.append('missing <nav class="toc"> with href="#section-id" links')
        errors.extend(_validate_toc(html))

    for pattern, label in FORBIDDEN_PATTERNS:
        if re.search(pattern, html, re.IGNORECASE):
            errors.append(f"forbidden content: {label}")

    for section_id, min_depth in MIN_CONTENT_DEPTH.items():
        section = _section_html(html, section_id)
        if section is None:
            continue
        depth = _section_content_depth(section_id, section)
        if depth < min_depth:
            errors.append(
                f"appendix section id={section_id} has insufficient content ({depth}), "
                f"need >= {min_depth}"
            )

    for stub in APPENDIX_STUB_PATTERNS:
        if stub.search(html):
            errors.append(
                "appendix appears to be a stub (links to JSON only) — "
                "expand per generate-artifacts-report.md"
            )

    if "draft for review" not in html.lower():
        errors.append('footer must contain "draft for review" disclaimer')

    if estimation_infra and estimation_infra.get("projected_costs", {}).get("breakdown", {}).get(
        "security_baseline"
    ):
        ok, msg = _has_guardduty_or_baseline(html, estimation_infra)
        if not ok:
            errors.append(msg)

    # Combined TCO required only when BOTH estimate artifacts exist (not AI-only runs)
    if estimation_infra is not None and estimation_ai is not None:
        counts = _section_id_counts(html)
        if counts.get("exec-tco", 0) != 1:
            errors.append(
                'when both estimation-infra.json and estimation-ai.json exist, '
                'include exactly one <section id="exec-tco"> with combined infra+AI TCO'
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate migration-report.html")
    parser.add_argument("report_path", type=Path, help="Path to migration-report.html")
    parser.add_argument("--estimation-infra", type=Path, default=None)
    parser.add_argument("--estimation-ai", type=Path, default=None)
    parser.add_argument(
        "--no-require-toc",
        action="store_true",
        help="Skip TOC requirement (for minimal test fixtures)",
    )
    args = parser.parse_args()

    if not args.report_path.is_file():
        print(f"REPORT_FAIL | file={args.report_path} | reason=not_found", file=sys.stderr)
        return 1

    html = args.report_path.read_text(encoding="utf-8")

    estimation_infra = None
    if args.estimation_infra and args.estimation_infra.is_file():
        estimation_infra = json.loads(args.estimation_infra.read_text(encoding="utf-8"))

    estimation_ai = None
    if args.estimation_ai and args.estimation_ai.is_file():
        estimation_ai = json.loads(args.estimation_ai.read_text(encoding="utf-8"))

    errors = validate_report(
        html,
        estimation_infra,
        estimation_ai,
        require_toc=not args.no_require_toc,
    )
    if errors:
        print("REPORT_FAIL | migration-report.html", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    counts = _section_id_counts(html)
    optional_present = [sid for sid in OPTIONAL_SECTION_IDS if counts.get(sid, 0) >= 1]
    print(
        "REPORT_OK | structure=complete | sections="
        + str(len(REQUIRED_SECTION_IDS))
        + f"/{len(REQUIRED_SECTION_IDS)}"
        + (f" | optional={','.join(optional_present)}" if optional_present else "")
        + " | note=verify dollar figures against estimation JSON before sign-off"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
