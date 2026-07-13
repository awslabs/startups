"""Unit tests for the RelationshipInferrer.

Requirements: 7.1, 7.2, 7.3
"""

from __future__ import annotations

from datetime import datetime, timezone

from bq_assess.core.analyzer import JoinPattern, QueryAnalysis
from bq_assess.core.relationships import RelationshipInferrer
from bq_assess.models import ColumnSchema, ConfidenceLevel, EntityMetadata, EntityType, EntityPopulation


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_table(
    table_id: str = "test_table",
    dataset_id: str = "test_dataset",
    columns: list[ColumnSchema] | None = None,
    clustering_fields: list[str] | None = None,
) -> EntityMetadata:
    """Build a minimal EntityMetadata (TABLE) for relationship tests."""
    if columns is None:
        columns = [ColumnSchema(name="id", field_type="INT64", mode="REQUIRED", fields=[])]
    return EntityMetadata(
        entity_id=table_id,
        dataset_id=dataset_id,
        full_name=f"{dataset_id}.{table_id}",
        entity_type=EntityType.TABLE,
        population=EntityPopulation.TABLE,
        num_rows=100,
        num_bytes=1024,
        columns=columns,
        time_partitioning=None,
        range_partitioning=None,
        clustering_fields=clustering_fields,
        view_query=None,
        mview_query=None,
        routine=None,
        depends_on=[],
        last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


# ── 1. _id column detection (naming heuristic) ──────────────────────────


def test_id_column_detected_in_more_than_3_tables() -> None:
    """customer_id in 4 tables → appears in likely_join_keys.

    Requirements: 7.1
    """
    tables = [
        _make_table(
            table_id=f"table_{i}",
            dataset_id="ds",
            columns=[
                ColumnSchema(name="customer_id", field_type="INT64", mode="NULLABLE", fields=[]),
                ColumnSchema(name="value", field_type="STRING", mode="NULLABLE", fields=[]),
            ],
        )
        for i in range(4)
    ]

    result = RelationshipInferrer().infer(tables)

    assert "customer_id" in result.likely_join_keys


def test_id_column_not_detected_in_3_or_fewer_tables() -> None:
    """order_id in only 3 tables → NOT in likely_join_keys.

    Requirements: 7.1
    """
    tables = [
        _make_table(
            table_id=f"table_{i}",
            dataset_id="ds",
            columns=[
                ColumnSchema(name="order_id", field_type="INT64", mode="NULLABLE", fields=[]),
            ],
        )
        for i in range(3)
    ]

    result = RelationshipInferrer().infer(tables)

    assert "order_id" not in result.likely_join_keys


def test_id_column_creates_pairwise_relationships() -> None:
    """customer_id in 4 tables → pairwise InferredRelationships created.

    Requirements: 7.1
    """
    tables = [
        _make_table(
            table_id=f"table_{i}",
            dataset_id="ds",
            columns=[
                ColumnSchema(name="customer_id", field_type="INT64", mode="NULLABLE", fields=[]),
            ],
        )
        for i in range(4)
    ]

    result = RelationshipInferrer().infer(tables)

    # 4 tables → C(4,2) = 6 pairwise relationships
    naming_rels = [r for r in result.relationships if r.source == "naming_convention"]
    assert len(naming_rels) == 6
    for rel in naming_rels:
        assert rel.join_column == "customer_id"
        assert rel.confidence == ConfidenceLevel.MEDIUM


# ── 2. View SQL JOIN parsing ─────────────────────────────────────────────


def test_view_sql_single_join() -> None:
    """Simple JOIN SQL → one InferredRelationship with correct fields.

    Requirements: 7.2
    """
    view_defs = {
        "my_view": (
            "SELECT * FROM orders JOIN customers "
            "ON orders.customer_id = customers.customer_id"
        ),
    }

    result = RelationshipInferrer().infer([], view_definitions=view_defs)

    view_rels = [r for r in result.relationships if r.source == "view_definition"]
    assert len(view_rels) == 1
    rel = view_rels[0]
    assert rel.source_table == "orders"
    assert rel.target_table == "customers"
    assert rel.join_column == "customer_id"
    assert rel.confidence == ConfidenceLevel.MEDIUM


def test_view_sql_multiple_joins() -> None:
    """SQL with multiple JOINs → multiple relationships extracted.

    Requirements: 7.2
    """
    view_defs = {
        "complex_view": (
            "SELECT * FROM orders "
            "JOIN customers ON orders.customer_id = customers.customer_id "
            "JOIN products ON orders.product_id = products.product_id"
        ),
    }

    result = RelationshipInferrer().infer([], view_definitions=view_defs)

    view_rels = [r for r in result.relationships if r.source == "view_definition"]
    assert len(view_rels) == 2

    join_cols = {r.join_column for r in view_rels}
    assert "customer_id" in join_cols
    assert "product_id" in join_cols


def test_view_sql_no_on_clause_fallback() -> None:
    """JOIN without ON clause → fallback relationship with 'unknown' join column.

    The JOIN_PATTERN regex requires whitespace after the table name, so we
    add a trailing space to ensure the pattern matches.

    Requirements: 7.2
    """
    view_defs = {
        "simple_view": "SELECT * FROM orders JOIN customers WHERE 1=1",
    }

    result = RelationshipInferrer().infer([], view_definitions=view_defs)

    view_rels = [r for r in result.relationships if r.source == "view_definition"]
    assert len(view_rels) >= 1
    assert view_rels[0].join_column == "unknown"


# ── 3. Clustering key → Iceberg sort-order hint mapping ─────────────────


def test_clustering_keys_become_sort_order_hints() -> None:
    """Tables with clustering_fields → those appear in sort_order_hints (R7; not SORTKEY per R15.5).

    Requirements: 7.3, 15.5
    """
    tables = [
        _make_table(
            table_id="orders",
            dataset_id="sales",
            clustering_fields=["order_date", "region"],
        ),
        _make_table(
            table_id="events",
            dataset_id="analytics",
            clustering_fields=["event_time"],
        ),
    ]

    result = RelationshipInferrer().infer(tables)

    assert "sales.orders" in result.sort_order_hints
    assert result.sort_order_hints["sales.orders"] == ["order_date", "region"]
    assert "analytics.events" in result.sort_order_hints
    assert result.sort_order_hints["analytics.events"] == ["event_time"]


def test_no_clustering_means_no_sort_order_hints() -> None:
    """Table without clustering_fields → not in sort_order_hints.

    Requirements: 7.3
    """
    tables = [
        _make_table(table_id="plain", dataset_id="ds", clustering_fields=None),
    ]

    result = RelationshipInferrer().infer(tables)

    assert "ds.plain" not in result.sort_order_hints


# ── 4. Query log integration ────────────────────────────────────────────


def test_query_log_produces_high_confidence_relationships() -> None:
    """QueryAnalysis with join_patterns → HIGH confidence relationships.

    Requirements: 7.1, 7.2
    """
    qa = QueryAnalysis(
        table_query_counts={"orders": 50, "customers": 30},
        join_patterns={
            "orders": [
                JoinPattern(
                    left_table="orders",
                    right_table="customers",
                    join_column="customer_id",
                    frequency=50,
                ),
            ],
        },
        where_columns={},
        hub_tables=[],
        anonymized=True,
    )

    result = RelationshipInferrer().infer([], query_analysis=qa)

    log_rels = [r for r in result.relationships if r.source == "query_logs"]
    assert len(log_rels) == 1
    assert log_rels[0].confidence == ConfidenceLevel.HIGH
    assert log_rels[0].source_table == "orders"
    assert log_rels[0].target_table == "customers"
    assert log_rels[0].join_column == "customer_id"
    assert result.confidence == ConfidenceLevel.HIGH


# ── 5. Empty input ──────────────────────────────────────────────────────


def test_empty_tables_returns_empty_results() -> None:
    """Empty tables list → empty relationships, join keys, and candidates.

    Requirements: 7.1
    """
    result = RelationshipInferrer().infer([])

    assert result.relationships == []
    assert result.likely_join_keys == []
    assert result.sort_order_hints == {}
    assert result.confidence == ConfidenceLevel.LOW


# ── 6. Confidence level determination ───────────────────────────────────


def test_confidence_medium_with_view_definitions() -> None:
    """View definitions present → MEDIUM confidence.

    Requirements: 7.1
    """
    view_defs = {
        "v": "SELECT * FROM a JOIN b ON a.id = b.id",
    }

    result = RelationshipInferrer().infer([], view_definitions=view_defs)

    assert result.confidence == ConfidenceLevel.MEDIUM


def test_confidence_medium_with_naming_heuristics() -> None:
    """Naming heuristics produce join keys → MEDIUM confidence.

    Requirements: 7.1
    """
    tables = [
        _make_table(
            table_id=f"t{i}",
            dataset_id="ds",
            columns=[
                ColumnSchema(name="user_id", field_type="INT64", mode="NULLABLE", fields=[]),
            ],
        )
        for i in range(5)
    ]

    result = RelationshipInferrer().infer(tables)

    assert result.confidence == ConfidenceLevel.MEDIUM


def test_confidence_low_schema_only() -> None:
    """No query logs, no views, no naming matches → LOW confidence.

    Requirements: 7.1
    """
    tables = [
        _make_table(
            table_id="lonely",
            dataset_id="ds",
            columns=[
                ColumnSchema(name="value", field_type="STRING", mode="NULLABLE", fields=[]),
            ],
        ),
    ]

    result = RelationshipInferrer().infer(tables)

    assert result.confidence == ConfidenceLevel.LOW
