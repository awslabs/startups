"""Property-based tests for the Iceberg Converter (P6, P9, P10, P11, P12).

Feature: bq-assess-lakehouse
Task: 2.3 TDD properties — conversion
Requirements: R4.4, R6.1, R6.2, R6.4, R6.6, R7.1-R7.5, R8.1-R8.4, R12.5
"""

from __future__ import annotations

from datetime import datetime, timezone

import hypothesis.strategies as st
from hypothesis import given, settings

from bq_assess import models as m
from bq_assess.targets.iceberg.converter import (
    CLEAN_TYPE_MAP,
    IcebergConverter,
)
from tests.conftest import entity_metadata

converter = IcebergConverter()

# ---- Helpers ----

CLEAN_SCALAR_TYPES = list(CLEAN_TYPE_MAP.keys())

LOSSY_TYPES = ["GEOGRAPHY", "INTERVAL", "TIME", "JSON", "BIGNUMERIC"]

_identifier = st.from_regex(r"[a-z][a-z0-9_]{0,9}", fullmatch=True)


@st.composite
def table_entity_clean_types(draw: st.DrawFn) -> m.EntityMetadata:
    """Generate a TABLE entity whose columns use ONLY cleanly-mapped scalar types."""
    n_cols = draw(st.integers(min_value=1, max_value=6))
    columns = []
    for i in range(n_cols):
        col_type = draw(st.sampled_from(CLEAN_SCALAR_TYPES))
        mode = draw(st.sampled_from(["NULLABLE", "REQUIRED"]))
        columns.append(m.ColumnSchema(
            name=f"col_{i}", field_type=col_type, mode=mode, fields=[],
        ))

    ds = draw(_identifier)
    tbl = draw(_identifier)
    return m.EntityMetadata(
        entity_id=tbl, dataset_id=ds, full_name=f"{ds}.{tbl}",
        entity_type=m.EntityType.TABLE, population=m.EntityPopulation.TABLE,
        num_rows=100, num_bytes=1000, columns=columns,
        time_partitioning=None, range_partitioning=None,
        clustering_fields=None, view_query=None, mview_query=None,
        routine=None, depends_on=[], last_modified=datetime.now(tz=timezone.utc),
    )


@st.composite
def table_entity_with_struct(draw: st.DrawFn) -> m.EntityMetadata:
    """Generate a TABLE with at least one STRUCT or REPEATED STRUCT column."""
    inner_fields = [
        m.ColumnSchema(name="x", field_type="STRING", mode="NULLABLE", fields=[]),
        m.ColumnSchema(name="y", field_type="INT64", mode="NULLABLE", fields=[]),
    ]
    struct_col = m.ColumnSchema(
        name="nested", field_type="STRUCT", mode="NULLABLE", fields=inner_fields,
    )
    array_struct_col = m.ColumnSchema(
        name="items", field_type="STRUCT", mode="REPEATED", fields=inner_fields,
    )
    flat_col = m.ColumnSchema(name="id", field_type="INT64", mode="REQUIRED", fields=[])

    columns = [flat_col, struct_col, array_struct_col]
    ds = draw(_identifier)
    tbl = draw(_identifier)
    return m.EntityMetadata(
        entity_id=tbl, dataset_id=ds, full_name=f"{ds}.{tbl}",
        entity_type=m.EntityType.TABLE, population=m.EntityPopulation.TABLE,
        num_rows=50, num_bytes=500, columns=columns,
        time_partitioning=None, range_partitioning=None,
        clustering_fields=None, view_query=None, mview_query=None,
        routine=None, depends_on=[], last_modified=datetime.now(tz=timezone.utc),
    )


@st.composite
def table_entity_with_lossy_col(draw: st.DrawFn) -> m.EntityMetadata:
    """Generate a TABLE with at least one lossy-type column."""
    lossy_type = draw(st.sampled_from(LOSSY_TYPES))
    lossy_col = m.ColumnSchema(
        name="lossy_field", field_type=lossy_type, mode="NULLABLE", fields=[],
    )
    clean_col = m.ColumnSchema(name="id", field_type="INT64", mode="REQUIRED", fields=[])

    ds = draw(_identifier)
    tbl = draw(_identifier)
    return m.EntityMetadata(
        entity_id=tbl, dataset_id=ds, full_name=f"{ds}.{tbl}",
        entity_type=m.EntityType.TABLE, population=m.EntityPopulation.TABLE,
        num_rows=10, num_bytes=100, columns=[clean_col, lossy_col],
        time_partitioning=None, range_partitioning=None,
        clustering_fields=None, view_query=None, mview_query=None,
        routine=None, depends_on=[], last_modified=datetime.now(tz=timezone.utc),
    )


# =============================================================================
# Property 6: No CREATE TABLE for rebuilt entities (R4.4, R12.5)
# =============================================================================


# Feature: bq-assess-lakehouse, Property 6: No CREATE TABLE for rebuilt entities
@settings(max_examples=100)
@given(entity=entity_metadata(entity_type=m.EntityType.VIEW))
def test_p6_no_ddl_for_view(entity: m.EntityMetadata):
    """REBUILT entities (VIEW) get empty DDL and no load/sync DML."""
    result = converter.convert(entity)
    assert result.ddl == ""
    assert result.lossy_casts == []
    assert result.success is True


@settings(max_examples=100)
@given(entity=entity_metadata(entity_type=m.EntityType.MATERIALIZED_VIEW))
def test_p6_no_ddl_for_mview(entity: m.EntityMetadata):
    """REBUILT entities (MATERIALIZED_VIEW) get empty DDL."""
    result = converter.convert(entity)
    assert result.ddl == ""
    assert result.success is True


@settings(max_examples=100)
@given(entity=entity_metadata(entity_type=m.EntityType.ROUTINE))
def test_p6_no_ddl_for_routine(entity: m.EntityMetadata):
    """REBUILT entities (ROUTINE) get empty DDL."""
    result = converter.convert(entity)
    assert result.ddl == ""
    assert result.success is True


# =============================================================================
# Property 9: Iceberg DDL round-trip for clean types (R6.1, R6.4, R6.6)
# =============================================================================


# Feature: bq-assess-lakehouse, Property 9: Iceberg DDL round-trip (clean types)
@settings(max_examples=100)
@given(entity=table_entity_clean_types())
def test_p9_clean_types_produce_valid_ddl(entity: m.EntityMetadata):
    """Tables with only clean types produce valid DDL with all columns present."""
    result = converter.convert(entity)
    assert result.success is True
    assert result.ddl != ""
    assert "CREATE TABLE" in result.ddl
    assert entity.full_name in result.ddl
    # Every column name appears in the DDL
    for col in entity.columns:
        assert col.name in result.ddl
    # No lossy casts for clean-only tables
    assert result.lossy_casts == []
    # Nullability: REQUIRED → NOT NULL in DDL
    for col in entity.columns:
        if col.mode == "REQUIRED":
            assert f"{col.name}" in result.ddl
            # Find the column line and check NOT NULL
            for line in result.ddl.split("\n"):
                if col.name in line:
                    assert "NOT NULL" in line
                    break


# =============================================================================
# Property 10: Native nesting preservation (R6.2)
# =============================================================================


# Feature: bq-assess-lakehouse, Property 10: Native nesting preservation
@settings(max_examples=100)
@given(entity=table_entity_with_struct())
def test_p10_nesting_preserved(entity: m.EntityMetadata):
    """STRUCT/ARRAY columns use struct/list in DDL, no flattening or JSON-stringify."""
    result = converter.convert(entity)
    assert result.success is True
    ddl = result.ddl

    # Must contain struct<> syntax (native nesting)
    assert "struct<" in ddl
    # Must contain list<struct<>> for REPEATED STRUCT
    assert "list<struct<" in ddl
    # Must NOT contain SUPER (that's the old Redshift fallback)
    assert "SUPER" not in ddl
    # Must NOT contain flattened column names like "nested_x" or "nested_y"
    assert "nested_x" not in ddl
    assert "nested_y" not in ddl


@st.composite
def table_entity_with_required_nested(draw: st.DrawFn) -> m.EntityMetadata:
    """Generate a TABLE with a STRUCT whose sub-fields have mixed REQUIRED/NULLABLE modes."""
    n_inner = draw(st.integers(min_value=1, max_value=4))
    inner_fields = []
    for i in range(n_inner):
        mode = draw(st.sampled_from(["NULLABLE", "REQUIRED"]))
        inner_fields.append(
            m.ColumnSchema(name=f"f_{i}", field_type="STRING", mode=mode, fields=[])
        )
    nesting = draw(st.sampled_from(["NULLABLE", "REPEATED"]))
    struct_col = m.ColumnSchema(
        name="nested", field_type="STRUCT", mode=nesting, fields=inner_fields,
    )
    ds = draw(_identifier)
    tbl = draw(_identifier)
    return m.EntityMetadata(
        entity_id=tbl, dataset_id=ds, full_name=f"{ds}.{tbl}",
        entity_type=m.EntityType.TABLE, population=m.EntityPopulation.TABLE,
        num_rows=10, num_bytes=100, columns=[struct_col],
        time_partitioning=None, range_partitioning=None,
        clustering_fields=None, view_query=None, mview_query=None,
        routine=None, depends_on=[], last_modified=datetime.now(tz=timezone.utc),
    )


# Feature: bq-assess-lakehouse, Property 10b: Nested-field nullability honored (R6.4)
@settings(max_examples=100)
@given(entity=table_entity_with_required_nested())
def test_p10_nested_required_fields_marked_not_null(entity: m.EntityMetadata):
    """Each REQUIRED sub-field of a STRUCT renders NOT NULL; NULLABLE ones do not (R6.4)."""
    result = converter.convert(entity)
    assert result.success is True
    ddl = result.ddl
    inner_fields = entity.columns[0].fields
    for f in inner_fields:
        if f.mode == "REQUIRED":
            assert f"{f.name}: string NOT NULL" in ddl, (
                f"REQUIRED nested field '{f.name}' missing NOT NULL in DDL: {ddl}"
            )
        else:
            assert f"{f.name}: string NOT NULL" not in ddl, (
                f"NULLABLE nested field '{f.name}' wrongly marked NOT NULL in DDL: {ddl}"
            )


# =============================================================================
# Property 11: Lossy casts are never silent (R8.1, R8.2, R8.3, R8.4)
# =============================================================================


# Feature: bq-assess-lakehouse, Property 11: Lossy casts are never silent
@settings(max_examples=100)
@given(entity=table_entity_with_lossy_col())
def test_p11_lossy_casts_never_silent(entity: m.EntityMetadata):
    """Every lossy-type column produces a LossyCast warning, never maps silently."""
    result = converter.convert(entity)
    assert result.success is True

    # Find lossy columns in the input
    lossy_col_names = [
        col.name for col in entity.columns
        if col.field_type.upper() in LOSSY_TYPES
    ]
    assert len(lossy_col_names) > 0

    # Every lossy column must have a corresponding LossyCast entry
    lossy_cast_cols = [lc.column for lc in result.lossy_casts]
    for col_name in lossy_col_names:
        assert col_name in lossy_cast_cols, (
            f"Column '{col_name}' is lossy but has no LossyCast warning"
        )

    # Each LossyCast has meaningful fields
    for lc in result.lossy_casts:
        assert lc.source_type != ""
        assert lc.iceberg_type != ""
        assert lc.loss_description != ""


@settings(max_examples=50)
@given(
    unknown_type=st.from_regex(r"[A-Z]{4,10}", fullmatch=True).filter(
        lambda t: t not in CLEAN_TYPE_MAP and t not in LOSSY_TYPES
        and t not in ("STRUCT", "RECORD", "ARRAY")
    )
)
def test_p11_unknown_type_is_lossy(unknown_type: str):
    """Unknown types get a string fallback AND a lossy_cast warning (R8.4)."""
    entity = m.EntityMetadata(
        entity_id="t", dataset_id="d", full_name="d.t",
        entity_type=m.EntityType.TABLE, population=m.EntityPopulation.TABLE,
        num_rows=1, num_bytes=1,
        columns=[m.ColumnSchema(name="unk", field_type=unknown_type, mode="NULLABLE", fields=[])],
        time_partitioning=None, range_partitioning=None,
        clustering_fields=None, view_query=None, mview_query=None,
        routine=None, depends_on=[], last_modified=datetime.now(tz=timezone.utc),
    )
    result = converter.convert(entity)
    assert result.success is True
    assert len(result.lossy_casts) == 1
    assert result.lossy_casts[0].column == "unk"
    assert result.lossy_casts[0].iceberg_type == "string"
    assert unknown_type in result.lossy_casts[0].loss_description


# =============================================================================
# Property 12: Partition mapping clean-vs-flagged (R7.1-R7.5, R9.2)
# =============================================================================


# Feature: bq-assess-lakehouse, Property 12: Partition mapping clean-vs-flagged
@settings(max_examples=100)
@given(
    part_type=st.sampled_from(["DAY", "HOUR", "MONTH", "YEAR"]),
    field_name=_identifier,
)
def test_p12_explicit_time_partition_is_clean(part_type: str, field_name: str):
    """Explicit-field time partition → auto_derived=True, no decision flags."""
    entity = m.EntityMetadata(
        entity_id="t", dataset_id="d", full_name="d.t",
        entity_type=m.EntityType.TABLE, population=m.EntityPopulation.TABLE,
        num_rows=100, num_bytes=1000,
        columns=[m.ColumnSchema(name=field_name, field_type="TIMESTAMP", mode="NULLABLE", fields=[])],
        time_partitioning=m.TimePartitionConfig(type=part_type, field=field_name),
        range_partitioning=None, clustering_fields=None,
        view_query=None, mview_query=None, routine=None,
        depends_on=[], last_modified=datetime.now(tz=timezone.utc),
    )
    result = converter.convert(entity)
    assert result.partition_mapping is not None
    assert result.partition_mapping.auto_derived is True
    assert result.partition_mapping.decision_flags == []
    # Transform uses the correct function
    expected_transform = f"{part_type.lower()}({field_name})"
    assert expected_transform in result.partition_mapping.iceberg_transforms


@settings(max_examples=50)
@given(data=st.data())
def test_p12_ingestion_time_partition_is_flagged(data):
    """Ingestion-time partition (field=None) → auto_derived=False + decision flag."""
    entity = m.EntityMetadata(
        entity_id="t", dataset_id="d", full_name="d.t",
        entity_type=m.EntityType.TABLE, population=m.EntityPopulation.TABLE,
        num_rows=100, num_bytes=1000,
        columns=[m.ColumnSchema(name="ts", field_type="TIMESTAMP", mode="NULLABLE", fields=[])],
        time_partitioning=m.TimePartitionConfig(type="DAY", field=None),
        range_partitioning=None, clustering_fields=None,
        view_query=None, mview_query=None, routine=None,
        depends_on=[], last_modified=datetime.now(tz=timezone.utc),
    )
    result = converter.convert(entity)
    assert result.partition_mapping is not None
    assert result.partition_mapping.auto_derived is False
    assert len(result.partition_mapping.decision_flags) > 0
    assert any("ingestion" in f.lower() for f in result.partition_mapping.decision_flags)


@settings(max_examples=50)
@given(data=st.data())
def test_p12_range_partition_is_flagged(data):
    """Range partition → auto_derived=False + decision flag."""
    entity = m.EntityMetadata(
        entity_id="t", dataset_id="d", full_name="d.t",
        entity_type=m.EntityType.TABLE, population=m.EntityPopulation.TABLE,
        num_rows=100, num_bytes=1000,
        columns=[m.ColumnSchema(name="val", field_type="INT64", mode="NULLABLE", fields=[])],
        time_partitioning=None,
        range_partitioning=m.RangePartitionConfig(field="val", start=0, end=1000, interval=10),
        clustering_fields=None,
        view_query=None, mview_query=None, routine=None,
        depends_on=[], last_modified=datetime.now(tz=timezone.utc),
    )
    result = converter.convert(entity)
    assert result.partition_mapping is not None
    assert result.partition_mapping.auto_derived is False
    assert len(result.partition_mapping.decision_flags) > 0
    assert any("range" in f.lower() for f in result.partition_mapping.decision_flags)


@settings(max_examples=50)
@given(fields=st.lists(_identifier, min_size=1, max_size=4, unique=True))
def test_p12_clustering_becomes_sort_order(fields: list[str]):
    """Clustering fields → sort order, auto_derived stays True (clean, R7.2)."""
    columns = [
        m.ColumnSchema(name=f, field_type="STRING", mode="NULLABLE", fields=[])
        for f in fields
    ]
    entity = m.EntityMetadata(
        entity_id="t", dataset_id="d", full_name="d.t",
        entity_type=m.EntityType.TABLE, population=m.EntityPopulation.TABLE,
        num_rows=100, num_bytes=1000, columns=columns,
        time_partitioning=None, range_partitioning=None,
        clustering_fields=fields,
        view_query=None, mview_query=None, routine=None,
        depends_on=[], last_modified=datetime.now(tz=timezone.utc),
    )
    result = converter.convert(entity)
    assert result.partition_mapping is not None
    assert result.partition_mapping.sort_order == fields
    assert result.partition_mapping.auto_derived is True
