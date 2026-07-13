"""Unit tests for storage stats — physical bytes, compression ratio fallbacks."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from hypothesis import given, strategies as st

from bq_assess.core.storage_stats import resolve_physical_bytes, effective_physical_bytes
from bq_assess.engine.redshift.cost import _tiered_s3_tables_usd
from bq_assess.engine.redshift import cost_constants as k
from bq_assess.models import EntityMetadata, EntityPopulation, EntityType


def test_entity_metadata_physical_bytes_default_none():
    """physical_bytes defaults to None for backward compat."""
    e = EntityMetadata(
        entity_id="t1",
        dataset_id="ds",
        full_name="ds.t1",
        entity_type=EntityType.TABLE,
        population=EntityPopulation.TABLE,
        num_rows=100,
        num_bytes=1_000_000,
        columns=[],
        time_partitioning=None,
        range_partitioning=None,
        clustering_fields=None,
        view_query=None,
        mview_query=None,
        routine=None,
        depends_on=[],
        last_modified=datetime.now(),
    )
    assert e.physical_bytes is None


def test_entity_metadata_physical_bytes_set():
    """physical_bytes can be explicitly set."""
    e = EntityMetadata(
        entity_id="t1",
        dataset_id="ds",
        full_name="ds.t1",
        entity_type=EntityType.TABLE,
        population=EntityPopulation.TABLE,
        num_rows=100,
        num_bytes=1_000_000,
        columns=[],
        time_partitioning=None,
        range_partitioning=None,
        clustering_fields=None,
        view_query=None,
        mview_query=None,
        routine=None,
        depends_on=[],
        last_modified=datetime.now(),
        physical_bytes=750_000,
    )
    assert e.physical_bytes == 750_000


def _make_entity(full_name, num_bytes, physical_bytes=None):
    """Helper: minimal EntityMetadata-like object."""
    from bq_assess.models import EntityMetadata, EntityType, EntityPopulation
    from datetime import datetime
    return EntityMetadata(
        entity_id=full_name.split(".")[-1], dataset_id=full_name.split(".")[0],
        full_name=full_name, entity_type=EntityType.TABLE,
        population=EntityPopulation.TABLE, num_rows=100,
        num_bytes=num_bytes, columns=[], time_partitioning=None,
        range_partitioning=None, clustering_fields=None,
        view_query=None, mview_query=None, routine=None,
        depends_on=[], last_modified=datetime.now(),
        physical_bytes=physical_bytes,
    )


def test_resolve_measured_path():
    """When TABLE_STORAGE returns data, physical_map uses measured values."""
    client = MagicMock()
    # Simulate query result: two rows with current_physical_bytes
    row1 = MagicMock()
    row1.table_schema = "ds"
    row1.table_name = "t1"
    row1.current_physical_bytes = 500_000
    row2 = MagicMock()
    row2.table_schema = "ds"
    row2.table_name = "t2"
    row2.current_physical_bytes = 300_000
    client.query.return_value.result.return_value = [row1, row2]

    entities = [_make_entity("ds.t1", 1_000_000), _make_entity("ds.t2", 800_000)]
    stats = resolve_physical_bytes(client, "my-project", "us", entities)

    assert stats.basis == "measured"
    assert stats.measured_count == 2
    assert stats.assumed_count == 0
    assert stats.physical_map == {"ds.t1": 500_000, "ds.t2": 300_000}
    assert "TABLE_STORAGE" in stats.source_note
    # Verify the generated SQL has WHERE clause
    sql = client.query.call_args[0][0]
    assert "WHERE table_schema IN" in sql


def test_resolve_fallback_on_error():
    """When TABLE_STORAGE query fails, fall back to 0.75 × logical."""
    client = MagicMock()
    client.query.side_effect = Exception("Permission denied")

    entities = [_make_entity("ds.t1", 1_000_000), _make_entity("ds.t2", 800_000)]
    stats = resolve_physical_bytes(client, "my-project", "us", entities)

    assert stats.basis == "assumed"
    assert stats.measured_count == 0
    assert stats.assumed_count == 2
    assert stats.physical_map == {
        "ds.t1": round(1_000_000 * k.ASSUMED_PHYSICAL_RATIO),
        "ds.t2": round(800_000 * k.ASSUMED_PHYSICAL_RATIO),
    }
    assert str(k.ASSUMED_PHYSICAL_RATIO) in stats.source_note


def test_resolve_partial_coverage():
    """Entities missing from TABLE_STORAGE get ratio fallback."""
    client = MagicMock()
    row1 = MagicMock()
    row1.table_schema = "ds"
    row1.table_name = "t1"
    row1.current_physical_bytes = 500_000
    client.query.return_value.result.return_value = [row1]

    entities = [_make_entity("ds.t1", 1_000_000), _make_entity("ds.t2", 800_000)]
    stats = resolve_physical_bytes(client, "my-project", "us", entities)

    assert stats.basis == "mixed"
    assert stats.measured_count == 1
    assert stats.assumed_count == 1
    assert stats.physical_map["ds.t1"] == 500_000
    assert stats.physical_map["ds.t2"] == round(800_000 * k.ASSUMED_PHYSICAL_RATIO)


def test_resolve_zero_bytes_entities():
    """Views/routines with num_bytes=0 get physical_bytes=0, no ratio math."""
    client = MagicMock()
    client.query.side_effect = Exception("fail")

    entities = [_make_entity("ds.v1", 0)]
    stats = resolve_physical_bytes(client, "my-project", "us", entities)
    assert stats.physical_map["ds.v1"] == 0


def test_effective_physical_bytes():
    """effective_physical_bytes helper uses physical when set, fallback otherwise."""
    assert effective_physical_bytes(1000, None) == 750
    assert effective_physical_bytes(1000, 400) == 400
    assert effective_physical_bytes(1000, 0) == 0
    assert effective_physical_bytes(0, None) == 0


@given(logical_bytes=st.integers(min_value=0, max_value=10 * 10**12))
def test_physical_storage_cost_leq_logical(logical_bytes):
    """S3 cost on physical bytes is always ≤ cost on logical bytes (ratio ≤ 1.0)."""
    physical_bytes = round(logical_bytes * k.ASSUMED_PHYSICAL_RATIO)
    logical_gb = logical_bytes * k.GB_PER_BYTE
    physical_gb = physical_bytes * k.GB_PER_BYTE

    cost_logical = _tiered_s3_tables_usd(logical_gb)
    cost_physical = _tiered_s3_tables_usd(physical_gb)

    assert cost_physical <= cost_logical
