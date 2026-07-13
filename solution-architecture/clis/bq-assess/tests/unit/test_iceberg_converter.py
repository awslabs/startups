"""Unit tests for IcebergConverter and DMLGenerator (task 2.5).

Covers: each type-table row, mixed-type table, nested struct/array, each lossy type,
each partition kind, small/large/huge DML, MERGE presence.
Requirements: R6.1, R6.2, R7.1, R7.3, R7.4, R8.1, R12.1, R12.2
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bq_assess import models as m
from bq_assess.targets.iceberg.converter import (
    IcebergConverter,
)
from bq_assess.targets.iceberg.dml import (
    DMLGenerator,
)


converter = IcebergConverter()
dml_gen = DMLGenerator()

NOW = datetime.now(tz=timezone.utc)


def _make_table(
    columns, *, time_part=None, range_part=None, clustering=None,
    num_bytes=1000, full_name="ds.tbl",
) -> m.EntityMetadata:
    return m.EntityMetadata(
        entity_id="tbl", dataset_id="ds", full_name=full_name,
        entity_type=m.EntityType.TABLE, population=m.EntityPopulation.TABLE,
        num_rows=100, num_bytes=num_bytes, columns=columns,
        time_partitioning=time_part, range_partitioning=range_part,
        clustering_fields=clustering, view_query=None, mview_query=None,
        routine=None, depends_on=[], last_modified=NOW,
    )


def _col(name, field_type, mode="NULLABLE", fields=None):
    return m.ColumnSchema(name=name, field_type=field_type, mode=mode, fields=fields or [])


# =============================================================================
# Type mapping — each row in the type table (R6.1)
# =============================================================================

class TestCleanTypeMappings:
    """Each clean BQ type maps to the correct Iceberg type."""

    @pytest.mark.parametrize("bq_type,expected_iceberg", [
        ("STRING", "string"),
        ("INT64", "long"),
        ("INTEGER", "long"),
        ("FLOAT64", "double"),
        ("FLOAT", "double"),
        ("BOOL", "boolean"),
        ("BOOLEAN", "boolean"),
        ("BYTES", "binary"),
        ("DATE", "date"),
        ("TIMESTAMP", "timestamptz"),
        ("DATETIME", "timestamp"),
        ("NUMERIC", "decimal(38,9)"),
    ])
    def test_clean_scalar_type(self, bq_type, expected_iceberg):
        entity = _make_table([_col("c", bq_type)])
        result = converter.convert(entity)
        assert result.success
        assert expected_iceberg in result.ddl
        assert result.lossy_casts == []

    def test_mixed_type_table(self):
        """Table with multiple clean types produces DDL with all columns."""
        cols = [
            _col("id", "INT64", "REQUIRED"),
            _col("name", "STRING"),
            _col("amount", "NUMERIC"),
            _col("created", "TIMESTAMP"),
            _col("active", "BOOL"),
        ]
        entity = _make_table(cols)
        result = converter.convert(entity)
        assert result.success
        assert "long NOT NULL" in result.ddl
        assert "string" in result.ddl
        assert "decimal(38,9)" in result.ddl
        assert "timestamptz" in result.ddl
        assert "boolean" in result.ddl


# =============================================================================
# Nested types — struct / array / struct-in-array (R6.2)
# =============================================================================

class TestNestedTypes:

    def test_struct_becomes_iceberg_struct(self):
        inner = [_col("x", "STRING"), _col("y", "INT64")]
        cols = [_col("data", "STRUCT", fields=inner)]
        entity = _make_table(cols)
        result = converter.convert(entity)
        assert "struct<" in result.ddl
        assert "x: string" in result.ddl
        assert "y: long" in result.ddl

    def test_record_treated_as_struct(self):
        inner = [_col("a", "FLOAT64")]
        cols = [_col("rec", "RECORD", fields=inner)]
        entity = _make_table(cols)
        result = converter.convert(entity)
        assert "struct<" in result.ddl
        assert "a: double" in result.ddl

    def test_repeated_scalar_becomes_list(self):
        cols = [_col("tags", "STRING", mode="REPEATED")]
        entity = _make_table(cols)
        result = converter.convert(entity)
        assert "list<string>" in result.ddl

    def test_repeated_struct_becomes_list_struct(self):
        inner = [_col("item_id", "INT64"), _col("qty", "INT64")]
        cols = [_col("items", "STRUCT", mode="REPEATED", fields=inner)]
        entity = _make_table(cols)
        result = converter.convert(entity)
        assert "list<struct<" in result.ddl
        assert "item_id: long" in result.ddl

    def test_deeply_nested_struct(self):
        """Two levels of nesting preserved."""
        inner2 = [_col("zip", "STRING")]
        inner1 = [_col("city", "STRING"), _col("geo", "STRUCT", fields=inner2)]
        cols = [_col("address", "STRUCT", fields=inner1)]
        entity = _make_table(cols)
        result = converter.convert(entity)
        assert "struct<city: string, geo: struct<zip: string>>" in result.ddl

    def test_required_nested_field_gets_not_null(self):
        """REQUIRED sub-field inside a STRUCT renders NOT NULL (R6.4)."""
        inner = [_col("x", "STRING", mode="REQUIRED"), _col("y", "INT64")]
        cols = [_col("data", "STRUCT", fields=inner)]
        entity = _make_table(cols)
        result = converter.convert(entity)
        # Required sub-field carries NOT NULL; nullable sibling does not
        assert "x: string NOT NULL" in result.ddl
        assert "y: long," in result.ddl or "y: long>" in result.ddl
        assert "y: long NOT NULL" not in result.ddl

    def test_required_field_in_repeated_struct_gets_not_null(self):
        """REQUIRED sub-field inside ARRAY<STRUCT> renders NOT NULL (R6.4)."""
        inner = [_col("item_id", "INT64", mode="REQUIRED"), _col("note", "STRING")]
        cols = [_col("items", "STRUCT", mode="REPEATED", fields=inner)]
        entity = _make_table(cols)
        result = converter.convert(entity)
        assert "list<struct<" in result.ddl
        assert "item_id: long NOT NULL" in result.ddl


# =============================================================================
# Lossy types (R8.1)
# =============================================================================

class TestLossyTypes:

    @pytest.mark.parametrize("bq_type", ["GEOGRAPHY", "INTERVAL", "TIME", "JSON", "BIGNUMERIC"])
    def test_lossy_type_produces_warning(self, bq_type):
        cols = [_col("lossy_col", bq_type)]
        entity = _make_table(cols)
        result = converter.convert(entity)
        assert result.success
        assert len(result.lossy_casts) == 1
        lc = result.lossy_casts[0]
        assert lc.column == "lossy_col"
        assert lc.source_type == bq_type
        assert lc.iceberg_type != ""
        assert lc.loss_description != ""

    def test_unknown_type_fallback_to_string(self):
        cols = [_col("mystery", "FOOBAR")]
        entity = _make_table(cols)
        result = converter.convert(entity)
        assert result.success
        assert len(result.lossy_casts) == 1
        assert result.lossy_casts[0].iceberg_type == "string"
        assert "FOOBAR" in result.lossy_casts[0].loss_description

    def test_multiple_lossy_columns(self):
        cols = [_col("geo", "GEOGRAPHY"), _col("interval", "INTERVAL"), _col("id", "INT64")]
        entity = _make_table(cols)
        result = converter.convert(entity)
        assert len(result.lossy_casts) == 2
        lossy_names = {lc.column for lc in result.lossy_casts}
        assert lossy_names == {"geo", "interval"}


# =============================================================================
# Partition mapping — each kind (R7.1, R7.3, R7.4)
# =============================================================================

class TestPartitionMapping:

    @pytest.mark.parametrize("part_type,expected_transform", [
        ("DAY", "day(event_ts)"),
        ("HOUR", "hour(event_ts)"),
        ("MONTH", "month(event_ts)"),
        ("YEAR", "year(event_ts)"),
    ])
    def test_explicit_time_partition_clean(self, part_type, expected_transform):
        tp = m.TimePartitionConfig(type=part_type, field="event_ts")
        cols = [_col("event_ts", "TIMESTAMP")]
        entity = _make_table(cols, time_part=tp)
        result = converter.convert(entity)
        pm = result.partition_mapping
        assert pm is not None
        assert pm.auto_derived is True
        assert expected_transform in pm.iceberg_transforms
        assert pm.decision_flags == []

    def test_ingestion_time_partition_flagged(self):
        tp = m.TimePartitionConfig(type="DAY", field=None)
        cols = [_col("data", "STRING")]
        entity = _make_table(cols, time_part=tp)
        result = converter.convert(entity)
        pm = result.partition_mapping
        assert pm is not None
        assert pm.auto_derived is False
        assert len(pm.decision_flags) > 0

    def test_range_partition_flagged(self):
        rp = m.RangePartitionConfig(field="user_id", start=0, end=10000, interval=100)
        cols = [_col("user_id", "INT64")]
        entity = _make_table(cols, range_part=rp)
        result = converter.convert(entity)
        pm = result.partition_mapping
        assert pm is not None
        assert pm.auto_derived is False
        assert any("range" in f.lower() for f in pm.decision_flags)

    def test_range_partition_ddl_is_valid(self):
        """Flagged range partition emits valid DDL — no inline comment in PARTITION BY (R7.4)."""
        rp = m.RangePartitionConfig(field="user_id", start=0, end=10000, interval=100)
        cols = [_col("user_id", "INT64")]
        entity = _make_table(cols, range_part=rp)
        result = converter.convert(entity)
        # The review caveat must NOT leak into the DDL as an inline comment
        assert "-- REVIEW" not in result.ddl
        assert "bucket(16, user_id)" in result.ddl
        # PARTITION BY clause contains only the transform, comment closes the paren cleanly
        assert "PARTITION BY (bucket(16, user_id))" in result.ddl
        # The review caveat lives in decision_flags instead
        assert any("review" in f.lower() for f in result.partition_mapping.decision_flags)

    def test_ingestion_time_partition_ddl_is_valid(self):
        """Flagged ingestion-time partition emits valid DDL — no inline comment (R7.3)."""
        tp = m.TimePartitionConfig(type="DAY", field=None)
        cols = [_col("data", "STRING")]
        entity = _make_table(cols, time_part=tp)
        result = converter.convert(entity)
        assert "-- REVIEW" not in result.ddl
        assert "PARTITION BY (day(_ingestion_time))" in result.ddl
        assert any("review" in f.lower() for f in result.partition_mapping.decision_flags)

    def test_clustering_becomes_sort_order(self):
        cols = [_col("a", "STRING"), _col("b", "STRING"), _col("c", "STRING")]
        entity = _make_table(cols, clustering=["a", "b"])
        result = converter.convert(entity)
        pm = result.partition_mapping
        assert pm is not None
        assert pm.sort_order == ["a", "b"]
        assert pm.auto_derived is True

    def test_no_partition_or_clustering_returns_none(self):
        cols = [_col("id", "INT64")]
        entity = _make_table(cols)
        result = converter.convert(entity)
        assert result.partition_mapping is None


# =============================================================================
# DML Generator — volume tiers (R12.1)
# =============================================================================

class TestDMLGenerator:

    def test_small_table_uses_insert(self):
        cols = [_col("id", "INT64")]
        entity = _make_table(cols, num_bytes=500 * 1024**2)  # 500 MB
        effort = m.EffortResult(
            category=m.EffortCategory.AUTO, score=0,
            flags=[], reasoning="", confidence=m.ConfidenceLevel.MEDIUM,
        )
        dml = dml_gen.generate(entity, effort)
        assert dml is not None
        assert "INSERT INTO" in dml
        assert "COPY" not in dml

    def test_large_table_uses_copy(self):
        cols = [_col("id", "INT64")]
        entity = _make_table(cols, num_bytes=50 * 1024**3)  # 50 GB
        effort = m.EffortResult(
            category=m.EffortCategory.ASSISTED, score=1,
            flags=[], reasoning="", confidence=m.ConfidenceLevel.MEDIUM,
        )
        dml = dml_gen.generate(entity, effort)
        assert dml is not None
        assert "COPY" in dml
        assert "PARQUET" in dml

    def test_huge_table_uses_partition_copy(self):
        cols = [_col("id", "INT64"), _col("event_date", "DATE")]
        tp = m.TimePartitionConfig(type="DAY", field="event_date")
        entity = _make_table(cols, num_bytes=500 * 1024**3, time_part=tp)  # 500 GB
        effort = m.EffortResult(
            category=m.EffortCategory.MANUAL, score=3,
            flags=[], reasoning="", confidence=m.ConfidenceLevel.MEDIUM,
        )
        dml = dml_gen.generate(entity, effort)
        assert dml is not None
        assert "COPY" in dml
        assert "partition" in dml.lower()

    def test_rebuilt_entity_returns_none(self):
        entity = m.EntityMetadata(
            entity_id="v", dataset_id="ds", full_name="ds.v",
            entity_type=m.EntityType.VIEW, population=m.EntityPopulation.REBUILT,
            num_rows=0, num_bytes=0,
            columns=[_col("x", "STRING")],
            time_partitioning=None, range_partitioning=None,
            clustering_fields=None, view_query="SELECT 1",
            mview_query=None, routine=None, depends_on=[],
            last_modified=NOW,
        )
        effort = m.EffortResult(
            category=m.EffortCategory.AUTO, score=0,
            flags=[], reasoning="", confidence=m.ConfidenceLevel.MEDIUM,
        )
        dml = dml_gen.generate(entity, effort)
        assert dml is None

    def test_merge_present_when_sync_signal(self):
        """Table with time partitioning gets a MERGE statement (R12.2)."""
        cols = [_col("id", "INT64", "REQUIRED"), _col("value", "STRING")]
        tp = m.TimePartitionConfig(type="DAY", field="id")
        entity = _make_table(cols, time_part=tp)
        effort = m.EffortResult(
            category=m.EffortCategory.ASSISTED, score=1,
            flags=[], reasoning="", confidence=m.ConfidenceLevel.MEDIUM,
        )
        dml = dml_gen.generate(entity, effort)
        assert dml is not None
        assert "MERGE INTO" in dml
        assert "WHEN MATCHED" in dml
        assert "WHEN NOT MATCHED" in dml

    def test_no_merge_without_sync_signal(self):
        """Table with no partition and no timestamp columns → no MERGE."""
        cols = [_col("x", "STRING"), _col("y", "INT64")]
        entity = _make_table(cols)
        effort = m.EffortResult(
            category=m.EffortCategory.AUTO, score=0,
            flags=[], reasoning="", confidence=m.ConfidenceLevel.MEDIUM,
        )
        dml = dml_gen.generate(entity, effort)
        assert dml is not None
        assert "MERGE" not in dml

    def test_non_clean_partition_caveat_in_dml(self):
        """Flagged partition → caveat appears in DML output (R12.4)."""
        cols = [_col("user_id", "INT64")]
        rp = m.RangePartitionConfig(field="user_id", start=0, end=10000, interval=100)
        entity = _make_table(cols, range_part=rp)
        conversion = converter.convert(entity)
        effort = m.EffortResult(
            category=m.EffortCategory.ASSISTED, score=1,
            flags=["partition_decision_required"], reasoning="",
            confidence=m.ConfidenceLevel.MEDIUM,
        )
        dml = dml_gen.generate(entity, effort, conversion)
        assert dml is not None
        assert "REVIEW REQUIRED" in dml
        assert "range" in dml.lower()
