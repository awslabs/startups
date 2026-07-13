"""Query-Rewrite Guidance + Best-Effort SQL Translation (R13).

Per detected construct, emit a human-readable required change + effort indication.
For entities with SQL surface, also produce a best-effort Redshift translation using
sqlglot (illustrative only — requires validation before production use).
"""
from __future__ import annotations

import logging
import re

import sqlglot

from bq_assess.models import DetectedConstruct, EntityMetadata, TranslationResult

_GUIDANCE: dict[str, str] = {
    "JS_UDF": "JavaScript UDF has no Redshift equivalent — rewrite as Lambda UDF, Node.js recommended (high effort).",
    "UNNEST": "UNNEST over nested arrays — replace with Redshift FROM-clause unnest pattern: FROM t, t.arr AS x (medium effort).",
    "ARRAY_FN": "ARRAY_* function — replace with Redshift equivalent or SUPER array functions (medium effort).",
    "STRUCT_NAV": "Struct-path navigation (dot notation) — works as-is for Iceberg tables via Spectrum (low effort).",
    "FUNCTION_DRIFT": "Function name/semantic drift — rename or adjust argument order for Redshift dialect (low effort).",
}

_TIMESTAMPDIFF_RE = re.compile(
    r"\bTIMESTAMPDIFF\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+)\s*\)",
    re.IGNORECASE,
)

_SAFE_DIVIDE_RE = re.compile(
    r"\bSAFE_DIVIDE\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)",
    re.IGNORECASE,
)

_JS_UDF_RE = re.compile(r"\bLANGUAGE\s+js\b", re.IGNORECASE)


class RewriteGuide:
    """Generate human-readable rewrite guidance and best-effort SQL translation."""

    def guide(self, entity: EntityMetadata, constructs: list[DetectedConstruct]) -> list[str]:
        if not constructs:
            return []
        result: list[str] = []
        for c in constructs:
            text = _GUIDANCE.get(c.construct_class)
            if text is None:
                text = f"{c.construct_class}: {c.description} — review and adapt for Redshift."
            result.append(text)
        return result

    def translate(self, sql: str) -> TranslationResult:
        """Best-effort BQ→Redshift translation using sqlglot + post-processing."""
        if not sql or not sql.strip():
            return TranslationResult(
                redshift_sql="",
                confidence="LOW",
                warnings=["Empty SQL — nothing to translate."],
            )

        warnings: list[str] = []
        confidence = "HIGH"

        if _JS_UDF_RE.search(sql):
            warnings.append(
                "JavaScript UDF cannot be auto-translated — "
                "rewrite as Lambda UDF (Node.js recommended)."
            )
            confidence = "LOW"

        try:
            _sqlglot_logger = logging.getLogger("sqlglot")
            prev_level = _sqlglot_logger.level
            _sqlglot_logger.setLevel(logging.ERROR)
            try:
                results = sqlglot.transpile(sql, read="bigquery", write="redshift")
            finally:
                _sqlglot_logger.setLevel(prev_level)
            translated = "; ".join(results)
        except Exception as e:
            return TranslationResult(
                redshift_sql=f"-- [TRANSLATION FAILED: {type(e).__name__}]\n{sql}",
                confidence="LOW",
                warnings=[f"sqlglot could not parse this SQL: {e}"],
            )

        translated = self._post_fix(translated, warnings)

        if "BEGIN" in sql and ("DECLARE" in sql or "EXCEPTION" in sql or "FOR " in sql):
            warnings.append("Stored procedure with scripting constructs — partial translation only.")
            confidence = "LOW"

        if warnings:
            confidence = "LOW"

        return TranslationResult(
            redshift_sql=translated,
            confidence=confidence,
            warnings=warnings,
        )

    def _post_fix(self, sql: str, warnings: list[str]) -> str:
        """Apply post-processing fixes for known sqlglot gaps."""
        # Fix TIMESTAMPDIFF → DATEDIFF (sqlglot bug for TIMESTAMP_DIFF)
        if _TIMESTAMPDIFF_RE.search(sql):
            sql = _TIMESTAMPDIFF_RE.sub(r"DATEDIFF(\3, \2, \1)", sql)

        # Fix SAFE_DIVIDE (sqlglot passes it through unchanged)
        if _SAFE_DIVIDE_RE.search(sql):
            sql = _SAFE_DIVIDE_RE.sub(r"(\1) / NULLIF((\2), 0)", sql)
            warnings.append("SAFE_DIVIDE converted to x / NULLIF(y, 0) — verify NULL semantics.")

        return sql
