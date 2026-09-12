#!/usr/bin/env python3
"""Validate heroku-to-aws migration-report.html (thin stakeholder report).

Required sections: decision-summary, exec-costs, cost-optimization, next-steps.
Conditional: what-if-scenarios when scenarios/index.json has ≥2 entries.
Footer must contain "draft for review".

Also enforces the report's own decision-UX and a11y contract (ported subset of
the gcp-to-aws report validator, #223 — gated to what the Heroku one-pager
actually emits):
  - decision-summary must NOT contain any badge-verdict-* pill (the skeleton mandates
    a typography-first `verdict-headline`; color-only verdict carriers are banned).
  - when estimation-infra.json declares recommendation.outcome, decision-summary
    must contain a `verdict-headline` element.
  - <html> must declare a lang attribute; any <th> must declare scope=col|row;
    any <figure> must carry aria-label + <figcaption>.

Deliberately NOT enforced (would false-fail the intentionally-thin Heroku
report, whose skeleton puts <nav class="toc"> before the verdict and emits no
<h1> / table <caption>): decision-before-TOC ordering, single-<h1>, per-table
<caption>, glossary/appendix set.

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
    "cost-optimization",
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


def _section_html(html: str, section_id: str) -> str | None:
    """Return the inner HTML of <section id="section_id"> ... </section>.

    Brace-free, tag-depth match on <section> so a nested <section> does not
    truncate early. Returns None when the section is absent.
    """
    open_re = re.compile(
        rf'<section\b[^>]*\bid=["\']{re.escape(section_id)}["\'][^>]*>',
        re.IGNORECASE,
    )
    m = open_re.search(html)
    if not m:
        return None
    depth = 1
    pos = m.end()
    tag_re = re.compile(r"</?section\b", re.IGNORECASE)
    for tag in tag_re.finditer(html, pos):
        if tag.group(0).lower().startswith("</"):
            depth -= 1
            if depth == 0:
                return html[m.end():tag.start()]
        else:
            depth += 1
    return html[m.end():]


def _validate_verdict(html: str, migration_dir: Path | None) -> list[str]:
    """Typography-first verdict rules (skill: verdict is the section thesis and
    must never be a colored-pill row)."""
    errors: list[str] = []
    summary = _section_html(html, "decision-summary")
    if summary is None:
        return errors  # missing-section already reported by the required-ID check

    # Colored pill badges are banned outright (not merely as the "sole" carrier).
    if re.search(r'class=["\'][^"\']*\bbadge-verdict-', summary, re.IGNORECASE):
        errors.append(
            'decision-summary must use a typography-first verdict-headline, '
            "not badge-verdict-* pills (meaning must not depend on color alone)"
        )

    # When Estimate declared a recommendation outcome, the verdict headline is required.
    recommendation_outcome = False
    if migration_dir is not None:
        est_path = migration_dir / "estimation-infra.json"
        if est_path.is_file():
            try:
                est = json.loads(est_path.read_text(encoding="utf-8"))
                rec = (est or {}).get("recommendation") or {}
                recommendation_outcome = bool(rec.get("outcome"))
            except (OSError, json.JSONDecodeError):
                # Fail open on ambiguity: a missing/corrupt estimate does not force the
                # verdict-headline requirement (we can't confirm an outcome was declared).
                recommendation_outcome = False
    if recommendation_outcome and not re.search(
        r'class=["\'][^"\']*\bverdict-headline\b', summary, re.IGNORECASE
    ):
        errors.append(
            "estimation-infra.json declares recommendation.outcome but "
            "decision-summary has no verdict-headline element "
            '(render outcome_label as <p class="verdict-headline">…</p>)'
        )
    return errors


def _validate_accessibility(html: str) -> list[str]:
    """Dependency-free WCAG-oriented semantics — the safe subset the Heroku
    one-pager emits (no single-<h1> / per-table-<caption> requirement)."""
    errors: list[str] = []
    if not re.search(
        r"<html\b[^>]*\blang=[\"'][a-z]{2}(?:-[A-Za-z0-9]+)?[\"']", html, re.IGNORECASE
    ):
        errors.append("accessibility: <html> must declare a valid lang attribute")

    body = re.sub(r"<style\b.*?</style>", "", html, flags=re.IGNORECASE | re.DOTALL)

    for index, table_match in enumerate(
        re.finditer(r"<table\b[^>]*>.*?</table>", body, re.IGNORECASE | re.DOTALL), 1
    ):
        table = table_match.group(0)
        for th in re.findall(r"<th\b[^>]*>", table, re.IGNORECASE):
            if not re.search(r"\bscope=[\"'](?:col|row)[\"']", th, re.IGNORECASE):
                errors.append(
                    f'accessibility: table {index} header cells must declare '
                    'scope="col" or scope="row"'
                )
                break

    for index, figure_match in enumerate(
        re.finditer(r"<figure\b[^>]*>.*?</figure>", body, re.IGNORECASE | re.DOTALL), 1
    ):
        figure = figure_match.group(0)
        opening = re.match(r"<figure\b[^>]*>", figure, re.IGNORECASE)
        opening_tag = opening.group(0) if opening else ""
        if not re.search(r'\baria-label=["\'][^"\']+["\']', opening_tag, re.IGNORECASE):
            errors.append(f"accessibility: figure {index} must have an aria-label")
        if not re.search(r"<figcaption\b", figure, re.IGNORECASE):
            errors.append(f"accessibility: figure {index} must include a <figcaption>")
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

    # cost-optimization must not be a blank section (generate-report.md Step 3 item 6:
    # a table, or the explicit no-eligible-commitment sentence — never empty).
    if counts.get("cost-optimization", 0) >= 1:
        body = _section_html(html, "cost-optimization") or ""
        if not re.sub(r"<[^>]+>", "", body).strip():
            errors.append(
                '<section id="cost-optimization"> is empty — render the opportunities '
                "table or the explicit no-eligible-commitment sentence, never a blank section"
            )

    errors.extend(_validate_verdict(html, migration_dir))
    errors.extend(_validate_accessibility(html))

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
