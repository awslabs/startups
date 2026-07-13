# Feature: phase1-assessment-tool, Property 15: Query log extraction completeness
# Feature: phase1-assessment-tool, Property 16: Query text anonymization
"""Property tests for the QueryAnalyzer.

Validates: Requirements 9.4, 9.5, 14.4
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import hypothesis.strategies as st
from hypothesis import given, settings

from bq_assess.core.analyzer import QueryAnalyzer

from tests.conftest import sql_query_with_literals

# Shared identifier strategy for generating table/column names
_identifier = st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_query_log_entries(queries: list[str]) -> list[dict[str, str]]:
    """Wrap raw SQL strings into the JSON format expected by analyze_from_file."""
    return [{"query": q} for q in queries]


# ---------------------------------------------------------------------------
# Strategy: generate realistic SQL queries with FROM (and optional JOIN/WHERE)
# ---------------------------------------------------------------------------

@st.composite
def _sql_query_with_from(draw: st.DrawFn) -> str:
    """Generate a SQL query that always has a FROM clause referencing a table.

    Optionally includes JOIN and WHERE clauses so that the analyzer can
    extract join_patterns and where_columns.
    """
    dataset = draw(_identifier)
    table = draw(_identifier)
    _col1 = draw(_identifier)
    _col2 = draw(_identifier)

    base = f"SELECT * FROM {dataset}.{table}"

    include_join = draw(st.booleans())
    include_where = draw(st.booleans())

    if include_join:
        join_dataset = draw(_identifier)
        join_table = draw(_identifier)
        join_alias = draw(st.from_regex(r"[a-z]{1,4}", fullmatch=True))
        base_alias = draw(st.from_regex(r"[a-z]{1,4}", fullmatch=True))
        join_col = draw(_identifier)
        base += (
            f" {base_alias}"
            f" JOIN {join_dataset}.{join_table} {join_alias}"
            f" ON {base_alias}.{join_col} = {join_alias}.{join_col}"
        )

    if include_where:
        where_alias = draw(st.from_regex(r"[a-z]{1,4}", fullmatch=True))
        where_col = draw(_identifier)
        base += f" WHERE {where_alias}.{where_col} = 42"

    return base


# ---------------------------------------------------------------------------
# Property 15: Query log extraction completeness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(queries=st.lists(_sql_query_with_from(), min_size=1, max_size=5))
def test_query_log_extraction_completeness(queries: list[str]) -> None:
    """Property 15: Query log extraction completeness.

    **Validates: Requirements 9.4**

    Non-empty logs produce non-empty table_query_counts, valid where_columns,
    join_patterns, and correct hub_tables.  The key invariant is that every
    generated query has a FROM clause, so table_query_counts must be non-empty.
    The result must also be marked as anonymized.
    """
    # Feature: phase1-assessment-tool, Property 15: Query log extraction completeness
    analyzer = QueryAnalyzer()

    entries = _build_query_log_entries(queries)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as tmp:
        json.dump(entries, tmp)
        tmp_path = tmp.name

    try:
        result = analyzer.analyze_from_file(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Every query has a FROM clause → at least one table must be counted
    assert len(result.table_query_counts) > 0, (
        "Expected non-empty table_query_counts for queries with FROM clauses"
    )

    # Structural checks: fields are the correct types
    assert isinstance(result.where_columns, dict)
    assert isinstance(result.join_patterns, dict)
    assert isinstance(result.hub_tables, list)

    # Hub tables must be a subset of known tables (from table_query_counts
    # or join_patterns keys)
    known_tables = set(result.table_query_counts.keys())
    for patterns_list in result.join_patterns.values():
        for jp in patterns_list:
            known_tables.add(jp.left_table)
            known_tables.add(jp.right_table)
    for hub in result.hub_tables:
        assert hub in known_tables, (
            f"Hub table '{hub}' not found in known tables: {known_tables}"
        )

    # The result must be anonymized
    assert result.anonymized is True, "Expected anonymized=True"


# ---------------------------------------------------------------------------
# Property 16: Query text anonymization
# ---------------------------------------------------------------------------

# Regex to find single-quoted string literals (excluding the placeholder '?')
_REMAINING_STRING_LITERAL_RE = re.compile(r"'(?!\?')[^']*'")


@settings(max_examples=100)
@given(sql=sql_query_with_literals())
def test_query_text_anonymization(sql: str) -> None:
    """Property 16: Query text anonymization.

    **Validates: Requirements 9.5, 14.4**

    String and numeric literals are replaced with placeholders.  No original
    string literal values remain in the anonymized output.
    """
    # Feature: phase1-assessment-tool, Property 16: Query text anonymization
    analyzer = QueryAnalyzer()
    result = analyzer.anonymize_query(sql)

    # --- String literal check ---
    # No single-quoted string literals should remain except the placeholder '?'
    remaining = _REMAINING_STRING_LITERAL_RE.findall(result)
    assert remaining == [], (
        f"Found non-placeholder string literals in anonymized output: {remaining}\n"
        f"Original: {sql}\nAnonymized: {result}"
    )

    # Extract the original string literal value from the SQL.
    # The sql_query_with_literals strategy always embeds at least one 'value'.
    original_strings = re.findall(r"'([^']+)'", sql)
    for orig in original_strings:
        # The original literal value (without quotes) should not appear in
        # the anonymized result — unless it happens to be a substring of a
        # table/column name (which is extremely unlikely with the strategy).
        # We check that the *quoted* form is gone.
        assert f"'{orig}'" not in result, (
            f"Original string literal '{orig}' still present in anonymized output.\n"
            f"Original: {sql}\nAnonymized: {result}"
        )

    # --- Numeric literal check ---
    # Extract numeric literals from the original SQL.  The strategy places
    # them after operators (=, >, BETWEEN, AND).  We look for numbers that
    # appear after such tokens in the original.
    original_nums = re.findall(
        r"(?<=[\s=><!(,+\-*/])-?\d+\.?\d*", sql
    )
    for num_str in original_nums:
        # Skip small numbers (0, 1, etc.) that could appear in identifiers
        try:
            val = float(num_str)
        except ValueError:
            continue
        if abs(val) <= 1:
            continue
        # The exact numeric token should not appear in the same operator
        # context in the anonymized result.  We verify the specific token
        # preceded by an operator is replaced.
        pattern = re.compile(
            r"(?<=[\s=><!(,+\-*/])" + re.escape(num_str) + r"(?=[\s,);]|$)"
        )
        assert not pattern.search(result), (
            f"Numeric literal '{num_str}' still present in anonymized output.\n"
            f"Original: {sql}\nAnonymized: {result}"
        )
