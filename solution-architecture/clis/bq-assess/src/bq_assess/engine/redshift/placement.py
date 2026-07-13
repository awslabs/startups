"""View/MV/UDF Placement recommendation (R14).

UDF → REDSHIFT always. View/MV → signal-based recommendation with no blanket default.
MV with Iceberg placement → refresh_unverified=True (V7 unconfirmed).
"""
from __future__ import annotations

from bq_assess.models import (
    ConfidenceLevel,
    EntityMetadata,
    EntityPopulation,
    EntityType,
    PlacementRecommendation,
)


class PlacementAdvisor:
    """Recommend home for Views/MVs/UDFs — Redshift or Iceberg catalog (R14)."""

    def recommend(
        self,
        entity: EntityMetadata,
        relationships=None,
        has_logs: bool = False,
    ) -> PlacementRecommendation | None:
        if entity.population is EntityPopulation.TABLE:
            return None

        if entity.entity_type == EntityType.ROUTINE:
            return self._recommend_routine(entity)

        return self._recommend_view_or_mv(entity, has_logs)

    def _recommend_routine(self, entity: EntityMetadata) -> PlacementRecommendation:
        signals = ["UDF/procedure — Iceberg has no function concept"]
        if entity.routine and entity.routine.language and entity.routine.language.upper() == "JAVASCRIPT":
            signals.append("JavaScript UDF — requires Python/Lambda rewrite")
        return PlacementRecommendation(
            home="REDSHIFT",
            signals=signals,
            confidence=ConfidenceLevel.HIGH,
            refresh_unverified=False,
        )

    def _recommend_view_or_mv(self, entity: EntityMetadata, has_logs: bool) -> PlacementRecommendation:
        is_mv = entity.entity_type == EntityType.MATERIALIZED_VIEW

        # Per-entity signal (R14.2 — never a blanket default). From metadata we use
        # cross-dataset breadth as a proxy for multi-engine/open-lakehouse consumption:
        # a view/MV that spans more than one dataset is a candidate for the open Iceberg
        # catalog (queryable by multiple engines); a single-dataset one is simplest kept
        # engine-local in Redshift. Query logs (when present) raise confidence.
        distinct_datasets = {
            dep.split(".")[0] for dep in entity.depends_on if "." in dep
        }
        multi_domain = len(distinct_datasets) > 1

        if multi_domain:
            home = "ICEBERG_CATALOG"
            signals = [
                f"spans {len(distinct_datasets)} datasets — open multi-engine access favors "
                "the Iceberg catalog"
            ]
        else:
            home = "REDSHIFT"
            signals = [
                "single-dataset, engine-local consumption — simplest kept in Redshift"
            ]

        confidence = ConfidenceLevel.MEDIUM if has_logs else ConfidenceLevel.LOW
        if has_logs:
            signals.append("query logs available — consumption pattern observed")

        refresh_unverified = False
        if is_mv and home == "ICEBERG_CATALOG":
            refresh_unverified = True
            signals.append("MV on Iceberg — refresh behavior unverified (V7)")

        return PlacementRecommendation(
            home=home,
            signals=signals,
            confidence=confidence,
            refresh_unverified=refresh_unverified,
        )
