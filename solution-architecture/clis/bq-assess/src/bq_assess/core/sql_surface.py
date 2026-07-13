"""SQL Surface assembly + BigQuery construct detection + anonymization (R10, R22.4).

The SQL Surface is every piece of Source SQL the Query Complexity axis scores: view SQL,
materialized-view SQL, and persistent UDF/procedure bodies (auto-captured), plus inline
``CREATE TEMP FUNCTION`` and ad-hoc query text when query logs are provided (R10.1, R10.2).

``detect()`` scans a SQL string for BigQuery-specific constructs in five classes
(R10.3); ``anonymize()`` strips string and numeric literals before anything is stored or
reported (R10.4 / R22.4); ``assemble()`` builds the per-entity surface keyed by full_name
and attributes each construct to its entity (R10.5).

Issue #19 / 3.1.

⚠️ SEAM (see SCRUM_NOTES § construct_class vocabulary): ``DetectedConstruct.construct_class``
is a plain ``str``. The five canonical values below are the contract the Query Complexity
scorer (``scoring/complexity.py``, Ryan / #21) keys on. They match design.md and issue #21's
description. Hardening this to an Enum on ``models.py`` is an open option pending Ryan — do
NOT diverge from these strings without updating both sides.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from bq_assess.models import DetectedConstruct, EntityMetadata

# ---- Canonical construct classes (the frozen seam with scoring/complexity) ----

UNNEST = "UNNEST"
FUNCTION_DRIFT = "FUNCTION_DRIFT"
ARRAY_FN = "ARRAY_FN"
STRUCT_NAV = "STRUCT_NAV"
JS_UDF = "JS_UDF"

CONSTRUCT_CLASSES = (UNNEST, FUNCTION_DRIFT, ARRAY_FN, STRUCT_NAV, JS_UDF)


# ---------------------------------------------------------------------------
# Anonymization (R10.4 / R22.4) — salvaged from core/analyzer.py
# ---------------------------------------------------------------------------

# Single-quoted string literals (handles empty strings; greedy within quotes).
_STRING_LITERAL_RE = re.compile(r"'[^']*'")

# Numeric literals following an operator/keyword/punctuation, so digits inside
# identifiers (e.g. col1, table2) are preserved.
_NUMERIC_LITERAL_RE = re.compile(r"(?<=[\s=><!(,+\-*/])\d+\.?\d*(?=[\s,);]|$)")


# ---------------------------------------------------------------------------
# Construct detection patterns (R10.3)
# ---------------------------------------------------------------------------

# UNNEST(...) array-unnesting.
_UNNEST_RE = re.compile(r"\bUNNEST\s*\(", re.IGNORECASE)

# ARRAY_* scalar/aggregate functions (ARRAY_AGG, ARRAY_LENGTH, ARRAY_TO_STRING, ...)
# and ARRAY[...] / ARRAY<...>(...) constructors.
_ARRAY_FN_RE = re.compile(r"\bARRAY_[A-Z_]+\s*\(|\bARRAY\s*[<\[]", re.IGNORECASE)

# Function-name / semantic drift: BigQuery functions whose Redshift equivalent differs in
# name or argument order. Conservative, high-signal set (R10.3 names DATE_DIFF, ARRAY_LENGTH).
_FUNCTION_DRIFT_NAMES = (
    "DATE_DIFF",
    "DATETIME_DIFF",
    "TIMESTAMP_DIFF",
    "ARRAY_LENGTH",
    "SAFE_CAST",
    "FORMAT_DATE",
    "PARSE_DATE",
    "GENERATE_ARRAY",
    "GENERATE_DATE_ARRAY",
    "APPROX_QUANTILES",
)
_FUNCTION_DRIFT_RE = re.compile(
    r"\b(" + "|".join(_FUNCTION_DRIFT_NAMES) + r")\s*\(", re.IGNORECASE
)

# Nested STRUCT path navigation: dotted access two or more levels deep
# (e.g. payload.user.id). Avoids matching simple alias.col by requiring >=2 dots.
_STRUCT_NAV_RE = re.compile(r"\b\w+\.\w+\.\w+\b")

# JavaScript UDF: LANGUAGE js (in a CREATE FUNCTION / TEMP FUNCTION body).
_JS_UDF_RE = re.compile(r"\bLANGUAGE\s+js\b", re.IGNORECASE)

# Inline temp function marker (R10.2) — used by assemble() when scanning ad-hoc query text.
_TEMP_FUNCTION_RE = re.compile(r"\bCREATE\s+(?:TEMP|TEMPORARY)\s+FUNCTION\b", re.IGNORECASE)


_DETECTORS: list[tuple[str, re.Pattern, str]] = [
    (JS_UDF, _JS_UDF_RE, "JavaScript UDF — no Query Engine equivalent; rewrite to Python/Lambda UDF."),
    (UNNEST, _UNNEST_RE, "UNNEST over nested/array data — rewrite array-unnesting for the Query Engine."),
    (ARRAY_FN, _ARRAY_FN_RE, "ARRAY_* function or ARRAY constructor — dialect adaptation required."),
    (FUNCTION_DRIFT, _FUNCTION_DRIFT_RE, "BigQuery function with name/argument-order drift — adapt to the Query Engine dialect."),
    (STRUCT_NAV, _STRUCT_NAV_RE, "Nested STRUCT path navigation — verify struct access on the Query Engine."),
]


class SQLSurfaceAnalyzer:
    """Assembles the SQL Surface and detects BigQuery-specific constructs (R10)."""

    # ------------------------------------------------------------------
    # Anonymization (R10.4 / R22.4)
    # ------------------------------------------------------------------

    def anonymize(self, sql: str) -> str:
        """Replace string and numeric literals with ``?`` placeholders.

        String literals → ``'?'``; numeric literals after operators/keywords → ``?``.
        Identifiers containing digits (``col1``, ``table2``) are preserved. After this,
        no original literal value remains (P17).
        """
        if not sql:
            return sql
        result = _STRING_LITERAL_RE.sub("'?'", sql)
        result = _NUMERIC_LITERAL_RE.sub("?", result)
        return result

    # ------------------------------------------------------------------
    # Construct detection (R10.3)
    # ------------------------------------------------------------------

    def detect(self, sql: str) -> list[DetectedConstruct]:
        """Detect BigQuery-specific constructs in a single SQL string.

        Returns one :class:`DetectedConstruct` per construct *class* present (deduped by
        class), each carrying an anonymized snippet (R10.4) and a human-readable description.
        Order is stable and deterministic (the detector order above).
        """
        if not sql:
            return []

        constructs: list[DetectedConstruct] = []
        for construct_class, pattern, description in _DETECTORS:
            match = pattern.search(sql)
            if match is None:
                continue
            constructs.append(
                DetectedConstruct(
                    construct_class=construct_class,
                    snippet=self._snippet(sql, match),
                    description=description,
                )
            )
        return constructs

    # ------------------------------------------------------------------
    # Surface assembly (R10.1, R10.2, R10.5)
    # ------------------------------------------------------------------

    def assemble(
        self,
        entities: Iterable[EntityMetadata],
        query_log_text: list[str] | None = None,
    ) -> dict[str, list[str]]:
        """Build the SQL Surface: a map of entity full_name → list of SQL strings.

        Auto-captured surface (always available, R10.1):
          - views → ``view_query``
          - materialized views → ``mview_query``
          - routines → ``routine.body``
        Log-only surface (only when ``query_log_text`` is provided, R10.2):
          - each ad-hoc query / inline ``CREATE TEMP FUNCTION`` body, keyed under
            ``"__ad_hoc__"`` since it is not owned by a defined entity.

        All SQL is anonymized before being placed in the surface (R10.4 / R22.4).
        """
        surface: dict[str, list[str]] = {}

        for entity in entities:
            sqls: list[str] = []
            if entity.view_query:
                sqls.append(entity.view_query)
            if entity.mview_query:
                sqls.append(entity.mview_query)
            if entity.routine is not None and entity.routine.body:
                sqls.append(entity.routine.body)
            if sqls:
                surface[entity.full_name] = [self.anonymize(s) for s in sqls]

        if query_log_text:
            ad_hoc = [self.anonymize(q) for q in query_log_text if q]
            if ad_hoc:
                surface["__ad_hoc__"] = ad_hoc

        return surface

    def detect_for_entities(
        self,
        entities: Iterable[EntityMetadata],
        query_log_text: list[str] | None = None,
    ) -> dict[str, list[DetectedConstruct]]:
        """Attribute detected constructs to each entity (R10.5).

        Convenience over ``assemble`` + ``detect``: returns full_name → constructs, including
        the ``"__ad_hoc__"`` bucket for log-sourced SQL. Entities with no detected construct
        are omitted (callers treat absence as "no constructs", not failure).
        """
        result: dict[str, list[DetectedConstruct]] = {}
        for full_name, sqls in self.assemble(entities, query_log_text).items():
            found: list[DetectedConstruct] = []
            seen: set[str] = set()
            for sql in sqls:
                for c in self.detect(sql):
                    if c.construct_class not in seen:
                        seen.add(c.construct_class)
                        found.append(c)
            if found:
                result[full_name] = found
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _snippet(self, sql: str, match: re.Match, width: int = 40) -> str:
        """Return an anonymized window around *match* for human context (R10.4)."""
        start = max(0, match.start() - width // 2)
        end = min(len(sql), match.end() + width // 2)
        window = sql[start:end].replace("\n", " ").strip()
        return self.anonymize(window)
