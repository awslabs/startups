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
from html.parser import HTMLParser
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


class _TagAttrCollector(HTMLParser):
    """Collect (tag, attrs-dict, is_self_closed) for every start tag, using the
    stdlib parser rather than a literal-syntax regex. This accepts any legal
    HTML attribute spelling — quoted or unquoted values, spaces around `=`,
    single or double quotes — instead of only the exact `name="value"` form a
    hand-rolled regex happens to match."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None], bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs), False))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs), True))


def _collect_tags(html: str) -> list[tuple[str, dict[str, str | None], bool]]:
    parser = _TagAttrCollector()
    parser.feed(html)
    parser.close()
    return parser.tags


def _html_lang_declared(html: str) -> bool:
    for tag, attrs, _ in _collect_tags(html):
        if tag != "html":
            continue
        lang = attrs.get("lang")
        return bool(lang) and bool(re.fullmatch(r"[a-z]{2}(?:-[A-Za-z0-9]+)?", lang, re.IGNORECASE))
    return False


NO_ELIGIBLE_COMMITMENT_SENTENCE = (
    "no 1-year/3-year commitment product applies to this architecture"
)


class _OpportunityRowParser(HTMLParser):
    """Stdlib-parser scan for a populated <td> inside a <table> — parses actual
    table structure rather than matching raw HTML source, so it:
      - decodes character references (convert_charrefs=True) before text is
        seen, so a cell containing only "&nbsp;"/"&#160;" is correctly treated
        as blank rather than non-empty literal markup;
      - never sees text inside HTML comments (HTMLParser's tokenizer routes
        comments to handle_comment, not handle_data), so a commented-out
        <tr>...</tr> can never register as a populated row;
      - tracks "inside <table>, inside <tr>, inside <td>" state directly,
        without requiring an explicit <tbody> — a <table><tr><td> with no
        <tbody> is valid HTML (browsers infer an implicit tbody) and must be
        treated the same as one with an explicit <tbody>.
    <th> cells are deliberately excluded — header rows never count as an
    opportunity row, regardless of tbody/thead placement."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found = False
        self._table_depth = 0
        self._tr_depth = 0
        self._td_open = False  # a <td> is currently open (its end tag may be omitted)
        self._td_has_text = False

    def _in_table(self) -> bool:
        return self._table_depth > 0

    def _close_cell(self) -> None:
        """Finalize whatever <td> is currently open, exactly as a real HTML
        parser would when the cell's end tag is omitted: the HTML Standard
        permits a <td> end tag to be omitted immediately before the next
        <td>/<th>, or before its parent <tr>/<table> closes. Only checking
        text on an EXPLICIT handle_endtag("td") missed every cell written
        with an omitted end tag (e.g. `<table><tr><td>text</tr></table>`,
        which never fires handle_endtag("td") at all) — a populated,
        perfectly valid compact table would then silently register as
        empty."""
        if self._td_open and self._td_has_text:
            self.found = True
        self._td_open = False
        self._td_has_text = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table_depth += 1
        elif tag == "tr" and self._in_table():
            self._close_cell()  # any cell open from a previous row must not leak across rows
            self._tr_depth += 1
        elif tag in ("td", "th") and self._tr_depth > 0:
            self._close_cell()  # a new cell always implicitly closes any sibling cell still open
            if tag == "td":
                self._td_open = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("td", "th") and self._tr_depth > 0:
            self._close_cell()  # a self-closed <td/> or <th/> can never carry text content

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self._close_cell()
        elif tag == "tr":
            self._close_cell()
            if self._tr_depth > 0:
                self._tr_depth -= 1
        elif tag == "table":
            self._close_cell()
            if self._table_depth > 0:
                self._table_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._td_open and data.strip():
            self._td_has_text = True


def _has_populated_opportunity_row(body: str) -> bool:
    """True if any <tr> inside a <table> has a <td> (not <th>) with non-empty
    text content — i.e. an actual opportunity row, not just a header row, an
    empty cell, a whitespace-only/entity-only cell, or a commented-out row."""
    parser = _OpportunityRowParser()
    parser.feed(body)
    parser.close()
    return parser.found


def _validate_optimization_content(body: str) -> list[str]:
    """The cost-optimization section must render EITHER a populated opportunities
    table (a real <tbody> row with data) OR the explicit no-eligible-commitment
    sentence — nothing else counts as content. This is a positive check, not
    "any leftover text after stripping headings/<th>": that older approach let a
    heading, column headers, AND any other prose (e.g. the credits disclaimer
    that accompanies a populated table, or explanatory filler) satisfy the
    requirement even with an empty <tbody>. Only a real opportunity row or the
    literal no-eligible sentence can pass."""
    if _has_populated_opportunity_row(body):
        return []
    text = re.sub(r"<[^>]+>", " ", body).lower()
    text = re.sub(r"\s+", " ", text)
    if NO_ELIGIBLE_COMMITMENT_SENTENCE in text:
        return []
    return [
        '<section id="cost-optimization"> has no substantive content — render a '
        "populated opportunity row (not just column headers, an empty <tbody>, or "
        "other prose like the credits disclaimer) or the exact "
        f'"{NO_ELIGIBLE_COMMITMENT_SENTENCE}" sentence, never a blank, '
        "heading-only, or table-header-only section"
    ]


def _class_tokens(html_fragment: str) -> set[str]:
    """Return the set of all `class` attribute tokens across every tag in the
    fragment, parsed via the stdlib HTMLParser (the same approach already used
    for lang/scope/aria-label) rather than a literal `class="value"` regex. This
    accepts any legal spelling — `class="a b"`, `class = "a b"`, or an unquoted
    single token like `class=verdict-headline` — so equivalent HTML always
    produces the same tokens regardless of formatting."""
    tokens: set[str] = set()
    for _, attrs, _ in _collect_tags(html_fragment):
        cls = attrs.get("class")
        if cls:
            tokens.update(cls.split())
    return tokens


def _validate_verdict(html: str, migration_dir: Path | None) -> list[str]:
    """Typography-first verdict rules (skill: verdict is the section thesis and
    must never be a colored-pill row)."""
    errors: list[str] = []
    summary = _section_html(html, "decision-summary")
    if summary is None:
        return errors  # missing-section already reported by the required-ID check

    summary_classes = _class_tokens(summary)

    # Colored pill badges are banned outright (not merely as the "sole" carrier).
    if any(token.startswith("badge-verdict-") for token in summary_classes):
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
    if recommendation_outcome and "verdict-headline" not in summary_classes:
        errors.append(
            "estimation-infra.json declares recommendation.outcome but "
            "decision-summary has no verdict-headline element "
            '(render outcome_label as <p class="verdict-headline">…</p>)'
        )
    return errors


class _AccessibilityParser(HTMLParser):
    """Stdlib-parser accessibility scan: <th scope> and <figure aria-label> +
    <figcaption>. Using the parser (rather than a literal `name="value"` regex)
    accepts any legal HTML attribute syntax — `scope=col`, `scope = "col"`,
    single quotes, etc. — the same attribute in different valid spellings must
    not flip a validator result. VOID_ELEMENTS avoids mis-tracking self-closing
    tags (e.g. <br>) as unclosed ancestors."""

    VOID_ELEMENTS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.table_issues: list[int] = []  # 1-based table index with a scope-less <th>
        self.figure_issues: list[tuple[int, bool, bool]] = []  # (index, has_aria_label, has_figcaption)
        self._table_index = 0
        self._figure_index = 0
        self._table_depth = 0  # >0 while inside a <table> (nesting-tolerant)
        self._table_bad_at: dict[int, bool] = {}
        self._figure_stack: list[dict[str, bool | None]] = []

    def _in_table(self) -> bool:
        return self._table_depth > 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._table_index += 1
                self._table_bad_at[self._table_index] = False
        elif tag == "th" and self._in_table():
            scope = attr_map.get("scope")
            if not (scope and scope.lower() in ("col", "row")):
                self._table_bad_at[self._table_index] = True
        elif tag == "figure":
            self._figure_index += 1
            aria_label = attr_map.get("aria-label")
            self._figure_stack.append(
                {
                    "index": self._figure_index,
                    "has_aria_label": bool(aria_label and aria_label.strip()),
                    "has_figcaption": False,
                }
            )
        elif tag == "figcaption" and self._figure_stack:
            self._figure_stack[-1]["has_figcaption"] = True
        if tag not in self.VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Self-closed tags never open a scope for descendants (e.g. a self-closed
        # <figure /> can never contain a <figcaption>) — handled naturally since
        # we don't push onto self.stack or self._figure_stack for these.
        pass

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._table_depth > 0:
            self._table_depth -= 1
            if self._table_depth == 0:
                if self._table_bad_at.get(self._table_index):
                    self.table_issues.append(self._table_index)
        elif tag == "figure" and self._figure_stack:
            fig = self._figure_stack.pop()
            self.figure_issues.append(
                (fig["index"], fig["has_aria_label"], fig["has_figcaption"])
            )
        while self.stack and tag in self.stack:
            popped = self.stack.pop()
            if popped == tag:
                break


def _validate_accessibility(html: str) -> list[str]:
    """Dependency-free WCAG-oriented semantics — the safe subset the Heroku
    one-pager emits (no single-<h1> / per-table-<caption> requirement)."""
    errors: list[str] = []
    if not _html_lang_declared(html):
        errors.append("accessibility: <html> must declare a valid lang attribute")

    body = re.sub(r"<style\b.*?</style>", "", html, flags=re.IGNORECASE | re.DOTALL)
    parser = _AccessibilityParser()
    parser.feed(body)
    parser.close()

    for index in parser.table_issues:
        errors.append(
            f'accessibility: table {index} header cells must declare '
            'scope="col" or scope="row"'
        )

    for index, has_aria_label, has_figcaption in parser.figure_issues:
        if not has_aria_label:
            errors.append(f"accessibility: figure {index} must have an aria-label")
        if not has_figcaption:
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

    # cost-optimization must carry substantive content (generate-report.md Step 3
    # item 6: a table of real opportunity rows, or the explicit no-eligible-commitment
    # sentence — never empty, and never satisfied by a heading or table-header text
    # alone). A heading like "Cost Optimization Opportunities" or a table with only
    # column headers and an empty <tbody> must not pass as content.
    if counts.get("cost-optimization", 0) >= 1:
        body = _section_html(html, "cost-optimization") or ""
        errors.extend(_validate_optimization_content(body))

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
