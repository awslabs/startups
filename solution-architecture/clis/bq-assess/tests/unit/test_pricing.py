# Feature: bq-assess-lakehouse, issue 5.1: PricingDetector (R16, V4/V5)
"""Unit tests for the BigQuery Pricing Detector (on-demand vs capacity / Editions).

Drives the four outcomes of ``PricingDetector.detect()`` per R16:
  1. ``--reservation-config`` supplied        → CAPACITY + figures, HIGH
  2. JOBS show a non-null ``reservation_id``   → CAPACITY + edition, MEDIUM
  3. JOBS all-NULL ``reservation_id``          → ON_DEMAND, MEDIUM (lookback caveat)
  4. no usable signal (empty / SCRIPT / perms) → ON_DEMAND, LOW, prompt for config

The detector never returns ``model == UNKNOWN`` and never raises (R16.3 / P20 honesty).
Inputs come from the ``pricing_jobs`` / ``reservation_config`` strategies (conftest).
"""

from __future__ import annotations

from datetime import datetime, timezone

from google.api_core.exceptions import Forbidden

from bq_assess.core import pricing_constants as k
from bq_assess.core.pricing import PricingDetector
from bq_assess.models import BQPricingModel, ConfidenceLevel, PricingDetection


class _FakeQueryJob:
    """Stand-in for the object returned by ``bigquery.Client.query()``."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def result(self):
        return iter(self._rows)


class _FakeClient:
    """Minimal BigQuery client double routing JOBS queries to canned rows.

    ``jobs`` are returned for any INFORMATION_SCHEMA.JOBS query; ``jobs_error`` (if set)
    is raised instead, simulating a missing ``bigquery.jobs.listAll`` permission.
    """

    def __init__(self, *, jobs: list[dict] | None = None, jobs_error: Exception | None = None) -> None:
        self._jobs = jobs if jobs is not None else []
        self._jobs_error = jobs_error
        self.queries: list[str] = []

    def query(self, sql: str, *args, **kwargs) -> _FakeQueryJob:
        self.queries.append(sql)
        if self._jobs_error is not None:
            raise self._jobs_error
        return _FakeQueryJob(self._jobs)


def _job(*, reservation_id=None, edition=None, statement_type="SELECT"):
    """Build one INFORMATION_SCHEMA.JOBS row dict for a deterministic unit test."""
    return {
        "total_slot_ms": 1000,
        "total_bytes_processed": 10**9,
        "creation_time": datetime(2025, 6, 1, tzinfo=timezone.utc),
        "reservation_id": reservation_id,
        "edition": edition,
        "statement_type": statement_type,
    }


def _detect(jobs=None, *, jobs_error=None, reservation_config=None, location="US"):
    """Run detect() against a fake client carrying *jobs* (or raising *jobs_error*)."""
    client = _FakeClient(jobs=jobs, jobs_error=jobs_error)
    return PricingDetector().detect(client, "proj", reservation_config, location=location)


# --- Outcome 3: auto on-demand --------------------------------------------------------

def test_all_ondemand_jobs_yields_on_demand_medium() -> None:
    """All leaf jobs NULL reservation_id → ON_DEMAND. MEDIUM: a 30-day sample can't prove
    a reservation never runs outside the lookback window (asymmetric-confidence policy)."""
    jobs = [_job(reservation_id=None), _job(reservation_id=None, statement_type="INSERT")]

    result = _detect(jobs)

    assert isinstance(result, PricingDetection)
    assert result.model is BQPricingModel.ON_DEMAND
    assert result.confidence is ConfidenceLevel.MEDIUM
    # On-demand carries no capacity figures.
    assert result.edition is None
    assert result.baseline_slots is None
    assert result.max_slots is None
    assert result.commitment_slots is None
    assert result.commitment_plan is None
    # Provenance names the signal + the verification date.
    assert k.V5_JOBS_RESERVATION_ID_COLUMN in result.source_note
    assert k.V5_CONFIRMED_DATE in result.source_note


# --- Outcome 2: auto capacity ---------------------------------------------------------

def test_capacity_jobs_yields_capacity_with_edition_medium() -> None:
    """A non-null reservation_id → CAPACITY; edition read from the JOBS edition column.
    MEDIUM because slot figures aren't auto-enriched in 5.1 — supply --reservation-config."""
    jobs = [
        _job(reservation_id="admin:us.resv1", edition="ENTERPRISE"),
        _job(reservation_id=None, statement_type="SELECT"),  # mixed: any_capacity wins
    ]

    result = _detect(jobs)

    assert result.model is BQPricingModel.CAPACITY
    assert result.edition == "ENTERPRISE"
    assert result.edition in k.V4_EDITION_SLOT_HOUR_USD  # priceable by the estimator (R18.2)
    assert result.confidence is ConfidenceLevel.MEDIUM
    # Figures not auto-enriched in 5.1 → None, and the note prompts for --reservation-config.
    assert result.baseline_slots is None
    assert result.max_slots is None
    assert result.commitment_slots is None
    assert "--reservation-config" in result.source_note


# --- Outcome 1: --reservation-config override ----------------------------------------

def test_reservation_config_overrides_to_capacity_with_all_figures() -> None:
    """A supplied --reservation-config is a rung above auto-detection (R16.2): CAPACITY with
    all figures at HIGH confidence, even when the jobs look on-demand."""
    cfg = {
        "edition": "ENTERPRISE_PLUS",
        "baseline_slots": 100,
        "max_slots": 500,
        "commitment_slots": 100,
        "commitment_plan": "ANNUAL",
    }
    # Jobs say on-demand; the config must still win.
    jobs = [_job(reservation_id=None), _job(reservation_id=None)]

    result = _detect(jobs, reservation_config=cfg)

    assert result.model is BQPricingModel.CAPACITY
    assert result.confidence is ConfidenceLevel.HIGH
    assert result.edition == "ENTERPRISE_PLUS"
    assert result.baseline_slots == 100
    assert result.max_slots == 500
    assert result.commitment_slots == 100
    assert result.commitment_plan == "ANNUAL"
    # Provenance marks it as manually supplied.
    assert "--reservation-config" in result.source_note


# --- Outcome 4: undeterminable → on-demand, LOW, prompt (R16.3 honesty) ---------------

def _assert_undeterminable(result: PricingDetection) -> None:
    """R16.3: undeterminable collapses to ON_DEMAND at LOW with a prompt — never UNKNOWN."""
    assert result.model is BQPricingModel.ON_DEMAND
    assert result.model is not BQPricingModel.UNKNOWN
    assert result.confidence is ConfidenceLevel.LOW
    assert result.edition is None
    assert "--reservation-config" in result.source_note


def test_empty_job_list_defaults_to_on_demand_low() -> None:
    """No jobs at all → can't determine the model → ON_DEMAND/LOW/prompt (R16.3)."""
    _assert_undeterminable(_detect([]))


def test_all_script_parents_defaults_to_on_demand_low() -> None:
    """All rows SCRIPT parents (NULL reservation_id by design) → no leaf signal → ON_DEMAND/LOW.
    Guards the trap: SCRIPT NULLs must not be read as on-demand evidence."""
    jobs = [_job(statement_type="SCRIPT", reservation_id=None) for _ in range(3)]
    _assert_undeterminable(_detect(jobs))


def test_jobs_unreadable_permission_falls_through_to_on_demand_low() -> None:
    """Missing bigquery.jobs.listAll (Forbidden) → detect() does not raise; ON_DEMAND/LOW/prompt
    (R16.3 / R17.3 graceful degradation)."""
    err = Forbidden("missing bigquery.jobs.listAll")
    _assert_undeterminable(_detect(jobs_error=err))


def test_config_with_no_jobs_still_capacity() -> None:
    """A config supplied with zero jobs still yields CAPACITY with figures (R18.4) — the
    override outranks (and short-circuits) the absent job signal."""
    cfg = {
        "edition": "ENTERPRISE",
        "baseline_slots": 50,
        "max_slots": 200,
        "commitment_slots": 0,
        "commitment_plan": "FLEX",
    }
    result = _detect([], reservation_config=cfg)
    assert result.model is BQPricingModel.CAPACITY
    assert result.baseline_slots == 50
    assert result.confidence is ConfidenceLevel.HIGH


# --- SCRIPT / mixed traps -------------------------------------------------------------

def test_script_parent_with_capacity_leaf_yields_capacity() -> None:
    """A SCRIPT parent (NULL reservation_id) plus a capacity leaf child → CAPACITY.
    Proves SCRIPT *exclusion*, not inclusion: the leaf's signal still classifies."""
    jobs = [
        _job(statement_type="SCRIPT", reservation_id=None),          # parent: NULL by design
        _job(statement_type="SELECT", reservation_id="admin:us.r1", edition="ENTERPRISE"),
    ]
    result = _detect(jobs)
    assert result.model is BQPricingModel.CAPACITY
    assert result.edition == "ENTERPRISE"


# --- Robustness: never raise (P20) ----------------------------------------------------

def test_missing_columns_on_row_do_not_raise() -> None:
    """A JOBS row missing the signal columns degrades gracefully (.get semantics), never
    KeyErrors — real INFORMATION_SCHEMA rows can omit columns."""
    jobs = [{"total_slot_ms": 1, "creation_time": None}]  # no reservation_id/edition/stmt
    result = _detect(jobs)
    assert isinstance(result, PricingDetection)
    assert result.model is not BQPricingModel.UNKNOWN  # never UNKNOWN externally


def test_malformed_partial_config_does_not_raise() -> None:
    """A --reservation-config missing keys still classifies CAPACITY; absent figures are
    None rather than raising (P20 honesty)."""
    result = _detect([], reservation_config={"edition": "ENTERPRISE"})  # only edition
    assert result.model is BQPricingModel.CAPACITY
    assert result.edition == "ENTERPRISE"
    assert result.baseline_slots is None
    assert result.max_slots is None


def test_capacity_job_with_null_edition_is_capacity_edition_none() -> None:
    """A capacity job (non-null reservation_id) whose edition column is NULL → still CAPACITY,
    but edition=None: the detector cannot invent an edition from a reservation_id alone."""
    jobs = [_job(reservation_id="admin:us.r1", edition=None)]
    result = _detect(jobs)
    assert result.model is BQPricingModel.CAPACITY
    assert result.edition is None
    assert result.confidence is ConfidenceLevel.MEDIUM


# --- Edition contradiction edge (V4) --------------------------------------------------

def test_standard_edition_with_commitment_slots_is_flagged() -> None:
    """STANDARD has no true capacity/slot commitments (V4). A config claiming STANDARD +
    commitment_slots is surfaced as a warning in source_note (not silently priced)."""
    cfg = {
        "edition": "STANDARD",
        "baseline_slots": 100,
        "max_slots": 100,
        "commitment_slots": 100,  # contradiction: STANDARD has no slot commitments
        "commitment_plan": "ANNUAL",
    }
    result = _detect([], reservation_config=cfg)
    assert result.model is BQPricingModel.CAPACITY
    assert result.edition == "STANDARD"
    assert "STANDARD" in result.source_note
    # The contradiction is named, referencing the verified no-commitment fact.
    assert "commitment" in result.source_note.lower()


# --- Region (location param) ----------------------------------------------------------

def test_location_region_qualifies_the_jobs_query() -> None:
    """The location arg region-qualifies the INFORMATION_SCHEMA.JOBS query (e.g. region-eu)."""
    client = _FakeClient(jobs=[_job(reservation_id=None)])
    PricingDetector().detect(client, "proj", None, location="EU")
    assert client.queries
    assert "`region-eu`.INFORMATION_SCHEMA.JOBS" in client.queries[0]


# --- Provenance + R18.7 overridability ------------------------------------------------

def test_constants_are_sourced_not_inlined(monkeypatch) -> None:
    """Overriding the SCRIPT-statement constant changes which rows are excluded — proving the
    detector reads pricing_constants at call time, not a hardcoded 'SCRIPT' (R18.7)."""
    # Re-label the SCRIPT sentinel; a row carrying the new sentinel must now be excluded.
    monkeypatch.setattr(k, "V5_JOBS_SCRIPT_STATEMENT_TYPE", "SENTINEL_SCRIPT")
    jobs = [_job(statement_type="SENTINEL_SCRIPT", reservation_id=None)]
    result = _detect(jobs)
    # With the override, the only row is treated as a SCRIPT parent → no leaf signal → LOW.
    assert result.confidence is ConfidenceLevel.LOW


# --- Grouped reservation rows (2026-07-08 storm audit: bounded-rows JOBS read) ----------

def test_detector_sql_is_grouped() -> None:
    """The JOBS read GROUPs BY reservation/edition server-side — a handful of rows
    regardless of the Source's query volume."""
    client = _FakeClient(jobs=[])
    PricingDetector().detect(client, "proj", None, location="US")
    sql = client.queries[0]
    assert "GROUP BY reservation_id, edition" in sql
    assert "COUNT(*)" in sql


def test_grouped_capacity_rows_classify_with_true_job_counts() -> None:
    """Grouped rows carry job_count — the source_note quotes real job totals, not group counts."""
    groups = [
        {"reservation_id": None, "edition": None, "job_count": 9_000},
        {"reservation_id": "proj:US.res1", "edition": "ENTERPRISE", "job_count": 1_000},
    ]
    detection = _detect(groups)
    assert detection.model == BQPricingModel.CAPACITY
    assert detection.edition == "ENTERPRISE"
    assert "1000 of 10000" in detection.source_note.replace(",", "")


def test_grouped_all_null_reservation_is_on_demand() -> None:
    groups = [{"reservation_id": None, "edition": None, "job_count": 42}]
    detection = _detect(groups)
    assert detection.model == BQPricingModel.ON_DEMAND
    assert detection.confidence == ConfidenceLevel.MEDIUM
    assert "42" in detection.source_note
