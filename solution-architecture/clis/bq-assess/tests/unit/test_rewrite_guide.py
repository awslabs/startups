"""Unit tests for engine/redshift/rewrite.py — Query-Rewrite Guidance (R13)."""
from __future__ import annotations

from datetime import datetime, timezone

from bq_assess.models import (
    DetectedConstruct,
    EntityMetadata,
    EntityPopulation,
    EntityType,
)
from bq_assess.engine.redshift.rewrite import RewriteGuide


def _entity():
    return EntityMetadata(
        entity_id="v1", dataset_id="ds", full_name="ds.v1",
        entity_type=EntityType.VIEW, population=EntityPopulation.REBUILT,
        num_rows=0, num_bytes=0, columns=[],
        time_partitioning=None, range_partitioning=None, clustering_fields=None,
        view_query="SELECT UNNEST(arr) FROM t", mview_query=None, routine=None,
        depends_on=[], last_modified=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _construct(cls: str) -> DetectedConstruct:
    return DetectedConstruct(construct_class=cls, snippet="...", description="desc")


class TestRewriteGuide:
    def test_no_constructs_empty_list(self):
        guide = RewriteGuide()
        assert guide.guide(_entity(), []) == []

    def test_one_construct_one_guidance(self):
        guide = RewriteGuide()
        result = guide.guide(_entity(), [_construct("UNNEST")])
        assert len(result) == 1
        assert "UNNEST" in result[0]

    def test_js_udf_mentions_rewrite(self):
        guide = RewriteGuide()
        result = guide.guide(_entity(), [_construct("JS_UDF")])
        assert any("Python" in g or "Lambda" in g for g in result)

    def test_multiple_constructs_multiple_guidance(self):
        guide = RewriteGuide()
        result = guide.guide(_entity(), [_construct("UNNEST"), _construct("FUNCTION_DRIFT")])
        assert len(result) == 2
