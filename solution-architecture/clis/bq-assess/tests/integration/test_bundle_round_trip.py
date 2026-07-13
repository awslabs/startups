# Feature: collector/report split (2026-07-08 design) — anti-drift guarantee
"""Round-trip equivalence: analyze_and_report on an in-memory Bundle vs. the same
Bundle after write → load produces the same Assessment (modulo id/timestamp).

This is THE invariant that lets us generate a customer's report from their bundle
and trust it matches what a direct in-environment run would have produced. It also
covers spec test 7 (assess-emits-bundle self round-trip): the bundle written by an
assess run is accepted by `report` and reproduces the Assessment.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from bq_assess.bundle import Bundle, BundleLoader, BundleWriter
from bq_assess.bundle.models import QueryRecord
from bq_assess.cli import analyze_and_report
from bq_assess.models import (
    BQPricingModel,
    ColumnSchema,
    ConfidenceLevel,
    EntityMetadata,
    EntityPopulation,
    EntityType,
    FailureRecord,
    PricingDetection,
    RoutineMetadata,
    SlotUtilization,
    TimePartitionConfig,
)


def _fixture_entities() -> list[EntityMetadata]:
    """A small project: partitioned table, plain table, view, routine."""
    ts = datetime(2026, 1, 15, tzinfo=timezone.utc)
    return [
        EntityMetadata(
            entity_id="events", dataset_id="analytics", full_name="analytics.events",
            entity_type=EntityType.TABLE, population=EntityPopulation.TABLE,
            num_rows=1_000_000, num_bytes=5 * 1024**3,
            columns=[
                ColumnSchema("event_id", "STRING", "REQUIRED", []),
                ColumnSchema("user_id", "STRING", "NULLABLE", []),
                ColumnSchema("event_date", "DATE", "NULLABLE", []),
                ColumnSchema("payload", "RECORD", "NULLABLE", [
                    ColumnSchema("kind", "STRING", "NULLABLE", []),
                    ColumnSchema("value", "FLOAT64", "NULLABLE", []),
                ]),
            ],
            time_partitioning=TimePartitionConfig(type="DAY", field="event_date"),
            range_partitioning=None,
            clustering_fields=["user_id"],
            view_query=None, mview_query=None, routine=None,
            depends_on=[], last_modified=ts, physical_bytes=2 * 1024**3,
        ),
        EntityMetadata(
            entity_id="users", dataset_id="analytics", full_name="analytics.users",
            entity_type=EntityType.TABLE, population=EntityPopulation.TABLE,
            num_rows=50_000, num_bytes=256 * 1024**2,
            columns=[
                ColumnSchema("user_id", "STRING", "REQUIRED", []),
                ColumnSchema("signup_date", "DATE", "NULLABLE", []),
            ],
            time_partitioning=None, range_partitioning=None, clustering_fields=None,
            view_query=None, mview_query=None, routine=None,
            depends_on=[], last_modified=ts, physical_bytes=100 * 1024**2,
        ),
        EntityMetadata(
            entity_id="daily_summary", dataset_id="analytics",
            full_name="analytics.daily_summary",
            entity_type=EntityType.VIEW, population=EntityPopulation.REBUILT,
            num_rows=0, num_bytes=0,
            columns=[ColumnSchema("day", "DATE", "NULLABLE", [])],
            time_partitioning=None, range_partitioning=None, clustering_fields=None,
            view_query=(
                "SELECT e.event_date AS day, COUNT(*) AS n FROM analytics.events e "
                "JOIN analytics.users u ON e.user_id = u.user_id GROUP BY 1"
            ),
            mview_query=None, routine=None,
            depends_on=["analytics.events", "analytics.users"],
            last_modified=ts, physical_bytes=0,
        ),
        EntityMetadata(
            entity_id="clean_str", dataset_id="analytics", full_name="analytics.clean_str",
            entity_type=EntityType.ROUTINE, population=EntityPopulation.REBUILT,
            num_rows=0, num_bytes=0, columns=[],
            time_partitioning=None, range_partitioning=None, clustering_fields=None,
            view_query=None, mview_query=None,
            routine=RoutineMetadata(
                name="clean_str", language="SQL", arguments=["s STRING"],
                body="TRIM(LOWER(s))", routine_type="SCALAR_FUNCTION",
            ),
            depends_on=[], last_modified=ts, physical_bytes=0,
        ),
    ]


def _fixture_bundle() -> Bundle:
    return Bundle(
        project_id="fixture-project",
        bq_location="australia-southeast1",
        aws_region="ap-southeast-2",
        entities=_fixture_entities(),
        failures=[FailureRecord(entity_name="analytics.broken", stage="scan", error="403")],
        workload=SlotUtilization(
            avg_slots=12.0, p50_slots=9.0, p99_slots=45.0, peak_slots=60.0,
            active_hour_fraction=0.35, total_slot_ms=100_000_000, days_sampled=20,
            total_bytes_processed=8 * 10**12, total_bytes_billed=7 * 10**12,
            has_billed_bytes=True, total_queries=3400, lookback_days=30,
        ),
        pricing=PricingDetection(
            model=BQPricingModel.ON_DEMAND,
            confidence=ConfidenceLevel.HIGH,
            source_note="fixture",
        ),
        rates=None,  # hardcoded region-cascaded rates on both sides — deterministic
        queries=[
            QueryRecord(
                query="SELECT event_id FROM analytics.events WHERE event_date > '?'",
                total_slot_ms=50_000, total_bytes_processed=10**10,
                total_bytes_billed=10**10, statement_type="SELECT",
                creation_time="2026-07-01T10:00:00+00:00",
            ),
        ],
        storage_basis="measured",
        collector_version="0.3.0",
        created_at="2026-07-08T00:00:00+00:00",
    )


def _normalize(assessment) -> dict:
    """Assessment as a dict with the run-specific fields (id, timestamp) removed."""
    d = dataclasses.asdict(assessment)
    d.pop("assessment_id")
    d.pop("generated_at")
    return d


@pytest.fixture()
def report_params(tmp_path):
    def _params(subdir: str) -> dict:
        out = tmp_path / subdir
        out.mkdir()
        return {
            "output": str(out),
            "format": "json,html",
            "export_bundle": False,
            "skip_translation": True,  # deterministic + fast
        }
    return _params


class TestBundleRoundTripEquivalence:
    def test_in_memory_vs_written_bundle_same_assessment(self, tmp_path, report_params) -> None:
        """analyze_and_report(bundle) == analyze_and_report(load(write(bundle)))."""
        direct = analyze_and_report(_fixture_bundle(), report_params("direct"))

        bundle_dir = BundleWriter().write(_fixture_bundle(), str(tmp_path / "handoff"))
        loaded = BundleLoader().load(bundle_dir)
        via_disk = analyze_and_report(loaded, report_params("via-disk"))

        assert _normalize(direct) == _normalize(via_disk)

    def test_assess_emitted_bundle_is_reportable(self, tmp_path, report_params) -> None:
        """Spec test 7: the bundle an assess run writes (export_bundle=True) loads
        and reproduces the same Assessment."""
        params = report_params("assess-run")
        params["export_bundle"] = True
        direct = analyze_and_report(_fixture_bundle(), params)

        emitted = str(tmp_path / "assess-run" / "bundle")
        loaded = BundleLoader().load(emitted)
        rerun = analyze_and_report(loaded, report_params("rerun"))

        assert _normalize(direct) == _normalize(rerun)

    def test_report_outputs_written(self, tmp_path, report_params) -> None:
        """The report side writes HTML + 3 JSON files from a loaded bundle."""
        bundle_dir = BundleWriter().write(_fixture_bundle(), str(tmp_path / "b"))
        loaded = BundleLoader().load(bundle_dir)
        params = report_params("out")
        analyze_and_report(loaded, params)

        out = tmp_path / "out"
        files = {p.name for p in out.iterdir()}
        assert any(f.endswith("-assessment.html") for f in files)
        assert any(f.startswith("assessment-landing-") for f in files)
        assert any(f.startswith("assessment-effort-") for f in files)
        assert any(f.startswith("assessment-query-") for f in files)

    def test_html_report_carries_disclaimer(self, tmp_path, report_params) -> None:
        """Spec test 6: the HTML footer contains the beta/legal block."""
        params = report_params("disc")
        analyze_and_report(_fixture_bundle(), params)

        html_files = list((tmp_path / "disc").glob("*-assessment.html"))
        assert html_files, "no HTML report written"
        html = html_files[0].read_text(encoding="utf-8")
        assert "Beta &amp; Disclaimer Notice" in html
        assert "not a quote, offer, or commitment" in html
        assert "AS IS" in html

    def test_view_definitions_flow_into_relationships(self, report_params) -> None:
        """The Stage 6 wiring fix: view JOIN clauses produce relationships, which
        surface as REBUILT placement signals downstream."""
        assessment = analyze_and_report(_fixture_bundle(), report_params("rels"))

        view_report = next(
            e for e in assessment.entities if e.full_name == "analytics.daily_summary"
        )
        assert view_report.placement is not None

    def test_region_replay_prices_in_bundle_geography(self, report_params) -> None:
        """Spec test 5: an australia-southeast1 bundle prices AWS in ap-southeast-2,
        not the us-east-1 default — region provenance survives the hand-off."""
        assessment = analyze_and_report(_fixture_bundle(), report_params("region"))

        assert assessment.cost.aws_pricing_region == "ap-southeast-2"
        assert assessment.cost.bq_pricing_region.lower() == "australia-southeast1"
