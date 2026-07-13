"""Unit tests for scoring/complexity.py — Query Complexity scorer (R11)."""
from __future__ import annotations

from datetime import datetime, timezone

from bq_assess.models import (
    ComplexityCategory,
    ConfidenceLevel,
    ConfidenceSource,
    DetectedConstruct,
    EntityMetadata,
    EntityPopulation,
    EntityType,
)
from bq_assess.scoring.complexity import ComplexityScorer


def _entity(entity_type=EntityType.VIEW, view_query="SELECT 1"):
    return EntityMetadata(
        entity_id="v1",
        dataset_id="ds",
        full_name="ds.v1",
        entity_type=entity_type,
        population=EntityPopulation.REBUILT if entity_type != EntityType.TABLE else EntityPopulation.TABLE,
        num_rows=0,
        num_bytes=0,
        columns=[],
        time_partitioning=None,
        range_partitioning=None,
        clustering_fields=None,
        view_query=view_query if entity_type == EntityType.VIEW else None,
        mview_query=None,
        routine=None,
        depends_on=[],
        last_modified=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _construct(cls: str) -> DetectedConstruct:
    return DetectedConstruct(construct_class=cls, snippet="...", description="test")


class TestComplexityScorer:
    def test_no_constructs_no_surface_portable_low(self):
        scorer = ComplexityScorer()
        e = _entity(entity_type=EntityType.TABLE, view_query=None)
        e.view_query = None
        result = scorer.score(e, constructs=[], has_logs=False)
        assert result.category == ComplexityCategory.PORTABLE
        assert result.confidence == ConfidenceLevel.LOW

    def test_no_constructs_with_surface_portable_medium(self):
        scorer = ComplexityScorer()
        result = scorer.score(_entity(), constructs=[], has_logs=False)
        assert result.category == ComplexityCategory.PORTABLE
        assert result.confidence == ConfidenceLevel.MEDIUM

    def test_js_udf_is_rewrite(self):
        scorer = ComplexityScorer()
        result = scorer.score(_entity(), constructs=[_construct("JS_UDF")])
        assert result.category == ComplexityCategory.REWRITE
        assert result.score >= 4

    def test_unnest_is_adapt(self):
        scorer = ComplexityScorer()
        result = scorer.score(_entity(), constructs=[_construct("UNNEST")])
        assert result.category == ComplexityCategory.ADAPT
        assert "UNNEST" in result.flags

    def test_array_fn_is_adapt(self):
        scorer = ComplexityScorer()
        result = scorer.score(_entity(), constructs=[_construct("ARRAY_FN")])
        assert result.category == ComplexityCategory.ADAPT

    def test_struct_nav_one_point(self):
        scorer = ComplexityScorer()
        result = scorer.score(_entity(), constructs=[_construct("STRUCT_NAV")])
        assert result.score == 1
        assert result.category == ComplexityCategory.ADAPT

    def test_function_drift_one_per(self):
        scorer = ComplexityScorer()
        constructs = [_construct("FUNCTION_DRIFT"), _construct("FUNCTION_DRIFT")]
        result = scorer.score(_entity(), constructs=constructs)
        assert result.score == 2

    def test_combined_high_score_is_rewrite(self):
        scorer = ComplexityScorer()
        constructs = [_construct("UNNEST"), _construct("ARRAY_FN"), _construct("STRUCT_NAV")]
        result = scorer.score(_entity(), constructs=constructs)
        # 2 + 2 + 1 = 5 → REWRITE
        assert result.category == ComplexityCategory.REWRITE

    def test_has_logs_gives_high_confidence(self):
        scorer = ComplexityScorer()
        result = scorer.score(_entity(), constructs=[], has_logs=True)
        assert result.confidence == ConfidenceLevel.HIGH
        assert result.confidence_source == ConfidenceSource.QUERY_LOGS

    def test_constructs_included_in_result(self):
        scorer = ComplexityScorer()
        c = [_construct("UNNEST")]
        result = scorer.score(_entity(), constructs=c)
        assert result.constructs == c
