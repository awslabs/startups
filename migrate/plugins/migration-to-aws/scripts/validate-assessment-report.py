#!/usr/bin/env python3
"""Validate migration-report.html completeness after the Report phase.

Fork of scripts/validate-migration-report.py (GCP skill), adapted for
vercel-to-aws's outcome-filtered pre-flight-finding report structure. Checks
required section IDs, TOC anchor integrity, minimum appendix content, the
reader-vocabulary rule (no Pre-Flight Check IDs / artifact filenames /
Terraform resource IDs / "route disposition" in executive-flow sections), the
cost-labeling rule (every dollar figure phrased as "estimated monthly"), and
fixture-bleed detection. Exit 0 on PASS, 1 on FAIL, anything else means this
script itself did not run (e.g. python3 missing) - the caller must branch on
the shell exit code, never on stdout text alone.

Usage:
  python3 validate-assessment-report.py /path/to/migration-report.html
  python3 validate-assessment-report.py report.html \\
      --recommendation recommendation.json \\
      --preflight-findings preflight-findings.json \\
      --tier1-signals tier1-signals.json \\
      --migration-dir "$MIGRATION_DIR"

Script location: this file lives at
  migrate/plugins/migration-to-aws/scripts/validate-assessment-report.py
Agents should invoke it via Path(__file__) resolution or:
  python3 "$(dirname ...)/scripts/validate-assessment-report.py" ...
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Plugin root: migrate/plugins/migration-to-aws/
PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# Requirement 9.1 / design.md 4.2 - always-required sections.
REQUIRED_SECTION_IDS = [
    "exec-verdict",
    "what-you-gain",
    "what-you-lose",
    "coupling-score",
    "preflight-findings",
    "decision-traceability",
    "next-steps",
]

# Conditional sections - required only when their trigger condition holds
# (checked separately in validate_report(), not via REQUIRED_SECTION_IDS).
CONDITIONAL_SECTION_IDS = {
    "exec-tiebreak": "recommendation.tiebreak == true",
    "inputs-received": "any finding below HIGH confidence",
    "appendix-m1": "tier1-signals.has_middleware == true",
    "out-of-scope": "recommendation.outcome is 'C' or 'stay'",
    "cost-comparison": "estimation-infra.json exists (estimate phase completed)",
    "artifacts-generated": "estimation-infra.json exists (generate phase completed)",
    "what-if-scenarios": "scenarios/index.json has ≥2 scenarios (workshop variants)",
}

OPTIONAL_SECTION_IDS = list(CONDITIONAL_SECTION_IDS.keys())

FORBIDDEN_PATTERNS = [
    (r"\[placeholder\]", "placeholder text"),
    (r"\bTODO\b", "TODO marker"),
]

# Customer-facing readability rules (enforced unless --no-readability).
READABILITY_PATTERNS = [
    (
        r"Rubric:",
        'internal scoring trace ("Rubric:") - drop it or gate behind a '
        '<details> "Why this mapping?" block',
    ),
    (
        r"Section\s+0\b",
        'literal "Section 0" heading - drop numeric "Section N" prefixes from '
        "customer-facing headings; let the table of contents carry structure",
    ),
    (
        r"<h[1-6][^>]*>\s*Section\s+\d+[a-z]?\s*[\u2014-]",
        'numbered "Section N -" heading - drop numeric prefixes from headings; '
        "let the table of contents carry structure",
    ),
]

# Executive-flow sections must speak the founder's language, not the system's.
# Pre-Flight Check IDs, artifact filenames, Terraform resource IDs, and the
# term "route disposition" are internal build vocabulary - they belong in the
# technical appendices, not the executive summary (Requirement 9.7).
EXEC_SECTION_IDS = (
    "exec-verdict",
    "exec-tiebreak",
    "what-you-gain",
    "what-you-lose",
)

ARTIFACT_FILENAME_RE = re.compile(r"\b[a-z0-9][a-z0-9_-]*\.json\b", re.IGNORECASE)
TERRAFORM_RESOURCE_RE = re.compile(r"\baws_[a-z0-9_]+\.[a-z0-9_]+\b")
# The 10 named Pre-Flight Check IDs: M1, M2, B1-B4, S1, I1, O1, U1.
PREFLIGHT_CHECK_ID_RE = re.compile(r"\b(M1|M2|B[1-4]|S1|I1|O1|U1)\b")
ROUTE_DISPOSITION_RE = re.compile(r"route disposition", re.IGNORECASE)

APPENDIX_STUB_PATTERNS = [
    re.compile(
        r'<section[^>]*id="preflight-findings"[^>]*>.*?Full findings:\s*<code>preflight-findings\.json</code>',
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(
        r'<section[^>]*id="coupling-score"[^>]*>\s*<p>\s*See\s*<code>coupling-score\.json</code>',
        re.DOTALL | re.IGNORECASE,
    ),
]

MIN_CONTENT_DEPTH = {
    "coupling-score": 3,
    "preflight-findings": 2,
    "decision-traceability": 1,
}

SECTION_OPEN = re.compile(
    r"<section\b[^>]*\bid=(['\"])([^'\"]+)\1",
    re.IGNORECASE,
)

# Migration ID baked into the reference fixture. If this appears in a real
# $MIGRATION_DIR run, the agent copied the golden file verbatim (fixture bleed).
# Distinct from the GCP skill's canary (0611-0606) so the two never collide.
FIXTURE_CANARY_ID = "0722-1400"
MIGRATION_ID_RE = re.compile(r"\b(\d{4}-\d{4})\b")

# Requirement 9.6 - every dollar figure must be phrased as "estimated monthly".
# Matches $123, $1,234.56, $1234, etc.
DOLLAR_AMOUNT_RE = re.compile(r"\$[0-9][0-9,]*(?:\.[0-9]{1,2})?")
ESTIMATED_MONTHLY_RE = re.compile(r"estimated\s+monthly", re.IGNORECASE)

# AWS Activate credit ceilings (e.g. "up to $5,000 in AWS Activate credits")
# are one-time program limits, not a recurring cost or savings figure -
# forcing "estimated monthly" onto them would misrepresent a credit ceiling as
# a monthly estimate. Exempt a dollar figure from the cost-labeling rule ONLY
# when "activate" appears within the same window already used for the
# "estimated monthly" proximity check. Deliberately narrower than a bare
# "credit(s)" match (which would also match unrelated phrases like "credit
# card" or "store credit" and could let a real, unlabeled cost slip through) -
# "activate" is specific enough to this program that it should not appear
# near a dollar figure for any other reason in this report.
ACTIVATE_CREDIT_CONTEXT_RE = re.compile(r"\bactivate\b", re.IGNORECASE)

# NOTE: _section_html uses non-greedy match to first </section>. This assumes
# sections are NOT nested. Do not nest <section> elements in assessment reports.


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
            errors.append(f'missing required <section id="{section_id}">')
        elif n > 1:
            errors.append(f'duplicate <section id="{section_id}"> ({n} occurrences)')
    return errors


def _validate_conditional_sections(
    html: str,
    recommendation: dict | None,
    preflight_findings: dict | None,
    tier1_signals: dict | None,
    estimation_infra: dict | None = None,
    migration_dir: Path | None = None,
) -> list[str]:
    """Requirement 9.2-9.5 - conditional-gate sections + workshop scenarios."""
    errors: list[str] = []
    counts = _section_id_counts(html)

    if recommendation and recommendation.get("tiebreak") is True:
        if counts.get("exec-tiebreak", 0) < 1:
            errors.append(
                'recommendation.tiebreak is true but no <section id="exec-tiebreak"> '
                "(the Outcome A/B side-by-side section is required per Requirement 9.2)"
            )

    if preflight_findings:
        checks = preflight_findings.get("checks", [])
        any_sub_high = any(c.get("confidence", "HIGH") != "HIGH" for c in checks)
        if any_sub_high and counts.get("inputs-received", 0) < 1:
            errors.append(
                'a finding is below HIGH confidence but no <section id="inputs-received"> '
                "(the confidence-upgrade-offers section is required per Requirement 9.3)"
            )

    if tier1_signals and tier1_signals.get("has_middleware") is True:
        if counts.get("appendix-m1", 0) < 1:
            errors.append(
                'tier1-signals.has_middleware is true but no <section id="appendix-m1"> '
                "(required per Requirement 9.4)"
            )

    if recommendation and recommendation.get("outcome") in ("C", "stay"):
        if counts.get("out-of-scope", 0) < 1:
            errors.append(
                f'recommendation.outcome is "{recommendation.get("outcome")}" but no '
                '<section id="out-of-scope"> (the separability rationale is required '
                "per Requirement 9.5)"
            )

    # Cost-comparison and artifacts-generated are required when estimation-infra.json exists
    if estimation_infra is not None:
        if counts.get("cost-comparison", 0) < 1:
            errors.append(
                'estimation-infra.json exists but no <section id="cost-comparison"> '
                "(the cost comparison section is required when an estimate has been produced)"
            )
        if counts.get("artifacts-generated", 0) < 1:
            errors.append(
                'estimation-infra.json exists but no <section id="artifacts-generated"> '
                "(the artifacts summary section is required when generation has completed)"
            )

    # What-if workshop scenario table — required when ≥2 scenarios were snapshotted
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
                    '<section id="what-if-scenarios"> (workshop compare table is '
                    "required in the assessment report when variants exist)"
                )

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
            errors.append(f'TOC broken link href="#{href}" - no matching <section id="{href}">')

    for section_id in REQUIRED_SECTION_IDS:
        if section_id in section_ids and section_id not in hrefs and hrefs:
            errors.append(
                f'TOC missing link to required section id="{section_id}" '
                f'(add <a href="#{section_id}">)'
            )
    return errors


def _count_table_rows(section_html: str) -> int:
    tbody = re.search(r"<tbody>(.*?)</tbody>", section_html, re.DOTALL | re.IGNORECASE)
    if not tbody:
        return 0
    return len(re.findall(r"<tr\b", tbody.group(1), re.IGNORECASE))


def _section_content_depth(section_id: str, section_html: str) -> int:
    rows = _count_table_rows(section_html)
    if section_id == "preflight-findings":
        cards = len(re.findall(r'class="preflight-check-card"', section_html))
        return max(rows, cards)
    if section_id == "decision-traceability":
        entries = len(re.findall(r'class="trace-entry"', section_html))
        return max(rows, entries, 1 if re.search(r"fired\b", section_html, re.IGNORECASE) else 0)
    return rows


def _readability_scope(html: str) -> str:
    """Body only, excluding <style> blocks so CSS class names never trip the
    readability patterns."""
    no_style = re.sub(r"<style\b.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    body = re.search(r"<body\b[^>]*>(.*?)</body>", no_style, re.DOTALL | re.IGNORECASE)
    return body.group(1) if body else no_style


def _validate_readability(html: str) -> list[str]:
    errors: list[str] = []
    scope = _readability_scope(html)
    for pattern, label in READABILITY_PATTERNS:
        if re.search(pattern, scope, re.IGNORECASE):
            errors.append(f"readability: {label}")
    return errors


def _validate_exec_vocabulary(html: str) -> list[str]:
    """Requirement 9.7 - executive-flow sections must name what the founder
    controls, not internal identifiers. Pre-Flight Check IDs, artifact
    filenames, Terraform resource IDs, and "route disposition" belong only in
    technical appendices. Appendix sections are exempt by design."""
    errors: list[str] = []
    for sid in EXEC_SECTION_IDS:
        section = _section_html(html, sid)
        if not section:
            continue
        filenames = sorted(set(m.lower() for m in ARTIFACT_FILENAME_RE.findall(section)))
        resources = sorted(set(TERRAFORM_RESOURCE_RE.findall(section)))
        check_ids = sorted(set(PREFLIGHT_CHECK_ID_RE.findall(section)))
        has_route_disposition = bool(ROUTE_DISPOSITION_RE.search(section))
        if filenames:
            errors.append(
                f'exec vocabulary: <section id="{sid}"> exposes artifact filename(s) '
                f"{filenames} - name what the founder controls in the executive flow; "
                "keep artifact filenames in the technical appendices"
            )
        if resources:
            errors.append(
                f'exec vocabulary: <section id="{sid}"> exposes Terraform resource ID(s) '
                f"{resources} - move resource names to the appendix"
            )
        if check_ids:
            errors.append(
                f'exec vocabulary: <section id="{sid}"> exposes Pre-Flight Check ID(s) '
                f'{check_ids} (e.g. "M1") - describe the behavior in plain language '
                '("your middleware skips on cached pages"), not the check ID'
            )
        if has_route_disposition:
            errors.append(
                f'exec vocabulary: <section id="{sid}"> uses the term "route disposition" - '
                "this is internal build vocabulary; describe the behavior in plain language"
            )
    return errors


def _validate_cost_labeling(html: str) -> list[str]:
    """Requirement 9.6 - every dollar figure anywhere in the report body must
    be phrased as "estimated monthly cost/savings", including U1's cost-driver
    figures, even though full cost estimation is deferred to v2. Scoped to
    table cells and sentences (a $ figure and "estimated monthly" must appear
    within the same <td>...</td> or within ~120 characters of each other).

    Exception: an AWS Activate credit ceiling (e.g. "up to $5,000 in AWS
    Activate credits") is a one-time program limit, not a recurring cost or
    savings estimate - "estimated monthly" would misdescribe it. Exempted only
    when "Activate" appears in the same proximity window (deliberately not a
    bare "credit(s)" match, which would also match unrelated phrases like
    "credit card" and could let a real, unlabeled cost slip through)."""
    errors: list[str] = []
    scope = _readability_scope(html)

    # Scan table cells first (most dollar figures live in tables).
    for cell_match in re.finditer(r"<td\b[^>]*>(.*?)</td>", scope, re.DOTALL | re.IGNORECASE):
        cell = cell_match.group(1)
        if DOLLAR_AMOUNT_RE.search(cell) and not ESTIMATED_MONTHLY_RE.search(cell):
            # allow "estimated monthly" in an adjacent header cell/caption - do a
            # widened check against a window around the cell before flagging.
            start = max(0, cell_match.start() - 200)
            end = min(len(scope), cell_match.end() + 200)
            window = scope[start:end]
            if ESTIMATED_MONTHLY_RE.search(window):
                continue
            if ACTIVATE_CREDIT_CONTEXT_RE.search(window):
                continue  # one-time credit ceiling, not a cost/savings estimate
            amount = DOLLAR_AMOUNT_RE.search(cell).group(0)
            errors.append(
                f'cost-labeling: dollar figure "{amount}" appears without "estimated '
                'monthly" nearby - every dollar figure must be phrased as "estimated '
                'monthly cost/savings" (Requirement 9.6, applies even to U1 findings) - '
                'unless it is an AWS Activate credit ceiling, which reads "Activate" '
                "nearby instead"
            )

    # Then scan prose outside tables for stray dollar figures.
    prose = re.sub(r"<table\b.*?</table>", "", scope, flags=re.DOTALL | re.IGNORECASE)
    for amount_match in DOLLAR_AMOUNT_RE.finditer(prose):
        start = max(0, amount_match.start() - 120)
        end = min(len(prose), amount_match.end() + 120)
        window = prose[start:end]
        if ESTIMATED_MONTHLY_RE.search(window):
            continue
        if ACTIVATE_CREDIT_CONTEXT_RE.search(window):
            continue  # one-time credit ceiling, not a cost/savings estimate
        errors.append(
            f'cost-labeling: dollar figure "{amount_match.group(0)}" in prose appears '
            'without "estimated monthly" nearby (Requirement 9.6) - unless it is an AWS '
            'Activate credit ceiling, which reads "Activate" nearby instead'
        )

    return errors


def _validate_action_lists(html: str) -> list[str]:
    """Requirement 9.1 - Next Steps must be an ordered list."""
    errors: list[str] = []
    next_steps = _section_html(html, "next-steps") or ""
    if next_steps and not re.search(r"<ol\b", next_steps, re.IGNORECASE):
        errors.append(
            'next-steps section must use <ol> (ordered action items), not a bullet list '
            "or plain paragraphs (Requirement 9.1)"
        )
    return errors


def _validate_decision_traceability(html: str, recommendation: dict | None) -> list[str]:
    """Requirement 10.1-10.4 - the decision-traceability appendix is ALWAYS
    required (checked in REQUIRED_SECTION_IDS) and must name the fired rule."""
    errors: list[str] = []
    section = _section_html(html, "decision-traceability")
    if section is None:
        return errors  # already flagged by _validate_required_sections
    if not re.search(r"\bfired\b|\brule\b", section, re.IGNORECASE):
        errors.append(
            "decision-traceability appendix must state which precedence rule fired "
            "and why (Requirement 10.1, 10.3)"
        )
    if recommendation and recommendation.get("tiebreak") is True:
        if not re.search(r"log drain|resolving", section, re.IGNORECASE):
            errors.append(
                "decision-traceability appendix must state which rule would have applied "
                "had the missing input (log drain data) been available, since the "
                "tiebreak fired (Requirement 10.4)"
            )
    return errors


def _validate_verdict(html: str, recommendation: dict | None) -> list[str]:
    """Requirement 9.2 - exec-verdict must state a one-sentence verdict, not
    only badges."""
    if not recommendation:
        return []
    section = _section_html(html, "exec-verdict") or ""
    if not section:
        return []  # already flagged by _validate_required_sections
    if re.search(r'class="[^"]*\bverdict\b[^"]*"', section, re.IGNORECASE):
        return []
    if re.search(r"Recommendation:", section):
        return []
    return [
        'exec-verdict section exists but has no verdict banner '
        '(add an element with class="verdict" or a "Recommendation:" sentence)'
    ]


def _validate_fixture_bleed(html: str, migration_dir: Path | None) -> list[str]:
    """Catch agents that copied the reference fixture verbatim into a real run.

    Only active when --migration-dir is passed (i.e. validating a real
    $MIGRATION_DIR report, not the fixture itself). Fails if the fixture canary
    ID appears, or if the report's stated migration ID does not match the run dir.
    """
    if migration_dir is None:
        return []  # fixture-self-exemption: no run dir - don't flag the canary

    errors: list[str] = []
    dir_name = migration_dir.name
    body = _readability_scope(html)

    if FIXTURE_CANARY_ID in body and dir_name != FIXTURE_CANARY_ID:
        errors.append(
            f'fixture bleed: reference canary migration ID "{FIXTURE_CANARY_ID}" appears in a '
            f'real run (--migration-dir={dir_name}) - the report was copied from the fixture'
        )

    ids_in_report = {m.group(1) for m in MIGRATION_ID_RE.finditer(body)}
    if re.fullmatch(r"\d{4}-\d{4}", dir_name) and ids_in_report and dir_name not in ids_in_report:
        errors.append(
            f'migration ID mismatch: report references {sorted(ids_in_report)} but '
            f"--migration-dir is {dir_name} - verify the report belongs to this run"
        )
    return errors


def validate_report(
    html: str,
    recommendation: dict | None = None,
    preflight_findings: dict | None = None,
    tier1_signals: dict | None = None,
    estimation_infra: dict | None = None,
    *,
    require_toc: bool = True,
    check_readability: bool = True,
    migration_dir: Path | None = None,
) -> list[str]:
    errors: list[str] = []

    errors.extend(_validate_required_sections(html))
    errors.extend(
        _validate_conditional_sections(
            html,
            recommendation,
            preflight_findings,
            tier1_signals,
            estimation_infra,
            migration_dir,
        )
    )

    if require_toc:
        if not _toc_hrefs(html):
            errors.append('missing <nav class="toc"> with href="#section-id" links')
        errors.extend(_validate_toc(html))

    for pattern, label in FORBIDDEN_PATTERNS:
        if re.search(pattern, html, re.IGNORECASE):
            errors.append(f"forbidden content: {label}")

    if check_readability:
        errors.extend(_validate_readability(html))
        errors.extend(_validate_exec_vocabulary(html))
        errors.extend(_validate_cost_labeling(html))

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
                "appendix appears to be a stub (links to JSON only) - "
                "expand per report-render.md"
            )

    if "draft for review" not in html.lower():
        errors.append('footer must contain "draft for review" disclaimer')

    errors.extend(_validate_verdict(html, recommendation))
    errors.extend(_validate_decision_traceability(html, recommendation))
    errors.extend(_validate_action_lists(html))

    # Catch verbatim copies of the reference fixture into a real run.
    errors.extend(_validate_fixture_bleed(html, migration_dir))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate migration-report.html")
    parser.add_argument("report_path", type=Path, help="Path to migration-report.html")
    parser.add_argument("--recommendation", type=Path, default=None)
    parser.add_argument("--preflight-findings", type=Path, default=None)
    parser.add_argument("--tier1-signals", type=Path, default=None)
    parser.add_argument("--estimation-infra", type=Path, default=None,
                        help="Path to estimation-infra.json. Enables cost-comparison/artifacts-generated checks.")
    parser.add_argument(
        "--migration-dir",
        type=Path,
        default=None,
        help="Migration output dir ($MIGRATION_DIR). Enables fixture-bleed detection.",
    )
    parser.add_argument(
        "--no-require-toc",
        action="store_true",
        help="Skip TOC requirement (for minimal test fixtures)",
    )
    parser.add_argument(
        "--no-readability",
        action="store_true",
        help="Skip customer-facing readability checks (escape hatch; not for normal Report runs)",
    )
    args = parser.parse_args()

    if not args.report_path.is_file():
        print(f"REPORT_FAIL | file={args.report_path} | reason=not_found", file=sys.stderr)
        return 1

    html = args.report_path.read_text(encoding="utf-8")

    recommendation = None
    if args.recommendation and args.recommendation.is_file():
        recommendation = json.loads(args.recommendation.read_text(encoding="utf-8"))

    preflight_findings = None
    if args.preflight_findings and args.preflight_findings.is_file():
        preflight_findings = json.loads(args.preflight_findings.read_text(encoding="utf-8"))

    tier1_signals = None
    if args.tier1_signals and args.tier1_signals.is_file():
        tier1_signals = json.loads(args.tier1_signals.read_text(encoding="utf-8"))

    estimation_infra = None
    if args.estimation_infra and args.estimation_infra.is_file():
        estimation_infra = json.loads(args.estimation_infra.read_text(encoding="utf-8"))

    errors = validate_report(
        html,
        recommendation,
        preflight_findings,
        tier1_signals,
        estimation_infra,
        require_toc=not args.no_require_toc,
        check_readability=not args.no_readability,
        migration_dir=args.migration_dir,
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
        + " | note=verify dollar figures against recommendation/preflight JSON before sign-off"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
