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
from html.parser import HTMLParser
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


class _SectionScopeParser(HTMLParser):
    """Locate <section id="..."> ... </section> by parsed tag structure rather
    than a literal `<section ...>(.*?)</section>` regex, so any legal closing-
    tag spelling — `</section>`, `</section >` (trailing whitespace), or a
    newline before the `>` — is still recognized. A regex anchored to the
    exact literal string `</section>` misses these; a real HTML parser's
    handle_endtag fires the same regardless of how the tag was serialized."""

    def __init__(self, target_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.target_id = target_id
        self.found_html: str | None = None
        self._depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "section":
            if self._depth > 0:
                self._parts.append(self.get_starttag_text() or "")
            return
        if self._depth > 0:
            self._depth += 1
            self._parts.append(self.get_starttag_text() or "")
            return
        if dict(attrs).get("id") == self.target_id:
            self._depth = 1
            self._parts = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._depth > 0:
            self._parts.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag: str) -> None:
        if tag != "section" or self._depth == 0:
            if self._depth > 0:
                self._parts.append(f"</{tag}>")
            return
        self._depth -= 1
        if self._depth == 0:
            if self.found_html is None:
                self.found_html = "".join(self._parts)
        else:
            self._parts.append("</section>")

    def handle_data(self, data: str) -> None:
        if self._depth > 0:
            # Re-escape markup-syntax characters before appending. With
            # convert_charrefs=True, handle_data receives ALREADY-DECODED
            # text: an escaped code example like `&lt;span
            # data-cost-key="x"&gt;$112&lt;/span&gt;` decodes to the literal
            # text `<span data-cost-key="x">$112</span>` — indistinguishable,
            # once appended into the returned string, from a REAL <span> tag
            # that was never actually in the source. Re-escaping `<`, `>`,
            # and `&` (the only characters that make reparsed text look like
            # markup) makes the returned string round-trip safely through a
            # second HTMLParser pass (e.g. _cost_anchor_matches) while
            # leaving every other decoded character as plain text.
            self._parts.append(
                data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )

    def handle_comment(self, data: str) -> None:
        if self._depth > 0:
            self._parts.append(f"<!--{data}-->")


def _section_html(html: str, section_id: str) -> str | None:
    """Return the inner HTML of the first <section id="section_id"> in `html`,
    found via parsed tag structure (any legal attribute/closing-tag spelling),
    or None when that section is genuinely absent. Non-nesting semantics
    preserved (first section with a matching id wins) — the Heroku report
    skeleton never nests <section> elements."""
    parser = _SectionScopeParser(section_id)
    parser.feed(html)
    parser.close()
    return parser.found_html


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


class _CostAnchorParser(HTMLParser):
    """Collect the rendered text of every `data-cost-key="..."` element.

    Ported from validate-migration-report.py's parser (GCP). Uses the stdlib
    HTML parser rather than a regex so that (a) markup inside an HTML comment
    or a <template> subtree is never mistaken for a real anchor — comments
    are a distinct token the parser never re-tokenizes as tags, and
    <template> content is inert (never rendered) so its descendants are
    skipped even though the parser still walks their tags, and (b) nested
    child markup (`<span data-cost-key="x"><strong>$112</strong></span>`) is
    read through the anchored element's OWN matching close tag, not the
    first `</` encountered, by counting nested opens/closes of the same tag
    name. Character references are decoded automatically
    (`convert_charrefs=True`, the default).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[tuple[str, str]] = []  # (key, inner text)
        self._tag_name: str | None = None
        self._depth = 0
        self._pending_key = ""
        self._parts: list[str] = []
        self._template_depth = 0  # >0 while inside any <template> subtree

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "template":
            self._template_depth += 1
        if self._template_depth > 0:
            return  # <template> content is inert — never rendered, never an anchor
        if self._tag_name is not None:
            if tag == self._tag_name:
                self._depth += 1
            return
        key = dict(attrs).get("data-cost-key")
        if key:
            self._tag_name = tag
            self._depth = 1
            self._pending_key = key.lower()
            self._parts = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._template_depth > 0:
            return
        # A self-closed anchor (<span data-cost-key="x" />) has no text content;
        # treat it as an anchor with empty rendered text rather than ignoring it.
        if self._tag_name is None:
            key = dict(attrs).get("data-cost-key")
            if key:
                self.results.append((key.lower(), ""))

    def handle_endtag(self, tag: str) -> None:
        if tag == "template" and self._template_depth > 0:
            self._template_depth -= 1
            return
        if self._template_depth > 0:
            return
        if self._tag_name is None or tag != self._tag_name:
            return
        self._depth -= 1
        if self._depth == 0:
            self.results.append((self._pending_key, "".join(self._parts)))
            self._tag_name = None
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._template_depth > 0:
            return
        if self._tag_name is not None:
            self._parts.append(data)


def _cost_anchor_matches(html: str) -> list[tuple[str, str]]:
    """Parse `html` and return every (data-cost-key, rendered text) pair found
    outside of comments and other non-rendered markup (e.g. <template>)."""
    parser = _CostAnchorParser()
    parser.feed(html)
    parser.close()
    return parser.results


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
    - aws_monthly_balanced present in JSON + exec-costs present -> an anchor MUST
      exist INSIDE <section id="exec-costs">; a missing anchor there FAILs (an
      un-anchored wrong figure, or an anchor placed elsewhere e.g. decision-summary,
      must not pass) — mirrors validate-migration-report.py's required-anchors
      section scoping.
    - Anchor present anywhere + JSON value present but rendered dollars differ -> FAIL
      (any anchor is still cross-checked against the estimate, even outside exec-costs).
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

    for key, text in _cost_anchor_matches(html):
        key = key.lower()
        path = _COST_ANCHORS.get(key)
        if path is None:
            continue
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
        rendered = _normalize_money(text)
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

    # Required figures must be anchored INSIDE <section id="exec-costs"> when their
    # JSON value exists and that section is rendered. A redundant anchor elsewhere
    # (e.g. a decision-summary hero metric) is still cross-checked by the mismatch
    # loop above, but does not satisfy this requirement: exec-costs is the section
    # customers read as the authoritative cost comparison.
    exec_costs_html = _section_html(html, "exec-costs")
    if exec_costs_html is not None:
        exec_costs_keys = {k.lower() for k, _ in _cost_anchor_matches(exec_costs_html)}
        for key in _REQUIRED_COST_KEYS:
            path = _COST_ANCHORS[key]
            if _dig(est, path) is None:
                continue
            if key not in exec_costs_keys:
                errors.append(
                    f'missing data-cost-key="{key}" anchor inside '
                    f'<section id="exec-costs">; cannot confirm the rendered figure '
                    f"matches estimation-infra.json {'.'.join(path)} (wrap that "
                    f'figure in <span data-cost-key="{key}">...</span> inside '
                    f"exec-costs)"
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
