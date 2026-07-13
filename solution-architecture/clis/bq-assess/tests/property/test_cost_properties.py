# Feature: bq-assess-lakehouse, Property 22: Cost decoupling & range-without-data
# Feature: bq-assess-lakehouse, Property 23: Cost internal consistency
"""Property-based tests for the lakehouse Cost Estimator (issue 5.3 / 5.4).

Realizes the design.md cost-comparison properties:

- **P22** cost decoupling & range-without-data — Validates R18.1, R18.3, R18.4, R18.5, R18.6
- **P23** cost internal consistency + provenance — Validates R18.2, R18.5, R18.7

CRITICAL: these tests drive ``CostEstimator.estimate()`` over GENERATED INPUTS (entities +
PricingDetection + SlotUtilization). They do NOT assert the conftest ``assessment()`` generator
against itself — a CostComparison built by the generator already bakes in the P23 identities, so
testing it would exercise zero production code. The whole point is to test the estimator.
"""

from __future__ import annotations

import hypothesis.strategies as st

from bq_assess.engine.redshift import cost_constants as k
from hypothesis import given, settings

from bq_assess.engine.redshift.cost import CostEstimator
from bq_assess.models import (
    BQPricingModel,
    ConfidenceLevel,
    CostComparison,
    EntityPopulation,
    EntityReport,
    EntityType,
    PricingDetection,
    SlotUtilization,
)

_EDITIONS = ["STANDARD", "ENTERPRISE", "ENTERPRISE_PLUS"]
_PLANS = ["FLEX", "MONTHLY", "ANNUAL", "THREE_YEAR"]


@st.composite
def _entities(draw):
    n = draw(st.integers(min_value=0, max_value=8))
    entities = []
    for i in range(n):
        size_gb = draw(st.floats(min_value=0.0, max_value=1e5, allow_nan=False, allow_infinity=False))
        entities.append(EntityReport(
            full_name=f"ds.t{i}", entity_type=EntityType.TABLE,
            population=EntityPopulation.TABLE, rows=draw(st.integers(0, 10**9)),
            size_gb=size_gb,
            depends_on=[], effort=None, conversion=None, load_sync_dml=None,
            complexity=None, rewrite_guidance=[], placement=None,
        ))
    return entities


@st.composite
def _pricing(draw):
    model = draw(st.sampled_from(list(BQPricingModel)))
    if model is BQPricingModel.CAPACITY:
        base = draw(st.integers(0, 5000))
        return PricingDetection(
            model=model, confidence=ConfidenceLevel.HIGH, source_note="gen",
            edition=draw(st.sampled_from(_EDITIONS)), baseline_slots=base,
            max_slots=draw(st.integers(base, base + 5000)),
            commitment_slots=draw(st.one_of(st.none(), st.integers(0, 5000))),
            commitment_plan=draw(st.sampled_from(_PLANS)),
        )
    return PricingDetection(model=model, confidence=ConfidenceLevel.HIGH, source_note="gen")


@st.composite
def _slots_or_none(draw):
    if draw(st.booleans()):
        return None
    return SlotUtilization(
        avg_slots=draw(st.floats(0.0, 100.0, allow_nan=False)),
        p50_slots=draw(st.floats(0.0, 100.0, allow_nan=False)),
        p99_slots=draw(st.floats(0.0, 200.0, allow_nan=False)),
        peak_slots=draw(st.floats(0.0, 500.0, allow_nan=False)),
        active_hour_fraction=draw(st.floats(0.0, 1.0, allow_nan=False)),
        total_slot_ms=draw(st.integers(0, 10**13)),
        days_sampled=draw(st.integers(1, 60)),
    )


def _estimate(entities, pricing, slots, override=None, effort=10.0):
    return CostEstimator(skip_live_pricing=True).estimate(entities, pricing, slots, override, effort)


@settings(max_examples=200)
@given(entities=_entities(), pricing=_pricing(), slots=_slots_or_none())
def test_p22_aws_is_storage_plus_compute_no_nodes(entities, pricing, slots) -> None:
    """P22(a): AWS is exactly storage + compute, with zero node references anywhere (R18.1/R18.6)."""
    r = _estimate(entities, pricing, slots)
    assert isinstance(r, CostComparison)
    assert len(r.aws_lines) >= 2
    blob = " ".join(line.label + " " + line.source_note
                    for line in r.aws_lines + r.bigquery_breakdown).lower()
    for banned in ("node", "ra3", "xlplus", "provisioned", "deploymentadvisor"):
        assert banned not in blob


@settings(max_examples=200)
@given(entities=_entities(), pricing=_pricing())
def test_p22_range_without_data(entities, pricing) -> None:
    """P22(b): with no slots the compute line is a range (low<high) at LOW, never a point (R18.4)."""
    r = _estimate(entities, pricing, slots=None)
    compute = next(line for line in r.aws_lines if "compute" in line.label.lower())
    assert compute.monthly is None
    assert compute.monthly_low < compute.monthly_high
    assert compute.confidence is ConfidenceLevel.LOW
    assert r.compute_confidence is ConfidenceLevel.LOW


@settings(max_examples=200)
@given(entities=_entities(), pricing=_pricing(), slots=_slots_or_none(),
       effort=st.floats(0.0, 1000.0, allow_nan=False))
def test_p22_breakeven_from_effort_not_count(entities, pricing, slots, effort) -> None:
    """P22(d): migration_onetime tracks aggregate effort, independent of entity count (R18.5)."""
    r = _estimate(entities, pricing, slots, effort=effort)
    # Same effort, different entity count → same one-time cost.
    r2 = _estimate(entities + list(entities), pricing, slots, effort=effort)
    assert r.migration_onetime == r2.migration_onetime


@settings(max_examples=300)
@given(entities=_entities(), pricing=_pricing(), slots=_slots_or_none())
def test_p23_delta_and_annual_identities(entities, pricing, slots) -> None:
    """P23: the bound-crossed delta + annual identities hold for every estimate (R18.5)."""
    r = _estimate(entities, pricing, slots)
    assert r.monthly_delta_low == r.bigquery_monthly - r.aws_monthly_high
    assert r.monthly_delta_high == r.bigquery_monthly - r.aws_monthly_low
    assert r.annual_savings_low == r.monthly_delta_low * 12
    assert r.annual_savings_high == r.monthly_delta_high * 12
    # bound ordering: low <= high (aws_low <= aws_high ⇒ delta_low <= delta_high)
    assert r.monthly_delta_low <= r.monthly_delta_high


@settings(max_examples=200)
@given(entities=_entities(), pricing=_pricing(), slots=_slots_or_none(),
       override=st.floats(0.0, 1e6, allow_nan=False))
def test_p23_override_sets_bigquery_monthly(entities, pricing, slots, override) -> None:
    """P23: a supplied --bigquery-monthly-cost override sets bigquery_monthly exactly (R18.2)."""
    r = _estimate(entities, pricing, slots, override=override)
    assert r.bigquery_monthly == override


@settings(max_examples=200)
@given(entities=_entities(), pricing=_pricing(), slots=_slots_or_none())
def test_p23_every_line_has_source_note(entities, pricing, slots) -> None:
    """P23 / R18.7: every emitted CostLine carries a non-empty source_note."""
    r = _estimate(entities, pricing, slots)
    for line in r.aws_lines + r.bigquery_breakdown:
        assert line.source_note


@settings(max_examples=200)
@given(entities=_entities(), pricing=_pricing(), slots=_slots_or_none())
def test_p22_breakeven_never_iff_no_savings(entities, pricing, slots) -> None:
    """P22: break-even = BREAKEVEN_NEVER only when the matching delta is non-positive (R18.5)."""
    r = _estimate(entities, pricing, slots)
    assert (r.breakeven_months_low == k.BREAKEVEN_NEVER) == (r.monthly_delta_low <= 0)
    assert (r.breakeven_months_high == k.BREAKEVEN_NEVER) == (r.monthly_delta_high <= 0)
