# Feature: bq-assess-lakehouse, Property 8: Cache round-trip
"""Property P8 — cache round-trip (issue #10 / 1.5).

*For any* list of EntityMetadata, store-then-load SHALL yield structurally-equivalent
entities — including nested columns, BOTH partitionings, view/mview SQL, and routines.
**Validates: R5.1, R5.4**

Supersedes the interim round-trip added in #9; this is the canonical, fully-asserting P8.
"""

from __future__ import annotations

import os
import tempfile

import hypothesis.strategies as st
from hypothesis import given, settings

from bq_assess.core.cache import MetadataCache
from bq_assess.models import ColumnSchema, EntityMetadata

from tests.conftest import entity_metadata


@st.composite
def unique_entity_list(draw: st.DrawFn) -> list[EntityMetadata]:
    """EntityMetadata list with unique (dataset_id, entity_id) — the cache primary key."""
    entities = draw(st.lists(entity_metadata(), min_size=0, max_size=6))
    seen: set[tuple[str, str]] = set()
    unique: list[EntityMetadata] = []
    for e in entities:
        key = (e.dataset_id, e.entity_id)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


@settings(max_examples=100)
@given(entities=unique_entity_list())
def test_p8_cache_round_trip(entities: list[EntityMetadata]) -> None:
    """Property 8: store→load yields structurally-equivalent EntityMetadata."""
    # Feature: bq-assess-lakehouse, Property 8: Cache round-trip
    db_path = os.path.join(tempfile.mkdtemp(), "p8_cache.db")
    cache = MetadataCache(db_path=db_path)
    cache.store("test-project", entities)

    loaded = cache.load("test-project")
    assert loaded is not None
    assert len(loaded) == len(entities)

    key = lambda e: (e.dataset_id, e.entity_id)  # noqa: E731
    for orig, back in zip(sorted(entities, key=key), sorted(loaded, key=key)):
        _assert_entity_equivalent(orig, back)


def _assert_entity_equivalent(orig: EntityMetadata, back: EntityMetadata) -> None:
    # Scalar identity / classification
    assert back.entity_id == orig.entity_id
    assert back.dataset_id == orig.dataset_id
    assert back.full_name == orig.full_name
    assert back.entity_type == orig.entity_type
    assert back.population == orig.population
    assert back.num_rows == orig.num_rows
    assert back.num_bytes == orig.num_bytes
    assert back.last_modified == orig.last_modified

    # Nested columns (recursive, nesting depth preserved)
    _assert_columns_equal(orig.columns, back.columns)

    # Both partitionings
    _assert_time_part_equal(orig.time_partitioning, back.time_partitioning)
    _assert_range_part_equal(orig.range_partitioning, back.range_partitioning)
    assert back.clustering_fields == orig.clustering_fields

    # SQL surface
    assert back.view_query == orig.view_query
    assert back.mview_query == orig.mview_query

    # Routine
    if orig.routine is None:
        assert back.routine is None
    else:
        assert back.routine is not None
        assert back.routine.name == orig.routine.name
        assert back.routine.language == orig.routine.language
        assert back.routine.arguments == orig.routine.arguments
        assert back.routine.body == orig.routine.body
        assert back.routine.routine_type == orig.routine.routine_type

    # Dependency links
    assert back.depends_on == orig.depends_on


def _assert_columns_equal(original: list[ColumnSchema], loaded: list[ColumnSchema]) -> None:
    assert len(loaded) == len(original)
    for orig_col, loaded_col in zip(original, loaded):
        assert loaded_col.name == orig_col.name
        assert loaded_col.field_type == orig_col.field_type
        assert loaded_col.mode == orig_col.mode
        _assert_columns_equal(orig_col.fields, loaded_col.fields)


def _assert_time_part_equal(orig, back) -> None:
    if orig is None:
        assert back is None
    else:
        assert back is not None
        assert back.type == orig.type
        assert back.field == orig.field


def _assert_range_part_equal(orig, back) -> None:
    if orig is None:
        assert back is None
    else:
        assert back is not None
        assert back.field == orig.field
        assert back.start == orig.start
        assert back.end == orig.end
        assert back.interval == orig.interval
