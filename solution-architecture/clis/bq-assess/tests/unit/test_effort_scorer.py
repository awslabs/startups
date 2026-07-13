"""Unit tests for scoring/effort.py — Migration Effort scorer (R9)."""
from __future__ import annotations

from bq_assess.models import (
    ConversionResult,
    EffortCategory,
    EntityMetadata,
    EntityPopulation,
    EntityType,
    ConfidenceLevel,
    LossyCast,
    PartitionMapping,
)
from bq_assess.scoring.effort import EffortScorer


def _entity(num_bytes: int = 100_000, entity_type=EntityType.TABLE, columns=None):
    from datetime import datetime, timezone
    return EntityMetadata(
        entity_id="t1",
        dataset_id="ds",
        full_name="ds.t1",
        entity_type=entity_type,
        population=EntityPopulation.TABLE,
        num_rows=1000,
        num_bytes=num_bytes,
        columns=columns or [],
        time_partitioning=None,
        range_partitioning=None,
        clustering_fields=None,
        view_query=None,
        mview_query=None,
        routine=None,
        depends_on=[],
        last_modified=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _conversion(lossy_casts=None, decision_flags=None):
    pm = None
    if decision_flags:
        pm = PartitionMapping(
            iceberg_transforms=[],
            sort_order=[],
            auto_derived=False,
            decision_flags=decision_flags,
        )
    return ConversionResult(
        ddl="CREATE TABLE ds.t1 (id bigint);",
        partition_mapping=pm,
        lossy_casts=lossy_casts or [],
        warnings=[],
        success=True,
    )


class TestEffortScorer:
    def test_small_clean_table_is_auto(self):
        scorer = EffortScorer()
        result = scorer.score(_entity(num_bytes=500_000_000), _conversion())
        assert result.category == EffortCategory.AUTO
        assert result.score == 0

    def test_large_table_gets_volume_point(self):
        scorer = EffortScorer()
        # 50 GB
        result = scorer.score(_entity(num_bytes=50 * 1024**3), _conversion())
        assert result.score >= 1
        assert "data_volume_large" in result.flags

    def test_huge_table_gets_two_volume_points(self):
        scorer = EffortScorer()
        # 200 GB
        result = scorer.score(_entity(num_bytes=200 * 1024**3), _conversion())
        assert result.score >= 2
        assert "data_volume_huge" in result.flags

    def test_lossy_casts_add_points(self):
        scorer = EffortScorer()
        lossy = [
            LossyCast(column="c1", source_type="TIME", iceberg_type="STRING", loss_description="no TIME"),
            LossyCast(column="c2", source_type="JSON", iceberg_type="STRING", loss_description="no JSON"),
        ]
        result = scorer.score(_entity(), _conversion(lossy_casts=lossy))
        assert result.score >= 2
        assert "lossy_casts" in result.flags

    def test_partition_decision_adds_point(self):
        scorer = EffortScorer()
        result = scorer.score(_entity(), _conversion(decision_flags=["partition_decision_required"]))
        assert result.score >= 1
        assert "partition_decision_required" in result.flags

    def test_sort_decision_adds_point(self):
        scorer = EffortScorer()
        result = scorer.score(_entity(), _conversion(decision_flags=["sort_decision_required"]))
        assert result.score >= 1
        assert "sort_decision_required" in result.flags

    def test_sync_need_adds_point(self):
        from bq_assess.models import TimePartitionConfig
        e = _entity()
        e.time_partitioning = TimePartitionConfig(field="_PARTITIONTIME", type="DAY")
        scorer = EffortScorer()
        result = scorer.score(e, _conversion())
        assert "ongoing_sync" in result.flags

    def test_combined_factors_manual(self):
        from bq_assess.models import TimePartitionConfig
        scorer = EffortScorer()
        e = _entity(num_bytes=200 * 1024**3)
        e.time_partitioning = TimePartitionConfig(field="_PARTITIONTIME", type="DAY")
        lossy = [LossyCast(column="c", source_type="TIME", iceberg_type="STRING", loss_description="x")]
        result = scorer.score(e, _conversion(lossy_casts=lossy, decision_flags=["partition_decision_required"]))
        assert result.category == EffortCategory.MANUAL
        assert result.score >= 3

    def test_confidence_high_when_num_bytes_known(self):
        scorer = EffortScorer()
        result = scorer.score(_entity(num_bytes=0), _conversion())
        assert result.confidence == ConfidenceLevel.HIGH

    def test_confidence_low_when_num_bytes_none(self):
        scorer = EffortScorer()
        e = _entity()
        e.num_bytes = None
        result = scorer.score(e, _conversion())
        assert result.confidence == ConfidenceLevel.LOW

    def test_failed_conversion_is_manual(self):
        scorer = EffortScorer()
        failed = ConversionResult(ddl="", partition_mapping=None, lossy_casts=[], warnings=["error"], success=False)
        result = scorer.score(_entity(), failed)
        assert result.category == EffortCategory.MANUAL

    def test_sync_column_name_adds_point(self):
        from bq_assess.models import ColumnSchema
        e = _entity(columns=[ColumnSchema(name="updated_at", field_type="TIMESTAMP", mode="NULLABLE")])
        scorer = EffortScorer()
        result = scorer.score(e, _conversion())
        assert "ongoing_sync" in result.flags
