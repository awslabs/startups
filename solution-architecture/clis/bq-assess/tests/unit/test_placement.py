"""Unit tests for engine/redshift/placement.py — Placement Advisor (R14)."""
from __future__ import annotations

from datetime import datetime, timezone

from bq_assess.models import (
    ConfidenceLevel,
    EntityMetadata,
    EntityPopulation,
    EntityType,
    RoutineMetadata,
)
from bq_assess.engine.redshift.placement import PlacementAdvisor


def _entity(etype=EntityType.VIEW, routine=None):
    return EntityMetadata(
        entity_id="v1", dataset_id="ds", full_name="ds.v1",
        entity_type=etype,
        population=EntityPopulation.REBUILT if etype != EntityType.TABLE else EntityPopulation.TABLE,
        num_rows=0, num_bytes=0, columns=[],
        time_partitioning=None, range_partitioning=None, clustering_fields=None,
        view_query="SELECT 1" if etype == EntityType.VIEW else None,
        mview_query="SELECT 1" if etype == EntityType.MATERIALIZED_VIEW else None,
        routine=routine, depends_on=[],
        last_modified=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class TestPlacementAdvisor:
    def test_table_returns_none(self):
        advisor = PlacementAdvisor()
        assert advisor.recommend(_entity(etype=EntityType.TABLE)) is None

    def test_udf_always_redshift(self):
        advisor = PlacementAdvisor()
        routine = RoutineMetadata(
            name="my_fn", language="SQL", body="RETURN x + 1",
            routine_type="SCALAR_FUNCTION", arguments=[],
        )
        result = advisor.recommend(_entity(etype=EntityType.ROUTINE, routine=routine))
        assert result is not None
        assert result.home == "REDSHIFT"

    def test_js_udf_flagged(self):
        advisor = PlacementAdvisor()
        routine = RoutineMetadata(
            name="js_fn", language="JAVASCRIPT", body="return x;",
            routine_type="SCALAR_FUNCTION", arguments=[],
        )
        result = advisor.recommend(_entity(etype=EntityType.ROUTINE, routine=routine))
        assert result is not None
        assert result.home == "REDSHIFT"
        assert any("javascript" in s.lower() or "js" in s.lower() for s in result.signals)

    def test_view_defaults_redshift_low_confidence(self):
        advisor = PlacementAdvisor()
        result = advisor.recommend(_entity(etype=EntityType.VIEW))
        assert result is not None
        assert result.home == "REDSHIFT"
        assert result.confidence == ConfidenceLevel.LOW

    def test_mv_iceberg_refresh_unverified(self):
        advisor = PlacementAdvisor()
        result = advisor.recommend(_entity(etype=EntityType.MATERIALIZED_VIEW), has_logs=True)
        assert result is not None
        # With logs suggesting cross-engine, could be ICEBERG_CATALOG
        # Without that signal, default is REDSHIFT
        # Either way, if home is ICEBERG_CATALOG, refresh_unverified must be True
        if result.home == "ICEBERG_CATALOG":
            assert result.refresh_unverified is True

    def test_external_returns_none(self):
        advisor = PlacementAdvisor()
        e = _entity(etype=EntityType.EXTERNAL)
        e.population = EntityPopulation.TABLE
        assert advisor.recommend(e) is None
