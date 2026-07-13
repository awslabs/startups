# Feature: bq-assess-lakehouse, Property 13: Migration Effort is Tables-only and additive
# Feature: bq-assess-lakehouse, Property 14: Query Complexity never fails on missing input
# Feature: bq-assess-lakehouse, Property 17: Query text anonymization
"""Property tests P13, P14, P17 — the scoring/anonymization gaps from the audit.

- **P13** Migration Effort is Tables-only and additive — Validates R9.1-R9.5
- **P14** Query Complexity never fails on missing input — Validates R11.5
- **P17** Query text anonymization — Validates R10.4, R17.4, R22.4

(P18 placement and P19 relationships are handled separately — they exposed real bugs.)
"""

from __future__ import annotations

import re

import hypothesis.strategies as st
from hypothesis import given, settings

from bq_assess.core.sql_surface import SQLSurfaceAnalyzer
from bq_assess.models import (
    ComplexityCategory,
    ConfidenceLevel,
    ConfidenceSource,
    ConversionResult,
    EffortCategory,
    LossyCast,
    PartitionMapping,
)
from bq_assess.scoring.complexity import ComplexityScorer
from bq_assess.scoring.effort import EffortScorer

from tests.conftest import entity_metadata


# ---------------------------------------------------------------------------
# P13: Migration Effort is Tables-only and additive — R9.1-R9.5
# ---------------------------------------------------------------------------


@st.composite
def _conversion_result(draw: st.DrawFn) -> ConversionResult:
    """A successful ConversionResult with a random but known number of lossy casts
    and an optional non-clean partition decision flag — the additive factors P13 checks."""
    n_lossy = draw(st.integers(min_value=0, max_value=3))
    lossy = [
        LossyCast(column=f"c{i}", source_type="GEOGRAPHY", iceberg_type="binary",
                  loss_description="no native geo")
        for i in range(n_lossy)
    ]
    decision_flags: list[str] = []
    if draw(st.booleans()):
        decision_flags.append(
            draw(st.sampled_from(["partition_decision_required", "sort_decision_required"]))
        )
    pm = PartitionMapping(
        iceberg_transforms=[], sort_order=[], auto_derived=not decision_flags,
        decision_flags=decision_flags,
    )
    return ConversionResult(
        ddl="CREATE TABLE t (id long);",
        partition_mapping=pm,
        lossy_casts=lossy,
        warnings=[],
        success=True,
    )


@settings(max_examples=100)
@given(entity=entity_metadata(), conversion=_conversion_result())
def test_p13_effort_tables_only_and_additive(entity, conversion):
    """Effort = sum of factor points; category follows AUTO=0/ASSISTED<=2/MANUAL>2;
    flags match contributing factors. (REBUILT entities are not scored by EffortScorer —
    the pipeline fixes their effort to None; see P-spec note.)"""
    # Feature: bq-assess-lakehouse, Property 13: Migration Effort is Tables-only and additive
    result = EffortScorer().score(entity, conversion)

    # Additivity: score equals the documented sum of contributing factors.
    expected = 0
    size = entity.num_bytes or 0
    if size >= 100 * 1024**3:
        expected += 2
    elif size >= 1024**3:
        expected += 1
    expected += len(conversion.lossy_casts)
    # sync signal
    sync = False
    if entity.time_partitioning and (entity.time_partitioning.field or "").lower() in (
        "_partitiontime", "updated_at", "modified_at", "ingestion_time"
    ):
        sync = True
    if any((c.name or "").lower() in (
        "_partitiontime", "updated_at", "modified_at", "ingestion_time"
    ) for c in entity.columns):
        sync = True
    if sync:
        expected += 1
    expected += sum(
        1 for f in conversion.partition_mapping.decision_flags
        if f in ("partition_decision_required", "sort_decision_required")
    )

    assert result.score == expected, f"score {result.score} != additive sum {expected}"

    # Category thresholds (AUTO=0, ASSISTED 1..2, MANUAL >2)
    if result.score == 0:
        assert result.category is EffortCategory.AUTO
    elif result.score <= 2:
        assert result.category is EffortCategory.ASSISTED
    else:
        assert result.category is EffortCategory.MANUAL

    # Flags correspond to contributing factors (lossy flag present iff lossy casts)
    assert ("lossy_casts" in result.flags) == (len(conversion.lossy_casts) > 0)


# ---------------------------------------------------------------------------
# P14: Query Complexity never fails on missing input — R11.5
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(entity=entity_metadata())
def test_p14_complexity_never_fails_on_missing_input(entity):
    """With no constructs and no logs, the scorer returns a LOW-confidence result with an
    explicit 'no read workload visible' state — never raises, never omits the entity."""
    # Feature: bq-assess-lakehouse, Property 14: Query Complexity never fails on missing input
    result = ComplexityScorer().score(entity, constructs=[], relationships=None, has_logs=False)

    assert result is not None
    # No constructs → PORTABLE, score 0
    assert result.category is ComplexityCategory.PORTABLE
    assert result.score == 0

    # If the entity also has no SQL surface, confidence must be LOW with an explicit state.
    has_surface = bool(
        entity.view_query or entity.mview_query or (entity.routine and entity.routine.body)
    )
    if not has_surface:
        assert result.confidence is ConfidenceLevel.LOW
        assert result.confidence_source is ConfidenceSource.SCHEMA_ONLY
        assert "no sql surface" in result.reasoning.lower() or "no read workload" in result.reasoning.lower()


# ---------------------------------------------------------------------------
# P17: Query text anonymization — R10.4, R17.4, R22.4
# ---------------------------------------------------------------------------

# A SQL generator that always embeds a known string literal and a known numeric literal.
@st.composite
def _sql_with_literals(draw: st.DrawFn) -> tuple[str, str, str]:
    str_val = draw(st.text(alphabet=st.characters(whitelist_categories=("L",)), min_size=3, max_size=12))
    num_val = str(draw(st.integers(min_value=1000, max_value=999999)))
    sql = f"SELECT * FROM t WHERE name = '{str_val}' AND amount = {num_val}"
    return sql, str_val, num_val


@settings(max_examples=100)
@given(payload=_sql_with_literals())
def test_p17_anonymization_removes_all_literals(payload):
    """After anonymization, no original string or numeric literal value remains."""
    # Feature: bq-assess-lakehouse, Property 17: Query text anonymization
    sql, str_val, num_val = payload
    out = SQLSurfaceAnalyzer().anonymize(sql)

    # The original quoted string value must be gone.
    assert f"'{str_val}'" not in out
    assert str_val not in out.replace("?", "")  # value not lurking unquoted either
    # The original numeric literal must be gone.
    assert not re.search(rf"(?<!\d){re.escape(num_val)}(?!\d)", out)
