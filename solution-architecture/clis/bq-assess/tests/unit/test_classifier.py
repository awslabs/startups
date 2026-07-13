"""Unit tests for the entity classifier — EntityType → EntityPopulation (R4.1-R4.3).

The P5 Hypothesis property (classification partitions the population) is owned by issue #8;
these unit tests pin the explicit mapping, totality, and disjointness for issue #7 (1.2).
"""

from __future__ import annotations

import pytest

from bq_assess.core.classifier import (
    classify_population,
    is_table_population,
)
from bq_assess.models import EntityPopulation, EntityType


class TestClassifyPopulation:
    @pytest.mark.parametrize(
        ("entity_type", "expected"),
        [
            (EntityType.TABLE, EntityPopulation.TABLE),
            (EntityType.EXTERNAL, EntityPopulation.TABLE),
            (EntityType.VIEW, EntityPopulation.REBUILT),
            (EntityType.MATERIALIZED_VIEW, EntityPopulation.REBUILT),
            (EntityType.ROUTINE, EntityPopulation.REBUILT),
        ],
    )
    def test_explicit_mapping(self, entity_type, expected):
        assert classify_population(entity_type) is expected

    def test_mapping_is_total(self):
        """Every EntityType maps to a population (no member left unclassified)."""
        for et in EntityType:
            result = classify_population(et)
            assert isinstance(result, EntityPopulation)

    def test_mapping_is_disjoint(self):
        """TABLE and REBUILT populations do not overlap across the type set."""
        table_types = {et for et in EntityType if classify_population(et) is EntityPopulation.TABLE}
        rebuilt_types = {et for et in EntityType if classify_population(et) is EntityPopulation.REBUILT}
        assert table_types.isdisjoint(rebuilt_types)
        # Union covers every EntityType (total partition)
        assert table_types | rebuilt_types == set(EntityType)

    def test_table_population_membership(self):
        assert table_types_only() == {EntityType.TABLE, EntityType.EXTERNAL}

    def test_invalid_input_raises(self):
        with pytest.raises(TypeError):
            classify_population("TABLE")  # not an EntityType


class TestIsTablePopulation:
    def test_true_for_table_and_external(self):
        assert is_table_population(EntityType.TABLE)
        assert is_table_population(EntityType.EXTERNAL)

    def test_false_for_rebuilt_types(self):
        assert not is_table_population(EntityType.VIEW)
        assert not is_table_population(EntityType.MATERIALIZED_VIEW)
        assert not is_table_population(EntityType.ROUTINE)


def table_types_only() -> set[EntityType]:
    """Helper: the set of EntityTypes classified into the TABLE population."""
    return {et for et in EntityType if is_table_population(et)}
