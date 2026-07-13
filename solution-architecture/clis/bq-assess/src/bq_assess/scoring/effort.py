"""Migration Effort scorer (R9) — Tables only.

Factors: data-volume tier (dominant), lossy-cast count, ongoing-sync need,
non-clean partition/sort mapping. Nesting and clean partitioning contribute
zero (R9.3, ADR-0002).
"""
from __future__ import annotations

from bq_assess.models import (
    ConfidenceLevel,
    ConversionResult,
    EffortCategory,
    EffortResult,
    EntityMetadata,
)

_ONE_GB = 1024**3
_LARGE_THRESHOLD = 1 * _ONE_GB
_HUGE_THRESHOLD = 100 * _ONE_GB

_SYNC_SIGNALS = {"_partitiontime", "updated_at", "modified_at", "ingestion_time"}


class EffortScorer:
    """Score migration effort for TABLE-population entities."""

    def score(self, entity: EntityMetadata, conversion: ConversionResult) -> EffortResult:
        if not conversion.success:
            return EffortResult(
                category=EffortCategory.MANUAL,
                score=99,
                flags=["conversion_failed"],
                reasoning="Iceberg DDL conversion failed — manual migration design required.",
                confidence=ConfidenceLevel.HIGH,
            )

        points = 0
        flags: list[str] = []
        reasons: list[str] = []

        # Data-volume tier (dominant factor)
        size_bytes = entity.num_bytes or 0
        if size_bytes >= _HUGE_THRESHOLD:
            points += 2
            flags.append("data_volume_huge")
            reasons.append(f"huge volume ({size_bytes / _ONE_GB:.0f} GB) — partition-wise load (+2)")
        elif size_bytes >= _LARGE_THRESHOLD:
            points += 1
            flags.append("data_volume_large")
            reasons.append(f"large volume ({size_bytes / _ONE_GB:.1f} GB) — staged COPY (+1)")

        # Lossy casts
        n_lossy = len(conversion.lossy_casts)
        if n_lossy > 0:
            points += n_lossy
            flags.append("lossy_casts")
            reasons.append(f"{n_lossy} lossy cast(s) — manual type review (+{n_lossy})")

        # Ongoing-sync need
        if self._has_sync_signal(entity):
            points += 1
            flags.append("ongoing_sync")
            reasons.append("ongoing-sync signal detected — recurring MERGE needed (+1)")

        # Non-clean partition/sort
        if conversion.partition_mapping and conversion.partition_mapping.decision_flags:
            for flag in conversion.partition_mapping.decision_flags:
                if flag in ("partition_decision_required", "sort_decision_required"):
                    points += 1
                    flags.append(flag)
                    reasons.append(f"{flag.replace('_', ' ')} (+1)")

        # Category
        if points == 0:
            category = EffortCategory.AUTO
        elif points <= 2:
            category = EffortCategory.ASSISTED
        else:
            category = EffortCategory.MANUAL

        # Confidence
        if entity.num_bytes is None:
            confidence = ConfidenceLevel.LOW
        else:
            confidence = ConfidenceLevel.HIGH

        return EffortResult(
            category=category,
            score=points,
            flags=flags,
            reasoning="; ".join(reasons) if reasons else "No effort factors detected — fully automatable.",
            confidence=confidence,
        )

    def _has_sync_signal(self, entity: EntityMetadata) -> bool:
        if entity.time_partitioning:
            field = entity.time_partitioning.field or ""
            if field and (field.upper() == "_PARTITIONTIME" or field.lower() in _SYNC_SIGNALS):
                return True
        for col in entity.columns:
            if col.name and col.name.lower() in _SYNC_SIGNALS:
                return True
        return False
