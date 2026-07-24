#!/usr/bin/env python3
"""Validate migration-report.html completeness after Generate phase.

Checks required section IDs, TOC anchor integrity, minimum appendix content,
artifact-derived cost markers, and customer-facing readability rules. Exit 0
on PASS, 1 on FAIL.

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
    "exec-assumptions",
    "exec-services",
    "exec-costs",
    "exec-timeline",
    "exec-risks",
    "appendix-services",
    "appendix-costs",
    "appendix-steps",
    "appendix-artifacts",
]

# Decision mode (decision-report.html rendered at the post-Estimate Decision
# gate, choice A): executive sections + CTA only — appendices are forbidden
# because no Generate artifacts exist yet.
DECISION_REQUIRED_SECTION_IDS = [
    "decision-summary",
    "exec-assumptions",
    "exec-services",
    "exec-costs",
    "exec-timeline",
    "exec-risks",
    "decision-cta",
]

OPTIONAL_SECTION_IDS = [
    "exec-tco",
    "exec-architecture",
    "exec-security-teaser",
    "what-if-scenarios",
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

# Customer-facing readability rules (enforced unless --no-readability).
# These move the de-jargoning and no-numbering conventions from "example in the
# fixture" to "enforced gate", so a stray internal scoring trace or a patched
# "Section 0/1b" heading fails the report instead of silently shipping.
READABILITY_PATTERNS = [
    (
        r"(?<![-_])\bTCO\b|Total\s+Cost\s+of\s+Ownership",
        'misleading ownership-cost label ("TCO") — use "estimated AWS monthly '
        'run rate"; the report does not price staffing or operating labor',
    ),
    (
        r"Rubric:",
        'internal scoring trace ("Rubric:") — drop it or gate behind a '
        '<details> "Why this mapping?" block',
    ),
    (
        r"Section\s+0\b",
        'literal "Section 0" heading — drop numeric "Section N" prefixes from '
        "customer-facing headings; let the table of contents carry structure",
    ),
    (
        r"<h[1-6][^>]*>\s*Section\s+\d+[a-z]?\s*[—-]",
        'numbered "Section N —" heading — drop numeric prefixes from headings; '
        "let the table of contents carry structure",
    ),
]

# Visual readability contract for generated reports. This intentionally checks
# structural CSS capabilities rather than pixel-perfect declarations: agents
# may refine colors and spacing, but they must not regress to unboxed prose on
# a plain white page or uneven inline-block metric cards.
VISUAL_CONTRACT_CHECKS = [
    (
        r"body\s*\{[^}]*background\s*:\s*(?:var\([^)]*\)|#f6f8fa)",
        "body must use a contrasting page background",
    ),
    (
        r"\.(?:report|container)\s*\{[^}]*max-width\s*:",
        "report shell must constrain line length with max-width",
    ),
    (
        r"section\s*\{[^}]*background\s*:[^;}]+;?[^}]*border\s*:[^;}]+;?"
        r"[^}]*border-radius\s*:",
        "sections must render as bordered surface cards",
    ),
    (
        r"\.metrics\s*\{[^}]*display\s*:\s*grid[^}]*grid-template-columns\s*:",
        "executive metrics must use a responsive CSS grid",
    ),
    (
        r"\.metric\s*\{[^}]*border\s*:[^;}]+;?[^}]*border-radius\s*:",
        "metric cards must have a bordered card treatment",
    ),
    (
        r"\.verdict\s*\{[^}]*background\s*:[^;}]+;?[^}]*border\s*:",
        "recommendation must have a visually distinct callout treatment",
    ),
    (
        r"\.savings\s*\{[^}]*color\s*:",
        "supported savings values must have a reusable visual treatment",
    ),
    (
        r"\.appendix-header\s*\{",
        "full/decision shared shell must define an appendix divider",
    ),
    (
        r":focus-visible\s*\{",
        "keyboard focus must be visibly styled",
    ),
    (
        r"@media\s*\([^)]*max-width\s*:\s*700px[^)]*\)",
        "mobile readability breakpoint (700px) is required",
    ),
    (
        r"@media\s+print\s*\{",
        "print-specific styling is required",
    ),
]

# Executive-flow sections must speak the reader's language, not the system's.
# Artifact filenames and Terraform resource IDs are internal build vocabulary —
# they belong in the technical appendices, not the executive summary. (Enforced
# unless --no-readability.)
EXEC_SECTION_IDS = (
    "decision-summary",
    "exec-tco",
    "exec-services",
    "exec-costs",
    "exec-architecture",
    "exec-security-teaser",
    "what-if-scenarios",
    "exec-timeline",
    "exec-risks",
)

ARTIFACT_FILENAME_RE = re.compile(r"\b[a-z0-9][a-z0-9_-]*\.json\b", re.IGNORECASE)
TERRAFORM_RESOURCE_RE = re.compile(r"\baws_[a-z0-9_]+\.[a-z0-9_]+\b")

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

# Migration ID baked into the reference fixture. If this appears in a real
# $MIGRATION_DIR run, the agent copied the golden file verbatim (fixture bleed).
FIXTURE_CANARY_ID = "0611-0606"
MIGRATION_ID_RE = re.compile(r"\b(\d{4}-\d{4})\b")

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


def _validate_required_sections(
    html: str, required_ids: list[str] | None = None
) -> list[str]:
    errors: list[str] = []
    counts = _section_id_counts(html)
    for section_id in required_ids if required_ids is not None else REQUIRED_SECTION_IDS:
        n = counts.get(section_id, 0)
        if n == 0:
            errors.append(f'missing required <section id="{section_id}">')
        elif n > 1:
            errors.append(f'duplicate <section id="{section_id}"> ({n} occurrences)')
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


def _validate_toc(html: str, required_ids: list[str] | None = None) -> list[str]:
    if required_ids is None:
        required_ids = REQUIRED_SECTION_IDS
    errors: list[str] = []
    hrefs = _toc_hrefs(html)
    if not hrefs:
        return errors  # TOC optional if nav.toc absent; spec requires it in generated reports

    section_ids = set(_section_id_counts(html).keys())
    for href in hrefs:
        if href not in section_ids:
            errors.append(f'TOC broken link href="#{href}" — no matching <section id="{href}">')

    # Every required section must be linked from the TOC.
    for section_id in required_ids:
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
    """True when a dollar-formatted value appears in text (not bare CSS integers)."""
    normalized = text.replace(",", "")
    v = float(amount)
    candidates: list[str] = []
    if v == int(v):
        i = int(v)
        candidates.extend([f"${i}", f"${i}.00", f"${i}.0"])
    candidates.append(f"${v:.2f}")
    return any(c in normalized for c in candidates)


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


def _readability_scope(html: str) -> str:
    """Body only, excluding <style> blocks so CSS class names like .rubric or
    selectors never trip the readability patterns."""
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


def _validate_visual_contract(html: str) -> list[str]:
    """Validate the shared report shell's minimum visual readability contract."""
    style_blocks = re.findall(
        r"<style\b[^>]*>(.*?)</style>",
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not style_blocks:
        return ["visual readability: missing inline <style> report shell"]
    css = "\n".join(style_blocks)
    errors: list[str] = []
    for pattern, label in VISUAL_CONTRACT_CHECKS:
        if not re.search(pattern, css, re.DOTALL | re.IGNORECASE):
            errors.append(f"visual readability: {label}")
    return errors


def _validate_exec_vocabulary(html: str) -> list[str]:
    """Executive-flow sections must name what the reader controls, not how the
    system is built. Artifact filenames (*.json) and Terraform resource IDs
    (aws_<resource>.<name>) are internal vocabulary and belong in the technical
    appendices. Appendix sections are exempt by design."""
    errors: list[str] = []
    for sid in EXEC_SECTION_IDS:
        section = _section_html(html, sid)
        if not section:
            continue
        filenames = sorted(set(m.lower() for m in ARTIFACT_FILENAME_RE.findall(section)))
        resources = sorted(set(TERRAFORM_RESOURCE_RE.findall(section)))
        if filenames:
            errors.append(
                f'exec vocabulary: <section id="{sid}"> exposes artifact filename(s) '
                f"{filenames} — name what the reader controls in the executive flow; "
                "keep artifact filenames in the technical appendices"
            )
        if resources:
            errors.append(
                f'exec vocabulary: <section id="{sid}"> exposes Terraform resource ID(s) '
                f"{resources} — move resource names to the appendix; the executive flow "
                "names what the reader controls"
            )
    return errors


def _has_security_baseline(estimation_infra: dict | None) -> bool:
    if not estimation_infra:
        return False
    return bool(
        estimation_infra.get("projected_costs", {}).get("breakdown", {}).get("security_baseline")
    )


def _validate_security_teaser(html: str, estimation_infra: dict | None) -> list[str]:
    """When a security baseline exists, the executive flow must carry a compact
    teaser (exec-security-teaser) — not the full control table inline."""
    if not _has_security_baseline(estimation_infra):
        return []
    if _section_id_counts(html).get("exec-security-teaser", 0) >= 1:
        return []
    return [
        'security_baseline exists but no <section id="exec-security-teaser"> — keep a compact '
        "teaser in the executive flow and the full control table in appendix-security"
    ]


def _validate_action_lists(html: str) -> list[str]:
    """Key decisions ahead and Next steps must be ordered lists — actionable sequence."""
    errors: list[str] = []
    summary = _section_html(html, "decision-summary") or ""
    for heading in ("Key decisions ahead", "Next steps"):
        pattern = re.compile(
            rf"<h3[^>]*>\s*{re.escape(heading)}\s*</h3>\s*<(ul|ol)\b",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(summary)
        if match and match.group(1).lower() == "ul":
            errors.append(
                f'decision-summary: "{heading}" must use <ol class="compact"> (ordered action '
                "items), not a bullet list"
            )
    return errors


def _validate_appendix_config(html: str) -> list[str]:
    """When appendix-config is present, require provenance columns."""
    section = _section_html(html, "appendix-config")
    if not section:
        return []
    errors: list[str] = []
    if not re.search(r"<table\b", section, re.IGNORECASE):
        errors.append("appendix-config must contain an HTML table of configuration choices")
        return errors
    header = re.search(r"<thead\b.*?</thead>", section, re.DOTALL | re.IGNORECASE)
    if not header:
        errors.append("appendix-config table must have <thead> with column headers")
        return errors
    hdr_text = header.group(0).lower()
    if "question" not in hdr_text and "assumption" not in hdr_text:
        errors.append(
            'appendix-config table must include a "Question" or "Assumption" column (from preferences.prompt)'
        )
    if "consequence" not in hdr_text:
        errors.append(
            "appendix-config table must include a Design consequence column (from preferences.design_consequence)"
        )
    rows = _count_table_rows(section)
    if rows < 2:
        errors.append(f"appendix-config must have >=2 configuration rows (found {rows})")
    return errors


def _validate_verdict(html: str, estimation_infra: dict | None) -> list[str]:
    """When a recommendation block exists, the decision summary must state a
    one-sentence verdict in a visually distinct class="verdict" callout."""
    if not estimation_infra or not estimation_infra.get("recommendation"):
        return []
    summary = _section_html(html, "decision-summary") or ""
    if re.search(r'class="[^"]*\bverdict\b[^"]*"', summary, re.IGNORECASE):
        return []
    return [
        "recommendation block exists but decision-summary has no verdict banner "
        '(wrap the one-sentence recommendation in class="verdict")'
    ]


def _validate_activate_link(html: str) -> list[str]:
    """Keep the Activate action attached to its executive-summary benefit."""
    summary = _section_html(html, "decision-summary") or ""
    if not re.search(r"AWS\s+Activate|Activate\s+(?:Founders|Portfolio|credits)", summary, re.I):
        return []
    if re.search(
        r'href=["\']https://aws\.amazon\.com/startups/credits/?["\']',
        summary,
        re.IGNORECASE,
    ):
        return []
    return [
        "decision-summary mentions AWS Activate but has no clickable official "
        "apply link (https://aws.amazon.com/startups/credits/)"
    ]


def _validate_glossary_table(html: str) -> list[str]:
    """Full reports present terms and meanings in a scannable two-column table."""
    match = re.search(
        r'<table\b[^>]*class=["\'][^"\']*\bglossary-table\b[^"\']*["\'][^>]*>'
        r"(.*?)</table>",
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return [
            'full report glossary must use <table class="glossary-table"> '
            "with distinct Term and Meaning cells"
        ]
    table = match.group(1)
    header = re.search(r"<thead\b[^>]*>(.*?)</thead>", table, re.DOTALL | re.I)
    if not header or not re.search(r">\s*Term\s*<", header.group(1), re.I) or not re.search(
        r">\s*Meaning\s*<", header.group(1), re.I
    ):
        return ['glossary-table must have "Term" and "Meaning" column headers']
    if _count_table_rows(f"<table>{table}</table>") < 3:
        return ["glossary-table must contain at least 3 term-definition rows"]
    return []


def _validate_fixture_bleed(html: str, migration_dir: Path | None) -> list[str]:
    """Catch agents that copied the reference fixture verbatim into a real run.

    Only active when --migration-dir is passed (i.e. validating a real
    $MIGRATION_DIR report, not the fixture itself). Fails if the fixture canary
    ID appears, or if the report's stated migration ID does not match the run dir.
    """
    if migration_dir is None:
        return []  # fixture-self-exemption: no run dir → don't flag the canary

    errors: list[str] = []
    dir_name = migration_dir.name
    body = _readability_scope(html)

    if FIXTURE_CANARY_ID in body and dir_name != FIXTURE_CANARY_ID:
        errors.append(
            f'fixture bleed: reference canary migration ID "{FIXTURE_CANARY_ID}" appears in a '
            f'real run (--migration-dir={dir_name}) — the report was copied from the fixture'
        )

    ids_in_report = {m.group(1) for m in MIGRATION_ID_RE.finditer(body)}
    if re.fullmatch(r"\d{4}-\d{4}", dir_name) and ids_in_report and dir_name not in ids_in_report:
        errors.append(
            f'migration ID mismatch: report references {sorted(ids_in_report)} but '
            f"--migration-dir is {dir_name} — verify the report belongs to this run"
        )
    return errors


def validate_report(
    html: str,
    estimation_infra: dict | None = None,
    estimation_ai: dict | None = None,
    *,
    require_toc: bool = True,
    check_readability: bool = True,
    migration_dir: Path | None = None,
    mode: str = "full",
) -> list[str]:
    errors: list[str] = []

    required_ids = DECISION_REQUIRED_SECTION_IDS if mode == "decision" else REQUIRED_SECTION_IDS
    errors.extend(_validate_required_sections(html, required_ids))

    if mode == "decision":
        # No Generate artifacts exist at decision time: appendices are forbidden.
        counts = _section_id_counts(html)
        for sid in counts:
            if sid.startswith("appendix-"):
                errors.append(
                    f'decision mode forbids <section id="{sid}"> — the decision report '
                    "has no appendices; the full migration report (Generate) carries them"
                )

    if require_toc:
        if not _toc_hrefs(html):
            errors.append('missing <nav class="toc"> with href="#section-id" links')
        errors.extend(_validate_toc(html, required_ids))

    for pattern, label in FORBIDDEN_PATTERNS:
        if re.search(pattern, html, re.IGNORECASE):
            errors.append(f"forbidden content: {label}")

    if check_readability:
        errors.extend(_validate_readability(html))
        errors.extend(_validate_exec_vocabulary(html))
        # Normal generated reports require a TOC. Use the same signal to
        # enforce the visual shell while preserving --no-require-toc as the
        # lightweight escape hatch for deliberately minimal unit fixtures.
        if require_toc:
            errors.extend(_validate_visual_contract(html))

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

    # Combined AWS monthly run-rate section required only when BOTH estimate
    # artifacts exist (not AI-only runs). exec-tco is a legacy structural ID.
    if estimation_infra is not None and estimation_ai is not None:
        counts = _section_id_counts(html)
        if counts.get("exec-tco", 0) != 1:
            errors.append(
                "when both estimation-infra.json and estimation-ai.json exist, "
                'include exactly one <section id="exec-tco"> with the combined '
                "infra+AI estimated AWS monthly run rate"
            )

    # Security teaser must exist in the exec flow when a baseline is estimated.
    errors.extend(_validate_security_teaser(html, estimation_infra))

    # Decision summary must state a one-sentence verdict when a recommendation exists.
    errors.extend(_validate_verdict(html, estimation_infra))
    errors.extend(_validate_activate_link(html))
    if mode == "full" and require_toc:
        errors.extend(_validate_glossary_table(html))

    # Ordered action lists and configuration provenance (when sections present).
    errors.extend(_validate_action_lists(html))
    errors.extend(_validate_appendix_config(html))

    # Catch verbatim copies of the reference fixture into a real run.
    errors.extend(_validate_fixture_bleed(html, migration_dir))

    # What-if workshop scenario table — required when ≥2 scenarios were snapshotted.
    if migration_dir is not None:
        index_path = migration_dir / "scenarios" / "index.json"
        if index_path.is_file():
            try:
                index = json.loads(index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                index = None
            scenarios = (index or {}).get("scenarios") or []
            counts = _section_id_counts(html)
            if len(scenarios) >= 2 and counts.get("what-if-scenarios", 0) < 1:
                errors.append(
                    'scenarios/index.json has ≥2 scenarios but no '
                    '<section id="what-if-scenarios"> (workshop compare table is '
                    "required in the migration report when variants exist)"
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate migration-report.html")
    parser.add_argument("report_path", type=Path, help="Path to migration-report.html")
    parser.add_argument("--estimation-infra", type=Path, default=None)
    parser.add_argument("--estimation-ai", type=Path, default=None)
    parser.add_argument(
        "--migration-dir",
        type=Path,
        default=None,
        help="Migration output dir ($MIGRATION_DIR). Enables fixture-bleed detection: "
        "the report's migration ID must match this folder, and the reference fixture's "
        "canary ID must not appear in a real run.",
    )
    parser.add_argument(
        "--no-require-toc",
        action="store_true",
        help="Skip TOC requirement (for minimal test fixtures)",
    )
    parser.add_argument(
        "--no-readability",
        action="store_true",
        help="Skip customer-facing readability checks (Rubric:/Section N)",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "decision"],
        default="full",
        help="full = migration-report.html (default); decision = decision-report.html "
        "written at the post-Estimate Decision gate (exec sections + CTA, no appendices)",
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
        check_readability=not args.no_readability,
        migration_dir=args.migration_dir,
        mode=args.mode,
    )
    if errors:
        print("REPORT_FAIL | migration-report.html", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    counts = _section_id_counts(html)
    optional_present = [sid for sid in OPTIONAL_SECTION_IDS if counts.get(sid, 0) >= 1]
    required_count = len(
        DECISION_REQUIRED_SECTION_IDS if args.mode == "decision" else REQUIRED_SECTION_IDS
    )
    mode_tag = "" if args.mode == "full" else f"mode={args.mode} | "
    print(
        f"REPORT_OK | {mode_tag}structure=complete | sections="
        + str(required_count)
        + f"/{required_count}"
        + (f" | optional={','.join(optional_present)}" if optional_present else "")
        + " | note=verify dollar figures against estimation JSON before sign-off"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
