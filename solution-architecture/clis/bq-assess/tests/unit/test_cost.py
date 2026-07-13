# Feature: bq-assess-lakehouse, issue 5.3: CostEstimator (R18)
"""Unit tests for the lakehouse Cost Estimator (BigQuery vs AWS run-rate comparison).

Drives ``CostEstimator.estimate()`` (R18): AWS = S3 Tables storage (V2) + Serverless RPU
compute (V1) via the slot→RPU bridge (V3), no node sizing (R18.6); BQ priced per the detected
model (R16.4); ``--bigquery-monthly-cost`` override wins (R18.2); compute is a point at MED/HIGH
with slots else a LOW-confidence range (R18.3/R18.4); every CostLine carries a dated source_note
and every constant is overridable (R18.7).

Inputs unique to this signature (PricingDetection, SlotUtilization) have no conftest strategy
yet (owed by 5.1/5.2 — they were TDD'd with ad-hoc inputs); built here as local helpers.
"""

from __future__ import annotations

import inspect

import pytest

from bq_assess.core import pricing_constants as v4
from bq_assess.engine.redshift import cost_constants as k
from bq_assess.engine.redshift.cost import CostEstimator
from bq_assess.models import (
    BQPricingModel,
    ConfidenceLevel,
    CostComparison,
    EntityPopulation,
    EntityType,
    PricingDetection,
    SlotUtilization,
)

# --- input helpers (local; PricingDetection/SlotUtilization have no conftest strategy yet) ----


def ondemand_pricing() -> PricingDetection:
    return PricingDetection(
        model=BQPricingModel.ON_DEMAND, confidence=ConfidenceLevel.HIGH,
        source_note="on-demand (test)",
    )


def capacity_pricing(edition="ENTERPRISE", baseline_slots=100, max_slots=200,
                     commitment_slots=100, commitment_plan="ANNUAL") -> PricingDetection:
    return PricingDetection(
        model=BQPricingModel.CAPACITY, confidence=ConfidenceLevel.HIGH,
        source_note="capacity (test)", edition=edition, baseline_slots=baseline_slots,
        max_slots=max_slots, commitment_slots=commitment_slots, commitment_plan=commitment_plan,
    )


def slot_util(*, total_slot_ms=730 * 3_600_000, days_sampled=14, avg=1.0, peak=2.0) -> SlotUtilization:
    return SlotUtilization(
        avg_slots=avg, p50_slots=avg, p99_slots=peak, peak_slots=peak,
        active_hour_fraction=0.5, total_slot_ms=total_slot_ms, days_sampled=days_sampled,
    )


def entity(size_gb=100.0, name="ds.t1"):
    """A minimal EntityReport carrying the size the cost model reads."""
    from bq_assess.models import EntityReport
    return EntityReport(
        full_name=name, entity_type=EntityType.TABLE, population=EntityPopulation.TABLE,
        rows=1000, size_gb=size_gb, depends_on=[], effort=None, conversion=None,
        load_sync_dml=None, complexity=None, rewrite_guidance=[], placement=None,
    )


def _estimate(entities=None, *, pricing=None, slots=None, override=None, effort=10.0):
    return CostEstimator(skip_live_pricing=True).estimate(
        entities if entities is not None else [entity()],
        pricing or ondemand_pricing(),
        slots,
        override,
        effort,
    )


# --- Phase A: signature + structure ---------------------------------------------------

def test_estimate_signature_matches_contract() -> None:
    """estimate() params match design.md exactly; entities/effort_total unannotated.

    ``location`` (keyword-only, default None) was added by the 2026-07-02 region-cascade
    amendment — see SCRUM_NOTES § Signature amendment 2026-07-02. Default None preserves
    the pre-amendment behavior for existing positional callers.
    ``storage_basis`` (keyword-only, default "assumed") was added by the 2026-07-08
    physical-bytes storage sizing feature (Task 4).
    """
    sig = inspect.signature(CostEstimator.estimate)
    params = list(sig.parameters)
    assert params == ["self", "entities", "pricing", "slots", "bq_monthly_override",
                      "effort_total", "location", "storage_basis"]
    assert sig.parameters["location"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["location"].default is None
    assert sig.parameters["storage_basis"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["storage_basis"].default == "assumed"


def test_returns_costcomparison() -> None:
    """estimate() returns a fully-populated CostComparison."""
    result = _estimate()
    assert isinstance(result, CostComparison)
    assert isinstance(result.bq_pricing_model, BQPricingModel)
    assert isinstance(result.compute_confidence, ConfidenceLevel)


def _aws(line_label, result):
    return next(line for line in result.aws_lines if line_label in line.label)


def test_aws_has_storage_and_compute_line() -> None:
    """AWS run-rate = storage line + compute line, both always present (R18.1)."""
    r = _estimate(slots=slot_util())
    labels = " ".join(line.label for line in r.aws_lines)
    assert "storage" in labels.lower()
    assert "compute" in labels.lower()
    assert len(r.aws_lines) >= 2


def test_aws_total_sums_all_lines_point_case() -> None:
    """With slots (point compute), aws bounds equal the sum of all line points (R18.1)."""
    r = _estimate(slots=slot_util())
    total = sum(line.monthly for line in r.aws_lines)
    assert r.aws_monthly_low == r.aws_monthly_high          # point case: bounds equal
    assert round(r.aws_monthly_low, 4) == round(total, 4)


# --- Phase B: compute switch (slots present → point MED/HIGH; absent → range LOW) -----

def test_compute_point_when_slots_present() -> None:
    """R18.3: with slots the compute line is a point at MED/HIGH, never LOW."""
    r = _estimate(slots=slot_util(days_sampled=14))
    compute = _aws("compute", r)
    assert compute.monthly is not None
    assert compute.monthly_low is None and compute.monthly_high is None
    assert compute.confidence in (ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH)
    assert r.compute_confidence is compute.confidence


def test_compute_high_confidence_when_week_plus_sampled() -> None:
    """>=7 days sampled → HIGH; <7 → MEDIUM (R18.3 / D7); never LOW with slots."""
    assert _estimate(slots=slot_util(days_sampled=7)).compute_confidence is ConfidenceLevel.HIGH
    assert _estimate(slots=slot_util(days_sampled=3)).compute_confidence is ConfidenceLevel.MEDIUM


def test_compute_range_when_slots_absent() -> None:
    """R18.4: no slots → compute is a range (low < high) at LOW, never a point."""
    r = _estimate(slots=None)
    compute = _aws("compute", r)
    assert compute.monthly is None                          # strictly not a point
    assert compute.monthly_low < compute.monthly_high
    assert compute.confidence is ConfidenceLevel.LOW
    assert r.compute_confidence is ConfidenceLevel.LOW


def test_aws_bounds_spread_when_compute_is_range() -> None:
    """The range branch must spread aws bounds via the compute low/high fallback (audit G3)."""
    r = _estimate(slots=None)
    assert r.aws_monthly_low < r.aws_monthly_high


def test_zero_slot_ms_workload_yields_range_not_confident_zero() -> None:
    """A SlotUtilization with total_slot_ms==0 carries no compute signal → LOW range, not a
    confident $0 point (review #5/#12). All-cached/metadata jobs produce this."""
    r = _estimate(slots=slot_util(total_slot_ms=0, days_sampled=14))
    compute = _aws("compute", r)
    assert compute.monthly is None                 # NOT a confident $0.00 point
    assert compute.monthly_low < compute.monthly_high
    assert r.compute_confidence is ConfidenceLevel.LOW


def test_compute_range_labels_estimate() -> None:
    """R18.4 / R20.6: the range source_note marks it an estimate + suggests query logs."""
    note = _aws("compute", _estimate(slots=None)).source_note.lower()
    assert "estimate" in note
    assert "query log" in note


def test_compute_depends_on_slot_ms_not_active_day_count() -> None:
    """Compute tracks total_slot_ms over the lookback window, NOT days_sampled (active days).
    Scaling by active-day count over-extrapolates a sparse workload (review #2)."""
    sparse = _estimate(slots=slot_util(total_slot_ms=365 * 3_600_000, days_sampled=3))
    dense = _estimate(slots=slot_util(total_slot_ms=365 * 3_600_000, days_sampled=30))
    # Same slot-ms over the same window → same monthly compute regardless of how many distinct
    # days saw activity (the old code inflated `sparse` 10× by dividing by days_sampled).
    assert _aws("compute", sparse).monthly == _aws("compute", dense).monthly
    # And the figure is the honest slot-hours × V3 ratio × rate (rounded to 4 dp).
    assert _aws("compute", dense).monthly == round(
        365 * k.V3_SLOT_TO_RPU_RATIO * k.V1_RPU_HOUR_USD, 4)


# --- Phase C: BigQuery pricing paths --------------------------------------------------

def test_ondemand_prices_storage_plus_bytes_scanned() -> None:
    """R18.2a: on-demand BQ = storage line + bytes-scanned line; scanned cites $/TiB."""
    r = _estimate(pricing=ondemand_pricing(), slots=slot_util())
    labels = [line.label.lower() for line in r.bigquery_breakdown]
    assert any("storage" in x for x in labels)
    assert any("scan" in x for x in labels)
    scan_line = next(line for line in r.bigquery_breakdown if "scan" in line.label.lower())
    assert str(v4.V4_ONDEMAND_USD_PER_TIB) in scan_line.source_note


def test_bq_breakdown_sums_to_bigquery_monthly() -> None:
    """The BQ breakdown lines explain (sum to) bigquery_monthly (audit G17)."""
    r = _estimate(pricing=ondemand_pricing(), slots=slot_util())
    total = sum(line.monthly for line in r.bigquery_breakdown)
    assert round(total, 4) == round(r.bigquery_monthly, 4)


def test_capacity_prices_from_reservation_figures() -> None:
    """R18.2b: capacity priced from edition × plan-rate × slots × 730; no on-demand line."""
    pricing = capacity_pricing(edition="ENTERPRISE", commitment_slots=100, commitment_plan="ANNUAL")
    r = _estimate(pricing=pricing)
    rate = v4.V4_EDITION_SLOT_HOUR_USD["ENTERPRISE"]["commit_1yr"]   # ANNUAL → commit_1yr
    assert round(r.bigquery_monthly, 4) == round(100 * rate * k.HOURS_PER_MONTH, 4)
    assert not any("scan" in line.label.lower() for line in r.bigquery_breakdown)


def test_capacity_plan_maps_to_rate_key() -> None:
    """commitment_plan vocabulary maps to V4 rate keys; FLEX/MONTHLY → payg (audit G7)."""
    ent = v4.V4_EDITION_SLOT_HOUR_USD["ENTERPRISE"]
    for plan, key in [("ANNUAL", "commit_1yr"), ("THREE_YEAR", "commit_3yr"),
                      ("MONTHLY", "payg"), ("FLEX", "payg")]:
        r = _estimate(pricing=capacity_pricing(commitment_slots=10, commitment_plan=plan))
        assert round(r.bigquery_monthly, 4) == round(10 * ent[key] * k.HOURS_PER_MONTH, 4)


def test_capacity_slot_basis_falls_back_commitment_then_baseline_then_max() -> None:
    """D5 precedence: commitment_slots → baseline_slots → max_slots."""
    ent_rate = v4.V4_EDITION_SLOT_HOUR_USD["ENTERPRISE"]["commit_1yr"]
    # commitment present and positive → used
    r1 = _estimate(pricing=capacity_pricing(commitment_slots=50, baseline_slots=10, max_slots=200))
    assert round(r1.bigquery_monthly, 4) == round(50 * ent_rate * k.HOURS_PER_MONTH, 4)
    # commitment None → baseline used
    r2 = _estimate(pricing=capacity_pricing(commitment_slots=None, baseline_slots=10, max_slots=200))
    assert round(r2.bigquery_monthly, 4) == round(10 * ent_rate * k.HOURS_PER_MONTH, 4)
    # commitment + baseline None → max used
    r3 = _estimate(pricing=capacity_pricing(commitment_slots=None, baseline_slots=None, max_slots=200))
    assert round(r3.bigquery_monthly, 4) == round(200 * ent_rate * k.HOURS_PER_MONTH, 4)


def test_commitment_slots_zero_falls_through_to_baseline() -> None:
    """commitment_slots=0 means 'no commitment purchased' — must NOT shadow a valid baseline.
    Regression guard for _first_positive (round-2 review fix #1)."""
    ent_rate = v4.V4_EDITION_SLOT_HOUR_USD["ENTERPRISE"]["commit_1yr"]
    r = _estimate(pricing=capacity_pricing(commitment_slots=0, baseline_slots=100, max_slots=200))
    assert round(r.bigquery_monthly, 4) == round(100 * ent_rate * k.HOURS_PER_MONTH, 4)


def test_standard_edition_commitment_priced_at_payg_not_commit() -> None:
    """STANDARD has no true slot commitments (V4): a STANDARD+ANNUAL config is priced at PAYG,
    flagged, NOT at the commit_1yr rate at HIGH confidence (review #6/#11)."""
    pricing = capacity_pricing(edition="STANDARD", commitment_slots=100, commitment_plan="ANNUAL")
    r = _estimate(pricing=pricing)
    payg = v4.V4_EDITION_SLOT_HOUR_USD["STANDARD"]["payg"]
    assert round(r.bigquery_monthly, 4) == round(100 * payg * k.HOURS_PER_MONTH, 4)
    line = r.bigquery_breakdown[0]
    assert "no true slot commitments" in line.source_note.lower() or "payg" in line.source_note.lower()


def test_unknown_edition_priced_as_enterprise_fallback_low_conf() -> None:
    """An unrecognized edition is priced at ENTERPRISE rates as a labelled LOW-confidence
    fallback, not silently (review #9)."""
    pricing = capacity_pricing(edition="GALACTIC", commitment_slots=100, commitment_plan="ANNUAL")
    r = _estimate(pricing=pricing)
    assert r.bigquery_monthly > 0
    line = r.bigquery_breakdown[0]
    assert line.confidence is ConfidenceLevel.LOW
    assert "galactic" in line.source_note.lower()


def test_zero_rate_override_not_replaced_by_payg(monkeypatch) -> None:
    """A 0.0 rate override is a legitimate value (credit/promo) — not swallowed by `or payg` (#7)."""
    rates = dict(v4.V4_EDITION_SLOT_HOUR_USD["ENTERPRISE"])
    rates["commit_1yr"] = 0.0
    monkeypatch.setitem(v4.V4_EDITION_SLOT_HOUR_USD, "ENTERPRISE", rates)
    r = _estimate(pricing=capacity_pricing(edition="ENTERPRISE", commitment_slots=100,
                                           commitment_plan="ANNUAL"))
    assert r.bigquery_monthly == 0.0      # priced at the 0.0 override, not payg


def test_malformed_capacity_config_does_not_raise() -> None:
    """A string commitment_slots degrades to 0 rather than crashing str×float (review #8/#16)."""
    pricing = capacity_pricing(commitment_slots="oops", baseline_slots=None, max_slots=None)
    r = _estimate(pricing=pricing)
    assert isinstance(r.bigquery_monthly, float)   # no TypeError


def test_capacity_never_falls_back_to_ondemand() -> None:
    """R16.4: a CAPACITY model with no figures is still capacity-priced, never on-demand."""
    pricing = capacity_pricing(commitment_slots=None, baseline_slots=None, max_slots=None)
    r = _estimate(pricing=pricing)
    assert r.bq_pricing_model is BQPricingModel.CAPACITY
    assert not any("scan" in line.label.lower() for line in r.bigquery_breakdown)
    assert not any(str(v4.V4_ONDEMAND_USD_PER_TIB) in line.source_note for line in r.bigquery_breakdown)


def test_bq_pricing_model_equals_detected_model() -> None:
    """R16.4 / R19.2: bq_pricing_model == pricing.model exactly, for all three models."""
    for model, pricing in [
        (BQPricingModel.ON_DEMAND, ondemand_pricing()),
        (BQPricingModel.CAPACITY, capacity_pricing()),
        (BQPricingModel.UNKNOWN, PricingDetection(
            model=BQPricingModel.UNKNOWN, confidence=ConfidenceLevel.LOW, source_note="?")),
    ]:
        assert _estimate(pricing=pricing).bq_pricing_model is model


def test_override_takes_precedence() -> None:
    """R18.2c: --bigquery-monthly-cost wins regardless of model."""
    r = _estimate(pricing=capacity_pricing(), override=4242.0)
    assert r.bigquery_monthly == 4242.0


# --- Phase D: deltas / annual / break-even (R18.5, bound cross) -----------------------

def test_delta_and_annual_identities() -> None:
    """R18.5 / P23: bound-crossed delta + annual = delta × 12."""
    r = _estimate(slots=slot_util())
    assert r.monthly_delta_low == r.bigquery_monthly - r.aws_monthly_high
    assert r.monthly_delta_high == r.bigquery_monthly - r.aws_monthly_low
    assert r.annual_savings_low == r.monthly_delta_low * 12
    assert r.annual_savings_high == r.monthly_delta_high * 12


def test_breakeven_from_effort_not_table_count() -> None:
    """R18.5 / R9.2: migration_onetime tracks aggregate Effort, not entity count."""
    low_effort = _estimate(effort=10.0)
    high_effort = _estimate(effort=100.0)
    assert high_effort.migration_onetime > low_effort.migration_onetime
    # Vary entity count, hold effort → one-time cost unchanged.
    few = _estimate([entity()], effort=50.0)
    many = _estimate([entity(name=f"ds.t{i}") for i in range(50)], effort=50.0)
    assert few.migration_onetime == many.migration_onetime


def test_breakeven_never_when_no_savings() -> None:
    """D6: AWS ≥ BQ (delta ≤ 0) → break-even = BREAKEVEN_NEVER (JSON-safe sentinel)."""
    # Make BQ tiny so AWS dwarfs it → negative delta.
    r = _estimate(slots=None, override=0.0)
    assert r.monthly_delta_high <= 0
    assert r.breakeven_months_low == k.BREAKEVEN_NEVER
    assert r.breakeven_months_high == k.BREAKEVEN_NEVER


def test_breakeven_mixed_when_bounds_straddle_zero() -> None:
    """When the savings range straddles zero, low break-even = BREAKEVEN_NEVER, high is finite."""
    # Tune override so bigquery sits between aws_low and aws_high.
    probe = _estimate(slots=None)
    mid = (probe.aws_monthly_low + probe.aws_monthly_high) / 2
    r = _estimate(slots=None, override=mid)
    assert r.monthly_delta_low < 0 < r.monthly_delta_high
    assert r.breakeven_months_low == k.BREAKEVEN_NEVER
    assert 0 < r.breakeven_months_high < k.BREAKEVEN_NEVER


def test_breakeven_never_is_json_serializable() -> None:
    """BREAKEVEN_NEVER must be finite so it serializes to JSON (RFC 7159).
    Regression guard: math.inf would pass equality tests but crash json.dumps."""
    import json
    import math
    r = _estimate(slots=None, override=0.0)
    assert r.breakeven_months_low == k.BREAKEVEN_NEVER
    assert math.isfinite(r.breakeven_months_low)
    assert math.isfinite(r.breakeven_months_high)
    json.dumps([r.breakeven_months_low, r.breakeven_months_high])  # ValueError if inf/nan


def test_negative_savings_not_clamped() -> None:
    """Negative deltas/annual are reported as negative, not clamped to 0 (audit G13)."""
    r = _estimate(slots=None, override=0.0)
    assert r.monthly_delta_low < 0
    assert r.annual_savings_low < 0


def test_zero_entities_no_crash() -> None:
    """Empty project → zero storage, both AWS lines still present, no divide-by-zero (audit G9)."""
    r = _estimate([], slots=None)
    assert isinstance(r, CostComparison)
    assert len(r.aws_lines) >= 2


# --- Phase E: decoupling & no node sizing (R18.6) -------------------------------------

def test_compute_not_sized_by_stored_bytes() -> None:
    """R18.6: compute is a function of slots only — identical when only storage scales."""
    small = _estimate([entity(size_gb=1.0)], slots=slot_util())
    large = _estimate([entity(size_gb=10_000.0)], slots=slot_util())
    assert _aws("compute", small).monthly == _aws("compute", large).monthly
    assert _aws("storage", small).monthly < _aws("storage", large).monthly   # storage does scale


def test_no_node_strings_anywhere() -> None:
    """R18.6: no node/RA3/provisioned/advisor leakage in any label or source_note."""
    for slots in (slot_util(), None):
        for pricing in (ondemand_pricing(), capacity_pricing()):
            r = _estimate(pricing=pricing, slots=slots)
            blob = " ".join(
                line.label + " " + line.source_note
                for line in r.aws_lines + r.bigquery_breakdown
            ).lower()
            for banned in ("node", "ra3", "xlplus", "4xlarge", "16xlarge", "provisioned",
                           "deploymentadvisor", "redshift_type"):
                assert banned not in blob


def test_costcomparison_has_no_node_fields() -> None:
    """R18.6: the dataclass exposes no node/type/advisor field (regression vs legacy)."""
    import dataclasses
    names = {f.name for f in dataclasses.fields(CostComparison)}
    for banned in ("node", "node_type", "redshift_type", "deployment", "advisor"):
        assert banned not in names


# --- Phase F: provenance + overridability (R18.7) -------------------------------------

def test_every_costline_has_dated_source_note() -> None:
    """R18.7: every line carries a non-empty source_note containing a date token."""
    for slots in (slot_util(), None):
        for pricing in (ondemand_pricing(), capacity_pricing()):
            r = _estimate(pricing=pricing, slots=slots)
            for line in r.aws_lines + r.bigquery_breakdown:
                assert line.source_note
                assert "2026-" in line.source_note          # V1/V2 (2026-06-15) or V4 (2026-06-11)


def test_overriding_v1_changes_compute(monkeypatch) -> None:
    """R18.7: V1 RPU rate is overridable, not hardcoded — compute line moves."""
    base = _aws("compute", _estimate(slots=slot_util())).monthly
    monkeypatch.setattr(k, "V1_RPU_HOUR_USD", k.V1_RPU_HOUR_USD * 2)
    assert _aws("compute", _estimate(slots=slot_util())).monthly > base


def test_overriding_v3_ratio_changes_compute(monkeypatch) -> None:
    """R18.7 / D4: the V3 slot→RPU ratio is the one tunable; compute scales with it."""
    base = _aws("compute", _estimate(slots=slot_util())).monthly
    monkeypatch.setattr(k, "V3_SLOT_TO_RPU_RATIO", k.V3_SLOT_TO_RPU_RATIO * 3)
    assert _aws("compute", _estimate(slots=slot_util())).monthly == pytest.approx(base * 3, rel=1e-3)


def test_overriding_v2_changes_storage(monkeypatch) -> None:
    """R18.7: V2 S3 Tables storage rate is overridable (audit G11)."""
    base = _aws("storage", _estimate()).monthly
    monkeypatch.setattr(k, "V2_S3_TABLES_USD_PER_GB_MONTH_TIER1", k.V2_S3_TABLES_USD_PER_GB_MONTH_TIER1 * 2)
    assert _aws("storage", _estimate()).monthly > base


def test_overriding_v4_changes_bq(monkeypatch) -> None:
    """R18.7: V4 BQ on-demand rate is overridable — BQ scanned line moves (audit G11)."""
    # Large entity so monthly scan exceeds the 1 TiB free tier and the rate actually bites.
    big = [entity(size_gb=500_000.0)]
    base = _estimate(big, pricing=ondemand_pricing(), slots=slot_util()).bigquery_monthly
    monkeypatch.setattr(v4, "V4_ONDEMAND_USD_PER_TIB", v4.V4_ONDEMAND_USD_PER_TIB * 5)
    assert _estimate(big, pricing=ondemand_pricing(), slots=slot_util()).bigquery_monthly > base


def test_v3_source_note_labels_assumption() -> None:
    """R18.7 / R20.6: the compute source_note flags V3 as a LOW-confidence assumption."""
    note = _aws("compute", _estimate(slots=slot_util())).source_note.lower()
    assert "assumption" in note


# --- Multi-scenario fixes: storage basis + money formatting ---------------------------
# These cover two bugs found reviewing the multi-scenario engine against a live run:
#   1. provisioned scenarios billed RMS storage instead of the shared S3 Tables basis
#   2. sub-dollar totals rendered as "$0/month" in the recommendation prose
from bq_assess.engine.redshift.cost import _fmt_usd  # noqa: E402


def _scenarios(result):
    return result.aws_scenarios


def test_provisioned_storage_uses_s3_tables_not_rms() -> None:
    """All scenarios — serverless AND provisioned — share the S3 Tables storage basis.

    Data lives in S3 Tables (decoupled lakehouse) and is queried via external tables, so the
    storage line must NOT change with the query engine. Provisioned must not bill RMS.
    """
    result = _estimate(slots=slot_util())
    prov = [s for s in _scenarios(result) if s.category.startswith("PROVISIONED")]
    assert prov, "expected provisioned scenarios when slot data is present"
    for s in prov:
        storage_lines = [ln for ln in s.lines if "storage" in ln.label.lower()]
        assert storage_lines, f"{s.label} has no storage line"
        for ln in storage_lines:
            assert "S3 Tables" in ln.label
            blob = (ln.label + " " + ln.source_note).lower()
            assert "managed storage" not in blob
            assert "ra3" not in blob


def test_storage_value_identical_across_all_scenarios() -> None:
    """Storage cost must not vary by engine — same bytes, same S3 Tables basis everywhere."""
    result = _estimate(slots=slot_util())
    storage_vals = []
    for s in _scenarios(result):
        ln = next(x for x in s.lines if "storage" in x.label.lower())
        storage_vals.append(round(ln.monthly, 6))
    assert len(set(storage_vals)) == 1, f"storage differs across scenarios: {storage_vals}"


def test_fmt_usd_does_not_round_subdollar_to_zero() -> None:
    """Sub-dollar amounts keep cents; $1+ are comma-grouped whole dollars."""
    assert _fmt_usd(0.1151) == "$0.12"
    assert _fmt_usd(0.0) == "$0.00"
    assert _fmt_usd(0.9) == "$0.90"
    assert _fmt_usd(1.0) == "$1"
    assert _fmt_usd(893.23) == "$893"
    assert _fmt_usd(43210.0) == "$43,210"
    assert _fmt_usd(-0.10) == "-$0.10"


def test_recommendation_prose_never_says_zero_dollars_for_real_cost() -> None:
    """A sub-dollar serverless workload must not be described as '$0/month'."""
    result = _estimate(
        [entity(size_gb=0.03)],
        slots=slot_util(total_slot_ms=7_000_000, days_sampled=30, avg=0.003, peak=0.03),
    )
    rec = result.recommendation
    assert rec is not None
    assert "$0/month" not in rec.reasoning


# --- Region cascade (2026-07-02): price both clouds in the Source's geography ----------
# Root cause of the Montu underestimate: an australia-southeast1 Source was priced at US
# multi-region rates ($6.25/TiB vs Sydney's $8.125). These tests pin the cascade.

@pytest.fixture()
def _restore_region_constants():
    """Snapshot/restore the module constants the region cascade mutates."""
    v4_snap = {n: getattr(v4, n) for n in (
        "V4_ONDEMAND_USD_PER_TIB", "V4_STORAGE_ACTIVE_LOGICAL_USD_PER_GIB_MONTH",
        "V4_STORAGE_LONGTERM_LOGICAL_USD_PER_GIB_MONTH",
        "V4_STORAGE_ACTIVE_PHYSICAL_USD_PER_GIB_MONTH",
        "V4_STORAGE_LONGTERM_PHYSICAL_USD_PER_GIB_MONTH",
        "V4_EDITION_SLOT_HOUR_USD", "V4_EDITION_RESOURCE_CUD_SLOT_HOUR_USD",
        "V4_PRICING_REGION", "V4_REGION_SCOPE",
    )}
    k_snap = {n: getattr(k, n) for n in (
        "V1_RPU_HOUR_USD", "V1_SERVERLESS_1YR_RPU_HOUR_USD", "V1_SERVERLESS_3YR_RPU_HOUR_USD",
        "V2_S3_TABLES_USD_PER_GB_MONTH_TIER1", "V2_S3_TABLES_USD_PER_GB_MONTH_TIER2",
        "V2_S3_TABLES_USD_PER_GB_MONTH_TIER3", "V6_MANAGED_STORAGE_USD_PER_GB_MONTH",
        "AWS_PRICING_REGION", "AWS_REGION_SCOPE",
    )}
    import copy
    node_snap = (copy.deepcopy(k.V7_RG_NODE_TYPES), copy.deepcopy(k.V6_RA3_NODE_TYPES))
    yield
    for n, val in v4_snap.items():
        setattr(v4, n, val)
    for n, val in k_snap.items():
        setattr(k, n, val)
    k.V7_RG_NODE_TYPES.update(node_snap[0])
    k.V6_RA3_NODE_TYPES.update(node_snap[1])


def _estimate_at(location, **kwargs):
    return CostEstimator(skip_live_pricing=True).estimate(
        kwargs.pop("entities", [entity()]),
        kwargs.pop("pricing", None) or ondemand_pricing(),
        kwargs.pop("slots", None),
        None, 10.0, location=location,
    )


def test_sydney_source_priced_at_sydney_rates(_restore_region_constants) -> None:
    """An australia-southeast1 Source uses $8.125/TiB, not the US $6.25 (Montu bug)."""
    r = _estimate_at("australia-southeast1", slots=slot_util())
    scan = next(ln for ln in r.bigquery_breakdown if "scanned" in ln.label.lower())
    assert "8.125" in scan.source_note
    assert r.bq_pricing_region == "australia-southeast1"
    assert r.aws_pricing_region == "ap-southeast-2"


def test_sydney_costs_more_than_us_for_same_workload(_restore_region_constants) -> None:
    """Same workload, Sydney region → strictly higher BQ estimate than US."""
    big = [entity(size_gb=500_000.0)]
    slots = slot_util()
    us = _estimate_at("US", entities=big, slots=slots).bigquery_monthly
    syd = _estimate_at("australia-southeast1", entities=big, slots=slots).bigquery_monthly
    assert syd > us


def test_aws_side_repriced_with_bq_region(_restore_region_constants) -> None:
    """The AWS comparison uses the mapped region's rates (Sydney RPU $0.419, not $0.375)."""
    r = _estimate_at("australia-southeast1", slots=slot_util())
    compute = next(ln for ln in r.aws_lines if "compute" in ln.label.lower())
    assert "0.419" in compute.source_note


def test_unknown_location_falls_back_to_us_with_caveat(_restore_region_constants) -> None:
    """An unmapped location prices at US rates and carries a scope-note caveat."""
    r = _estimate_at("mars-north1", slots=slot_util())
    scan = next(ln for ln in r.bigquery_breakdown if "scanned" in ln.label.lower())
    assert "6.25" in scan.source_note
    assert any("mars-north1" in n for n in r.scope_notes)


def test_no_location_preserves_module_constants(_restore_region_constants, monkeypatch) -> None:
    """location=None (legacy callers/tests) must not re-point overridden constants (R18.7)."""
    monkeypatch.setattr(v4, "V4_ONDEMAND_USD_PER_TIB", 99.0)
    r = _estimate(pricing=ondemand_pricing(), slots=slot_util())
    scan = next(ln for ln in r.bigquery_breakdown if "scanned" in ln.label.lower())
    assert "99.0" in scan.source_note


def test_scope_notes_disclose_unmodeled_skus(_restore_region_constants) -> None:
    """The estimate must disclose that streaming/Storage API SKUs are out of scope."""
    r = _estimate_at("US", slots=slot_util())
    joined = " ".join(r.scope_notes).lower()
    assert "storage read/write api" in joined
    assert "streaming" in joined


def test_billed_bytes_preferred_over_processed(_restore_region_constants) -> None:
    """Scan cost bills on total_bytes_billed (10 MiB minimums) when available."""
    processed = 10 * (1024 ** 4)
    billed = 15 * (1024 ** 4)   # small-query minimums push billed above processed
    s = SlotUtilization(
        avg_slots=1.0, p50_slots=1.0, p99_slots=2.0, peak_slots=2.0,
        active_hour_fraction=0.5, total_slot_ms=730 * 3_600_000, days_sampled=14,
        total_bytes_processed=processed, total_bytes_billed=billed,
        has_billed_bytes=True, total_queries=100,
    )
    s_proc_only = SlotUtilization(
        avg_slots=1.0, p50_slots=1.0, p99_slots=2.0, peak_slots=2.0,
        active_hour_fraction=0.5, total_slot_ms=730 * 3_600_000, days_sampled=14,
        total_bytes_processed=processed, total_bytes_billed=0, total_queries=100,
    )
    with_billed = _estimate_at("US", slots=s)
    with_processed = _estimate_at("US", slots=s_proc_only)
    assert with_billed.bigquery_monthly > with_processed.bigquery_monthly
    scan = next(ln for ln in with_billed.bigquery_breakdown if "scanned" in ln.label.lower())
    assert "billed" in scan.source_note
    fallback = next(ln for ln in with_processed.bigquery_breakdown if "scanned" in ln.label.lower())
    assert "billed unavailable" in fallback.source_note


def test_degraded_window_never_prices_on_partial_billed_sum(_restore_region_constants) -> None:
    """A degraded window (has_billed_bytes=False) prices on processed bytes even when a
    POSITIVE partial billed sum is present — pricing on the partial sum would silently
    exclude the NULL-billed jobs' volume (2026-07-08 review: the `or billed > 0` clause
    defeated workload.py's degradation policy)."""
    processed = 10 * (1024 ** 4)
    partial_billed = 8 * (1024 ** 4)   # 2 of 10 jobs NULL-billed: sum covers only 8
    s = SlotUtilization(
        avg_slots=1.0, p50_slots=1.0, p99_slots=2.0, peak_slots=2.0,
        active_hour_fraction=0.5, total_slot_ms=730 * 3_600_000, days_sampled=14,
        total_bytes_processed=processed, total_bytes_billed=partial_billed,
        has_billed_bytes=False, total_queries=10, lookback_days=14,
    )
    result = _estimate_at("US", slots=s)
    scan = next(ln for ln in result.bigquery_breakdown if "scanned" in ln.label.lower())
    assert "billed unavailable" in scan.source_note   # processed fallback, labelled
    # Priced on the 10 TiB processed overestimate, not the 8 TiB partial sum.
    assert f"{processed / (1024**4):,.2f} TiB" in scan.source_note


# --- Review fixes (2026-07-03): cascade ordering, projection window, billed-zero -------

def test_cascade_does_not_clobber_live_rates(_restore_region_constants, monkeypatch) -> None:
    """CLI ordering: cascade applied in Stage 9b, live rates layered on top — estimate()
    passing the SAME location must not re-apply the hardcoded table over the live rates."""
    v4.apply_bq_region("australia-southeast1")
    k.apply_aws_region("ap-southeast-2")
    # Live refresh drifts the rates (simulating apply_live_rates)
    monkeypatch.setattr(v4, "V4_ONDEMAND_USD_PER_TIB", 9.99)
    monkeypatch.setattr(k, "V1_RPU_HOUR_USD", 0.5)
    r = _estimate_at("australia-southeast1", slots=slot_util())
    scan = next(ln for ln in r.bigquery_breakdown if "scanned" in ln.label.lower())
    assert "9.99" in scan.source_note      # live rate survived
    compute = next(ln for ln in r.aws_lines if "compute" in ln.label.lower())
    assert "0.5" in compute.source_note


def test_unknown_region_resets_to_us_not_previous(_restore_region_constants) -> None:
    """An unknown location after a regional estimate must reset to US rates, not keep
    the previous region's (the 'priced at US rates' caveat must be true)."""
    _estimate_at("australia-southeast1", slots=slot_util())
    r = _estimate_at("mars-north1", slots=slot_util())
    scan = next(ln for ln in r.bigquery_breakdown if "scanned" in ln.label.lower())
    assert "6.25" in scan.source_note and "8.125" not in scan.source_note
    assert r.bq_pricing_region == "us"


def test_us_central1_has_verified_rates_no_scary_caveat(_restore_region_constants) -> None:
    """us-central1 (the most common single US region) is in the verified table — no
    unknown-region caveat, storage at its regional rate."""
    r = _estimate_at("us-central1", slots=slot_util())
    assert not any("No verified rate table" in n for n in r.scope_notes)
    storage = next(ln for ln in r.bigquery_breakdown if "storage" in ln.label.lower())
    assert "0.023" in storage.source_note


def test_scan_projected_over_calendar_window_not_active_days(_restore_region_constants) -> None:
    """A batch workload active 4 of 30 days projects over the 30-day window (~1×), not
    the 4 active days (7.5× inflation)."""
    ten_tib = 10 * (1024 ** 4)
    s = SlotUtilization(
        avg_slots=1.0, p50_slots=1.0, p99_slots=2.0, peak_slots=2.0,
        active_hour_fraction=0.1, total_slot_ms=4 * 3_600_000, days_sampled=4,
        total_bytes_processed=ten_tib, total_bytes_billed=ten_tib,
        has_billed_bytes=True, total_queries=40, lookback_days=30,
    )
    r = _estimate_at("US", slots=s)
    scan = next(ln for ln in r.bigquery_breakdown if "scanned" in ln.label.lower())
    assert scan.monthly == pytest.approx(10 * 6.25, rel=0.05)   # ~10 TiB/mo, not ~75


def test_billed_zero_window_is_zero_scan_not_fallback(_restore_region_constants) -> None:
    """A window that carried the billed column with a genuine zero (all-cached /
    reservation-served) bills $0 scan — no fallback to processed bytes."""
    s = SlotUtilization(
        avg_slots=1.0, p50_slots=1.0, p99_slots=2.0, peak_slots=2.0,
        active_hour_fraction=0.5, total_slot_ms=730 * 3_600_000, days_sampled=14,
        total_bytes_processed=5 * (1024 ** 4), total_bytes_billed=0,
        has_billed_bytes=True, total_queries=100, lookback_days=14,
    )
    r = _estimate_at("US", slots=s)
    scan = next(ln for ln in r.bigquery_breakdown if "scanned" in ln.label.lower())
    assert scan.monthly == 0
    assert "billed unavailable" not in scan.source_note


def test_workload_profile_scan_volume_matches_cost_basis(_restore_region_constants) -> None:
    """The recommendation's monthly_scanned_tb quotes the same (billed) basis and window
    as the BigQuery cost line — the report must not contradict itself."""
    processed, billed = 10 * (1024 ** 4), 15 * (1024 ** 4)
    s = SlotUtilization(
        avg_slots=1.0, p50_slots=1.0, p99_slots=2.0, peak_slots=2.0,
        active_hour_fraction=0.5, total_slot_ms=730 * 3_600_000, days_sampled=30,
        total_bytes_processed=processed, total_bytes_billed=billed,
        has_billed_bytes=True, total_queries=1000, lookback_days=30,
    )
    r = _estimate_at("US", slots=s)
    wp = r.recommendation.workload_profile
    assert wp.monthly_scanned_tb == pytest.approx((billed / 30 * 30.0) / (1024 ** 4), rel=1e-6)


def test_edition_commitments_use_catalog_factors(_restore_region_constants) -> None:
    """Regional edition commitments follow the catalog's ×0.8/×0.6 SKU factors (Sydney
    ENTERPRISE 1yr $0.0648 = 0.081×0.8, verified), not a fabricated ×0.9/×0.8."""
    v4.apply_bq_region("australia-southeast1")
    assert v4.V4_EDITION_SLOT_HOUR_USD["ENTERPRISE"]["commit_1yr"] == pytest.approx(0.0648)
    assert v4.V4_EDITION_SLOT_HOUR_USD["ENTERPRISE"]["commit_3yr"] == pytest.approx(0.0486)


# --- Round-2 review fixes (2026-07-04) --------------------------------------------------

def test_live_rates_survive_for_region_outside_hardcoded_table(_restore_region_constants) -> None:
    """A live catalog lookup for a region NOT in V4_REGIONAL_RATES stamps the region tag;
    estimate() must then keep those rates instead of resetting to hardcoded US."""
    from bq_assess.core.price_lookup import GCPRates, PricingRates, apply_live_rates
    live = PricingRates(bq_location="asia-east1", aws_region="us-east-1")
    live.gcp = GCPRates(ondemand_usd_per_tib=6.75, storage_active_logical_usd_per_gib=0.023,
                        fetched_at="2026-07-04", source="GCP Cloud Billing Catalog API (asia-east1)")
    apply_live_rates(live)
    assert v4.V4_PRICING_REGION == "asia-east1"

    r = _estimate_at("asia-east1", slots=slot_util())
    scan = next(ln for ln in r.bigquery_breakdown if "scanned" in ln.label.lower())
    assert "6.75" in scan.source_note                      # live rate survived the cascade
    assert r.bq_pricing_region == "asia-east1"
    assert not any("No verified rate table" in n for n in r.scope_notes)


def test_hardcoded_fallback_source_does_not_stamp_freshness(_restore_region_constants) -> None:
    """The GCP fallback's source reads 'hardcoded (verified …)' — apply_live_rates must not
    treat it as live (no date stamp, no region tag update)."""
    from bq_assess.core.price_lookup import GCPRates, PricingRates, apply_live_rates
    before_date, before_region = v4.V4_CONFIRMED_DATE, v4.V4_PRICING_REGION
    fallback = PricingRates(bq_location="australia-southeast1")
    fallback.gcp = GCPRates(ondemand_usd_per_tib=6.25, fetched_at="2026-06-24",
                            source="hardcoded (verified 2026-06-24)")
    apply_live_rates(fallback)
    assert v4.V4_CONFIRMED_DATE == before_date
    assert v4.V4_PRICING_REGION == before_region


def test_default_edition_commitments_match_catalog_factors() -> None:
    """The module-default edition table (location=None path) must carry the same catalog
    x0.8/x0.6 commitment factors apply_bq_region derives — not the fabricated x0.9/x0.8."""
    for edition, rates in v4.V4_EDITION_SLOT_HOUR_USD.items():
        assert rates["commit_1yr"] == pytest.approx(rates["payg"] * 0.8), edition
        assert rates["commit_3yr"] == pytest.approx(rates["payg"] * 0.6), edition


def test_reused_estimator_refreshes_per_region_pair(_restore_region_constants, monkeypatch) -> None:
    """A reused CostEstimator must attempt a live refresh for EACH region pair, not once."""
    calls: list[tuple[str, str]] = []

    class _FakeLookup:
        def __init__(self, aws_region="us-east-1", bq_location="us", use_cache=True):
            calls.append((bq_location, aws_region))
        def fetch(self, gcp_client=None):
            raise RuntimeError("no network in tests")

    import bq_assess.core.price_lookup as pl
    monkeypatch.setattr(pl, "PriceLookup", _FakeLookup)
    est = CostEstimator(skip_live_pricing=False)
    est.estimate([entity()], ondemand_pricing(), slot_util(), None, 10.0, location="US")
    est.estimate([entity()], ondemand_pricing(), slot_util(), None, 10.0,
                 location="australia-southeast1")
    est.estimate([entity()], ondemand_pricing(), slot_util(), None, 10.0, location="US")
    assert ("us", "us-east-1") in calls
    assert ("australia-southeast1", "ap-southeast-2") in calls
    assert len(calls) == 2       # third call = repeat pair, no re-fetch


# --- Physical bytes storage sizing (Task 4) ---------------------------------------------------

def test_s3_storage_line_uses_physical_bytes_when_measured():
    """S3 storage line uses physical_bytes when measured=True, HIGH confidence."""
    entities = [entity(size_gb=100.0, name=f"ds.t{i}") for i in range(3)]
    for e in entities:
        e.num_bytes = int(e.size_gb * (1024 ** 3))
        e.physical_bytes = round(e.num_bytes * 0.4)  # ~2.5× compression

    est = CostEstimator(skip_live_pricing=True)
    result = est.estimate(entities, ondemand_pricing(), slot_util(), None, 10.0,
                          storage_basis="measured")
    storage = _aws("storage", result)

    assert storage.confidence == ConfidenceLevel.HIGH
    total_physical = sum(e.physical_bytes for e in entities)
    expected_gb = total_physical * k.GB_PER_BYTE
    assert expected_gb > 0
    assert "TABLE_STORAGE" in storage.source_note
    assert str(k.ASSUMED_PHYSICAL_RATIO) not in storage.source_note


def test_s3_storage_line_drops_to_medium_confidence_when_fallback():
    """S3 storage line uses MEDIUM confidence when basis=assumed (0.75× fallback)."""
    entities = [entity(size_gb=100.0, name=f"ds.t{i}") for i in range(3)]
    for e in entities:
        e.num_bytes = int(e.size_gb * (1024 ** 3))
        e.physical_bytes = round(e.num_bytes * k.ASSUMED_PHYSICAL_RATIO)

    est = CostEstimator(skip_live_pricing=True)
    result = est.estimate(entities, ondemand_pricing(), slot_util(), None, 10.0,
                          storage_basis="assumed")
    storage = _aws("storage", result)

    assert storage.confidence == ConfidenceLevel.MEDIUM
    assert str(k.ASSUMED_PHYSICAL_RATIO) in storage.source_note
    assert "TABLE_STORAGE unavailable" in storage.source_note


def test_s3_storage_line_mixed_basis():
    """S3 storage line uses MEDIUM confidence for mixed basis."""
    entities = [entity(size_gb=100.0, name=f"ds.t{i}") for i in range(3)]
    for e in entities:
        e.num_bytes = int(e.size_gb * (1024 ** 3))
        e.physical_bytes = round(e.num_bytes * k.ASSUMED_PHYSICAL_RATIO)

    est = CostEstimator(skip_live_pricing=True)
    result = est.estimate(entities, ondemand_pricing(), slot_util(), None, 10.0,
                          storage_basis="mixed")
    storage = _aws("storage", result)

    assert storage.confidence == ConfidenceLevel.MEDIUM
    assert "mixed" in storage.source_note
