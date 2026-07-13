"""Query Complexity scorer (R11) — two-axis model.

Scores every entity with SQL surface on detected BigQuery-specific constructs.
Categories: PORTABLE / ADAPT / REWRITE. Confidence ladder: LOW (no surface) →
MEDIUM (auto-captured view/UDF defs) → HIGH (query logs).
"""
from __future__ import annotations

from bq_assess.models import (
    ComplexityCategory,
    ComplexityResult,
    ConfidenceLevel,
    ConfidenceSource,
    DetectedConstruct,
    EntityMetadata,
)

_WEIGHTS: dict[str, int] = {
    "JS_UDF": 4,
    "UNNEST": 2,
    "ARRAY_FN": 2,
    "STRUCT_NAV": 1,
    "FUNCTION_DRIFT": 1,
}


class ComplexityScorer:
    """Score query complexity for entities with SQL surface (R11)."""

    @staticmethod
    def build_dep_counts(relationships) -> dict[str, int]:
        """Pre-compute dependent counts from relationships (O(R) once)."""
        counts: dict[str, int] = {}
        if relationships is None:
            return counts
        for r in getattr(relationships, "relationships", []):
            tgt = getattr(r, "target_table", None)
            if tgt:
                counts[tgt] = counts.get(tgt, 0) + 1
        return counts

    def score(
        self,
        entity: EntityMetadata,
        constructs: list[DetectedConstruct],
        relationships=None,
        has_logs: bool = False,
        dep_counts: dict[str, int] | None = None,
    ) -> ComplexityResult:
        """Score query complexity based on detected constructs."""
        points = 0
        flags: list[str] = []
        reasons: list[str] = []

        seen_classes: set[str] = set()
        for c in constructs:
            weight = _WEIGHTS.get(c.construct_class, 1)
            # FUNCTION_DRIFT counts per distinct instance; all others count once per class
            if c.construct_class == "FUNCTION_DRIFT":
                points += weight
                reasons.append(f"{c.construct_class} (+{weight})")
            elif c.construct_class not in seen_classes:
                points += weight
                reasons.append(f"{c.construct_class} (+{weight})")
            if c.construct_class not in seen_classes:
                seen_classes.add(c.construct_class)
                flags.append(c.construct_class)

        # Hub entity bonus — O(1) lookup via pre-computed dict
        if dep_counts is not None:
            dep_count = dep_counts.get(entity.full_name, 0)
            if dep_count >= 3:
                points += 1
                flags.append("hub_entity")
                reasons.append(f"hub entity ({dep_count} dependents) (+1)")

        # Category
        if points == 0:
            category = ComplexityCategory.PORTABLE
        elif points <= 3:
            category = ComplexityCategory.ADAPT
        else:
            category = ComplexityCategory.REWRITE

        # Confidence ladder
        has_surface = bool(
            entity.view_query or entity.mview_query or
            (entity.routine and entity.routine.body)
        )
        if has_logs:
            confidence = ConfidenceLevel.HIGH
            confidence_source = ConfidenceSource.QUERY_LOGS
        elif has_surface:
            confidence = ConfidenceLevel.MEDIUM
            confidence_source = ConfidenceSource.VIEW_DEFINITION
        else:
            confidence = ConfidenceLevel.LOW
            confidence_source = ConfidenceSource.SCHEMA_ONLY

        reasoning = "; ".join(reasons) if reasons else (
            "no SQL surface visible — cannot assess query complexity"
            if not has_surface else "no BigQuery-specific constructs detected"
        )

        return ComplexityResult(
            category=category,
            score=points,
            constructs=constructs,
            flags=flags,
            reasoning=reasoning,
            confidence=confidence,
            confidence_source=confidence_source,
        )
