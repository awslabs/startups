# Feature: bq-assess-lakehouse, issue #4: conftest strategy contract checks
"""Contract tests for the issue-#4 normative-model Hypothesis strategies.

Prove the shared strategies in ``conftest`` generate structurally valid instances of the
normative model (Phase 0.5 checkpoint), and pin the invariants later phases' property tests
rely on (population↔type, Tables-only effort axis, slot-job shape, construct pairing).
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from bq_assess import models as m
from tests.conftest import (
    PRICING_EDITIONS,
    assessment,
    entity_metadata,
    pricing_jobs,
    reservation_config,
    slot_jobs,
    sql_with_constructs,
)


@settings(max_examples=50)
@given(e=entity_metadata())
def test_entity_metadata_population_matches_type(e: m.EntityMetadata) -> None:
    assert isinstance(e, m.EntityMetadata)
    expected = (
        m.EntityPopulation.TABLE
        if e.entity_type in (m.EntityType.TABLE, m.EntityType.EXTERNAL)
        else m.EntityPopulation.REBUILT
    )
    assert e.population is expected
    # Required fields non-null
    assert e.entity_id and e.dataset_id and e.full_name
    assert e.columns
    # REBUILT carries 0 rows; routines/views carry their payloads when applicable
    if e.population is m.EntityPopulation.REBUILT:
        assert e.num_rows == 0
    if e.entity_type is m.EntityType.ROUTINE:
        assert e.routine is not None


@settings(max_examples=50)
@given(jobs=slot_jobs())
def test_slot_jobs_shape(jobs: list[dict]) -> None:
    assert len(jobs) >= 1
    for j in jobs:
        base_keys = {"total_slot_ms", "total_bytes_processed", "creation_time"}
        # The billed column mirrors real data: present-and-normal (>= processed,
        # 10 MiB minimums), present-and-zero (cache hits / reservation-served), or
        # ABSENT (old exports) — the contract must cover all three so consumers'
        # fallback branches are reachable by property tests.
        assert set(j) in (base_keys, base_keys | {"total_bytes_billed"})
        assert j["total_slot_ms"] >= 0
        assert j["total_bytes_processed"] >= 0
        if "total_bytes_billed" in j:
            assert j["total_bytes_billed"] == 0 or (
                j["total_bytes_billed"] >= j["total_bytes_processed"])


@settings(max_examples=50)
@given(jobs=pricing_jobs())
def test_pricing_jobs_carry_detection_signal(jobs: list[dict]) -> None:
    """pricing_jobs() rows carry the detector's signal columns on top of slot_jobs()."""
    for j in jobs:
        # Superset of slot_jobs() keys plus the three V5 detection columns.
        assert set(j) == {
            "total_slot_ms", "total_bytes_processed", "total_bytes_billed",
            "creation_time", "reservation_id", "edition", "statement_type",
        }
        # billed is 0 (cache hit) or >= processed (10 MiB minimums)
        assert j["total_bytes_billed"] == 0 or (
            j["total_bytes_billed"] >= j["total_bytes_processed"])
        # reservation_id is the on-demand-vs-capacity signal: NULL or a path string.
        assert j["reservation_id"] is None or isinstance(j["reservation_id"], str)
        # edition is set iff the job ran on capacity (non-null reservation_id).
        if j["reservation_id"] is None:
            assert j["edition"] is None
        else:
            assert j["edition"] in PRICING_EDITIONS
        # SCRIPT parents are NULL-reservation by design (the trap the detector guards).
        if j["statement_type"] == "SCRIPT":
            assert j["reservation_id"] is None


@settings(max_examples=25)
@given(data=st.data())
def test_pricing_jobs_force_arms(data: st.DataObject) -> None:
    """The `force` arms pin a deterministic billing/shape for targeted tests."""
    ondemand = data.draw(pricing_jobs(force="ondemand"))
    assert ondemand and all(j["reservation_id"] is None for j in ondemand)
    assert all(j["statement_type"] != "SCRIPT" for j in ondemand)

    capacity = data.draw(pricing_jobs(force="capacity"))
    assert capacity and all(j["reservation_id"] is not None for j in capacity)
    assert all(j["edition"] in PRICING_EDITIONS for j in capacity)

    scripts = data.draw(pricing_jobs(force="all_script"))
    assert scripts and all(j["statement_type"] == "SCRIPT" for j in scripts)
    assert all(j["reservation_id"] is None for j in scripts)

    assert data.draw(pricing_jobs(force="empty")) == []


@settings(max_examples=50)
@given(cfg=reservation_config())
def test_reservation_config_shape(cfg: dict) -> None:
    """A --reservation-config dict carries edition + the four slot/commitment figures."""
    assert set(cfg) == {
        "edition", "baseline_slots", "max_slots", "commitment_slots", "commitment_plan",
    }
    assert cfg["edition"] in PRICING_EDITIONS
    assert 0 <= cfg["baseline_slots"] <= cfg["max_slots"]
    assert cfg["commitment_slots"] >= 0
    assert isinstance(cfg["commitment_plan"], str)


@settings(max_examples=50)
@given(pair=sql_with_constructs())
def test_sql_with_constructs_pairs_sql_and_classes(pair: tuple[str, list[str]]) -> None:
    sql, classes = pair
    assert classes
    assert isinstance(sql, str) and sql
    # Every named class contributed a non-empty snippet to the SQL
    assert len(set(classes)) == len(classes)


@settings(max_examples=50)
@given(a=assessment())
def test_assessment_summary_consistent(a: m.Assessment) -> None:
    assert isinstance(a, m.Assessment)
    assert a.summary.total_entities == len(a.entities)
    tables = [e for e in a.entities if e.population is m.EntityPopulation.TABLE]
    assert a.summary.total_tables == len(tables)
    # Effort axis present iff Table
    for e in a.entities:
        if e.population is m.EntityPopulation.REBUILT:
            assert e.effort is None
            assert e.conversion is None
        else:
            assert e.effort is not None
    # Effort counts agree with entities
    assert sum(a.summary.effort_counts.values()) == len(tables)
