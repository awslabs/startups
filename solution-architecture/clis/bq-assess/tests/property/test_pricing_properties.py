# Feature: bq-assess-lakehouse, Property 20: Pricing model honesty
"""Property-based test for the Pricing Detector (issue 5.1 / 5.4).

Realizes the design.md correctness property for pricing detection:

- **P20** pricing model honesty — Validates R16.1, R16.2, R16.3, R16.4

*For any* Source: a reachable/supplied reservation config → CAPACITY with recorded figures;
an undeterminable Source → ON_DEMAND at LOW confidence (never silently assumed, never the bare
UNKNOWN enum). The single property test the design test-map names is ``test_pricing_properties``.

Inputs come from the ``pricing_jobs`` / ``reservation_config`` strategies (conftest). A tiny
fake client returns the generated rows; the detector never touches a live BigQuery client here.
"""

from __future__ import annotations

from hypothesis import given, settings

from bq_assess.core.pricing import PricingDetector
from bq_assess.models import BQPricingModel, ConfidenceLevel, PricingDetection
from tests.conftest import pricing_jobs, reservation_config


class _FakeClient:
    """Returns canned JOBS rows for any query (no live BigQuery in property tests)."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def query(self, sql: str, *args, **kwargs):
        rows = self._rows

        class _Job:
            def result(self_):
                return iter(rows)

        return _Job()


def _detect(rows, reservation_config=None) -> PricingDetection:
    return PricingDetector().detect(_FakeClient(rows), "proj", reservation_config)


def _assert_universal_honesty(result: PricingDetection) -> None:
    """Invariants that hold for EVERY detect() result, regardless of input (R16.3 / P20)."""
    assert isinstance(result, PricingDetection)
    # Never the bare UNKNOWN enum externally — undeterminable collapses to ON_DEMAND/LOW.
    assert result.model is not BQPricingModel.UNKNOWN
    assert result.model in (BQPricingModel.ON_DEMAND, BQPricingModel.CAPACITY)
    assert isinstance(result.confidence, ConfidenceLevel)
    # Provenance is always recorded (R18.7 / R19.2).
    assert result.source_note
    # Capacity figures appear only on a CAPACITY result.
    if result.model is BQPricingModel.ON_DEMAND:
        assert result.edition is None
        assert result.baseline_slots is None
        assert result.max_slots is None
        assert result.commitment_slots is None
        assert result.commitment_plan is None


@settings(max_examples=200)
@given(jobs=pricing_jobs(), cfg=reservation_config())
def test_pricing_properties_config_supplied_is_capacity(jobs: list[dict], cfg: dict) -> None:
    """P20 (config arm): a supplied --reservation-config → CAPACITY with the figures recorded
    at HIGH confidence, regardless of what the jobs look like (R16.2)."""
    result = _detect(jobs, reservation_config=cfg)
    _assert_universal_honesty(result)
    assert result.model is BQPricingModel.CAPACITY
    assert result.confidence is ConfidenceLevel.HIGH
    assert result.edition == cfg["edition"]
    assert result.baseline_slots == cfg["baseline_slots"]
    assert result.max_slots == cfg["max_slots"]
    assert result.commitment_slots == cfg["commitment_slots"]
    assert result.commitment_plan == cfg["commitment_plan"]


@settings(max_examples=200)
@given(jobs=pricing_jobs())
def test_pricing_properties_auto_detection_is_honest(jobs: list[dict]) -> None:
    """P20 (auto arm, no config): the verdict honestly reflects the JOBS signal —
    any non-null reservation_id (on a non-SCRIPT leaf) → CAPACITY; otherwise ON_DEMAND.
    Undeterminable (no leaf signal) is ON_DEMAND at LOW, never UNKNOWN (R16.3)."""
    result = _detect(jobs, reservation_config=None)
    _assert_universal_honesty(result)

    leaf = [j for j in jobs if j.get("statement_type") != "SCRIPT"]
    any_capacity = any(j.get("reservation_id") is not None for j in leaf)

    if any_capacity:
        assert result.model is BQPricingModel.CAPACITY
    elif not leaf:
        # No usable leaf signal → undeterminable → ON_DEMAND at LOW with a prompt.
        assert result.model is BQPricingModel.ON_DEMAND
        assert result.confidence is ConfidenceLevel.LOW
        assert "--reservation-config" in result.source_note
    else:
        assert result.model is BQPricingModel.ON_DEMAND


@settings(max_examples=100)
@given(jobs=pricing_jobs(), cfg=reservation_config())
def test_detector_emits_no_node_concepts(jobs: list[dict], cfg: dict) -> None:
    """Detector-boundary decoupling guard (supports P22, which the Cost tests validate):
    the Pricing Detector classifies billing, not cluster shape — nothing it emits names a
    Redshift node count/type."""
    for result in (_detect(jobs), _detect(jobs, reservation_config=cfg)):
        note = result.source_note.lower()
        for term in ("node", "ra3", "dc2", "xlplus", "cluster"):
            assert term not in note
