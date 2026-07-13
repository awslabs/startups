"""Entity classifier — EntityType → EntityPopulation (Table vs View/MV/UDF).

Canonical, single source of truth for the population partition (R4.1-R4.3, property P5):
- TABLE / EXTERNAL  → population TABLE   (entities that *move*; scored on both axes)
- VIEW / MATERIALIZED_VIEW / ROUTINE → population REBUILT  (rebuilt; Query Complexity only)

The mapping is **total** (every EntityType maps) and **disjoint** (exactly one population).

Issue #7 / 1.2. NOTE: ``core/scanner.py`` (#6) currently carries a local ``population_for``
helper; once both land on main it should delegate to ``classify_population`` here so there
is one definition (see SCRUM_NOTES).
"""

from __future__ import annotations

from bq_assess.models import EntityPopulation, EntityType

# The entity types whose migration means *moving data* into the Storage Target (R4.2).
# Everything else is *rebuilt* SQL behavior (R4.3). Kept as an explicit frozenset so the
# partition is obvious and exhaustively testable.
_TABLE_POPULATION_TYPES: frozenset[EntityType] = frozenset(
    {EntityType.TABLE, EntityType.EXTERNAL}
)


def classify_population(entity_type: EntityType) -> EntityPopulation:
    """Return the EntityPopulation for an EntityType (total, disjoint partition).

    TABLE / EXTERNAL → ``EntityPopulation.TABLE``; VIEW / MATERIALIZED_VIEW / ROUTINE →
    ``EntityPopulation.REBUILT`` (R4.2/R4.3). Raises ``TypeError`` if given something that
    is not an ``EntityType``, so an unmapped future enum member fails loudly rather than
    silently defaulting.
    """
    if not isinstance(entity_type, EntityType):
        raise TypeError(f"expected EntityType, got {type(entity_type).__name__}")
    return (
        EntityPopulation.TABLE
        if entity_type in _TABLE_POPULATION_TYPES
        else EntityPopulation.REBUILT
    )


def is_table_population(entity_type: EntityType) -> bool:
    """Convenience predicate: True iff *entity_type* belongs to the TABLE population."""
    return entity_type in _TABLE_POPULATION_TYPES
