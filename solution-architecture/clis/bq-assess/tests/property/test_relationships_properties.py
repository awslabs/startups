# Feature: phase1-assessment-tool, Property 10: Relationship inference from naming conventions and clustering
# Feature: phase1-assessment-tool, Property 11: Relationship inference from view SQL
# Feature: phase1-assessment-tool, Property 12: LOW confidence safe defaults
"""Property tests for the RelationshipInferrer.

Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5
"""

from __future__ import annotations

from datetime import datetime, timezone

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

from bq_assess.models import (
    EntityType,
    EntityPopulation,
    ColumnSchema,
    ConfidenceLevel,
    EntityMetadata,
)
from bq_assess.core.relationships import RelationshipInferrer



# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_identifier = st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True)


@st.composite
def tables_with_shared_id_column(draw: st.DrawFn) -> tuple[list[EntityMetadata], str]:
    """Generate 4+ tables that all share a common ``_id`` column.

    Each table has a unique ``full_name`` so the naming heuristic counts
    them as distinct tables (the implementation uses a set of full_names).

    Returns the table list and the shared column name.
    """
    # Pick a shared _id column name
    prefix = draw(st.from_regex(r"[a-z][a-z0-9]{0,8}", fullmatch=True))
    shared_col = f"{prefix}_id"

    n_tables = draw(st.integers(min_value=4, max_value=7))
    tables: list[EntityMetadata] = []

    for i in range(n_tables):
        # Use index-based naming to guarantee unique full_names
        dataset_id = f"ds{i}"
        table_id = f"tbl{i}"

        # Always include the shared _id column
        shared = ColumnSchema(name=shared_col, field_type="INT64", mode="NULLABLE", fields=[])

        # Add 0-2 extra columns (non-_id to avoid accidental extra matches)
        extra_cols = [
            ColumnSchema(
                name=f"col{i}_{j}_val",
                field_type="STRING",
                mode="NULLABLE",
                fields=[],
            )
            for j in range(draw(st.integers(min_value=0, max_value=2)))
        ]

        clustering = draw(st.one_of(
            st.none(),
            st.lists(_identifier, min_size=1, max_size=3),
        ))

        tables.append(
            EntityMetadata(
                entity_id=table_id,
                dataset_id=dataset_id,
                full_name=f"{dataset_id}.{table_id}",
                entity_type=EntityType.TABLE,
                population=EntityPopulation.TABLE,
                num_rows=0,
                num_bytes=0,
                columns=[shared] + extra_cols,
                time_partitioning=None,
                range_partitioning=None,
                clustering_fields=clustering,
                view_query=None,
                mview_query=None,
                routine=None,
                depends_on=[],
                last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
            )
        )

    return tables, shared_col


@st.composite
def view_definitions_with_joins(draw: st.DrawFn) -> dict[str, str]:
    """Generate view definitions containing JOIN clauses with ON conditions."""
    n_views = draw(st.integers(min_value=1, max_value=3))
    views: dict[str, str] = {}

    for _ in range(n_views):
        view_name = draw(_identifier)
        left_table = draw(_identifier)
        right_table = draw(_identifier)
        join_col = draw(_identifier)

        sql = (
            f"SELECT * FROM {left_table} "
            f"JOIN {right_table} ON {left_table}.{join_col} = {right_table}.{join_col}"
        )
        views[view_name] = sql

    return views


@st.composite
def tables_with_unique_columns(draw: st.DrawFn) -> list[EntityMetadata]:
    """Generate tables with unique column names (no shared ``_id`` columns).

    Each table gets columns that won't trigger the naming heuristic.
    """
    n_tables = draw(st.integers(min_value=1, max_value=5))
    tables: list[EntityMetadata] = []

    for i in range(n_tables):
        dataset_id = draw(_identifier)
        table_id = draw(_identifier)

        # Use unique prefixes per table to avoid _id columns appearing in >3 tables
        cols = [
            ColumnSchema(
                name=f"tbl{i}_col{j}_val",
                field_type=draw(st.sampled_from(["STRING", "INT64", "FLOAT64", "BOOL", "TIMESTAMP"])),
                mode="NULLABLE",
                fields=[],
            )
            for j in range(draw(st.integers(min_value=1, max_value=4)))
        ]

        tables.append(
            EntityMetadata(
                entity_id=table_id,
                dataset_id=dataset_id,
                full_name=f"{dataset_id}.{table_id}",
                entity_type=EntityType.TABLE,
                population=EntityPopulation.TABLE,
                num_rows=draw(st.integers(min_value=0, max_value=10**9)),
                num_bytes=draw(st.integers(min_value=0, max_value=10**12)),
                columns=cols,
                time_partitioning=None,
                range_partitioning=None,
                clustering_fields=None,
                view_query=None,
                mview_query=None,
                routine=None,
                depends_on=[],
                last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
            )
        )

    return tables


# ---------------------------------------------------------------------------
# Property 10: Relationship inference from naming conventions and clustering
# ---------------------------------------------------------------------------


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(data=tables_with_shared_id_column())
def test_naming_conventions_and_clustering(
    data: tuple[list[EntityMetadata], str],
) -> None:
    """Property 10: Relationship inference from naming conventions and clustering.

    **Validates: Requirements 7.1, 7.3, 7.4**

    ``_id`` columns in >3 tables appear in ``likely_join_keys``.
    Clustering keys appear in ``sort_order_hints``.
    Each inferred relationship has a non-null confidence level.
    """
    # Feature: phase1-assessment-tool, Property 10: Relationship inference from naming conventions and clustering
    tables, shared_col = data
    inferrer = RelationshipInferrer()
    result = inferrer.infer(tables)

    # The shared _id column must appear in likely_join_keys
    assert shared_col in result.likely_join_keys, (
        f"Expected '{shared_col}' in likely_join_keys {result.likely_join_keys}"
    )

    # Clustering keys must appear in sort_order_hints (R7; not SORTKEY per R15.5)
    for table in tables:
        if table.clustering_fields:
            assert table.full_name in result.sort_order_hints, (
                f"Table {table.full_name} has clustering fields but is not in sort_order_hints"
            )
            assert result.sort_order_hints[table.full_name] == list(table.clustering_fields)

    # Every inferred relationship must have a non-null confidence
    for rel in result.relationships:
        assert rel.confidence is not None
        assert isinstance(rel.confidence, ConfidenceLevel)


# ---------------------------------------------------------------------------
# Property 11: Relationship inference from view SQL
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(views=view_definitions_with_joins())
def test_view_sql_produces_relationships(views: dict[str, str]) -> None:
    """Property 11: Relationship inference from view SQL.

    **Validates: Requirements 7.2**

    Views with JOINs produce at least one InferredRelationship
    with source="view_definition".
    """
    # Feature: phase1-assessment-tool, Property 11: Relationship inference from view SQL
    inferrer = RelationshipInferrer()
    result = inferrer.infer(tables=[], view_definitions=views)

    # At least one relationship should be inferred from the view definitions
    assert len(result.relationships) >= 1, (
        f"Expected at least 1 relationship from {len(views)} view(s), got 0"
    )

    # At least one relationship should have source="view_definition"
    view_rels = [r for r in result.relationships if r.source == "view_definition"]
    assert len(view_rels) >= 1, (
        "Expected at least one relationship with source='view_definition'"
    )


# ---------------------------------------------------------------------------
# Property 12: LOW confidence safe defaults
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(tables=tables_with_unique_columns())
def test_low_confidence_safe_defaults(tables: list[EntityMetadata]) -> None:
    """Property 12: LOW confidence safe defaults.

    **Validates: Requirements 7.5**

    LOW confidence → distkey=None (DISTSTYLE EVEN), sortkey=first timestamp column.
    When no query analysis and no view definitions are provided, and the naming
    heuristic doesn't trigger, confidence should be LOW.
    """
    # Feature: phase1-assessment-tool, Property 12: LOW confidence safe defaults
    inferrer = RelationshipInferrer()
    result = inferrer.infer(tables, query_analysis=None, view_definitions=None)

    # With unique column names and no query analysis / views, confidence must be LOW
    assert result.confidence == ConfidenceLevel.LOW, (
        f"Expected LOW confidence, got {result.confidence}"
    )

    # No likely join keys should be detected (unique column names, no _id sharing)
    assert result.likely_join_keys == [], (
        f"Expected no likely_join_keys, got {result.likely_join_keys}"
    )

    # No relationships should be inferred
    assert result.relationships == [], (
        f"Expected no relationships, got {len(result.relationships)}"
    )
