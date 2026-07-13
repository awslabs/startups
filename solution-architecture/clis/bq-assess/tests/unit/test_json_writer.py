"""Unit tests for report/json_writer.py — three mirrored JSON files (R19)."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone

from bq_assess.models import (
    Assessment, AssessmentSummary, BQPricingModel, ConfidenceLevel,
    CostComparison, CostLine, EntityPopulation, EntityReport, EntityType,
    EffortCategory, EffortResult, ComplexityCategory, ComplexityResult,
    ConfidenceSource, ConversionResult,
)
from bq_assess.report.json_writer import JSONWriter


def _known_assessment():
    """A deterministic Assessment for schema validation."""
    entities = [
        EntityReport(
            full_name="ds.orders", entity_type=EntityType.TABLE,
            population=EntityPopulation.TABLE, rows=1_000_000, size_gb=42.5,
            depends_on=[],
            effort=EffortResult(category=EffortCategory.ASSISTED, score=45, flags=["time_partitioning"], reasoning="has partitions", confidence=ConfidenceLevel.HIGH),
            conversion=ConversionResult(ddl="CREATE TABLE ds.orders (id long);", partition_mapping=None, lossy_casts=[], warnings=[], success=True),
            load_sync_dml="COPY INTO ds.orders FROM 's3://...'",
            complexity=ComplexityResult(category=ComplexityCategory.ADAPT, score=60, constructs=[], flags=["UNNEST"], reasoning="uses UNNEST", confidence=ConfidenceLevel.MEDIUM, confidence_source=ConfidenceSource.QUERY_LOGS),
            rewrite_guidance=["Replace UNNEST with SUPER type navigation"],
            placement=None,
        ),
        EntityReport(
            full_name="ds.active_users_v", entity_type=EntityType.VIEW,
            population=EntityPopulation.REBUILT, rows=0, size_gb=0.0,
            depends_on=["ds.orders"],
            effort=None, conversion=None, load_sync_dml=None,
            complexity=ComplexityResult(category=ComplexityCategory.REWRITE, score=80, constructs=[], flags=["JS_UDF"], reasoning="JS UDF", confidence=ConfidenceLevel.LOW, confidence_source=ConfidenceSource.VIEW_DEFINITION),
            rewrite_guidance=["Rewrite JS UDF to SQL"],
            placement=None,
        ),
    ]
    return Assessment(
        assessment_id="assess-20260617-abc123",
        generated_at=datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc),
        project_id="my-project",
        summary=AssessmentSummary(
            total_entities=2, total_tables=1, total_size_gb=42.5,
            effort_counts={"AUTO": 0, "ASSISTED": 1, "MANUAL": 0},
            complexity_counts={"PORTABLE": 0, "ADAPT": 1, "REWRITE": 1},
            sql_surface_confidence=ConfidenceLevel.HIGH,
        ),
        cost=CostComparison(
            bq_pricing_model=BQPricingModel.CAPACITY, bigquery_monthly=105000.0,
            bigquery_breakdown=[CostLine(label="BigQuery capacity (ENTERPRISE)", monthly=105000.0, monthly_low=None, monthly_high=None, confidence=ConfidenceLevel.HIGH, source_note="V4 ENTERPRISE")],
            aws_lines=[
                CostLine(label="S3 Tables storage", monthly=50.0, monthly_low=None, monthly_high=None, confidence=ConfidenceLevel.HIGH, source_note="V2"),
                CostLine(label="Redshift Serverless compute", monthly=26200.0, monthly_low=None, monthly_high=None, confidence=ConfidenceLevel.MEDIUM, source_note="V1 via V3"),
            ],
            aws_monthly_low=26250.0, aws_monthly_high=26250.0,
            monthly_delta_low=78750.0, monthly_delta_high=78750.0,
            annual_savings_low=945000.0, annual_savings_high=945000.0,
            migration_onetime=15000.0, breakeven_months_low=0.19, breakeven_months_high=0.19,
            compute_confidence=ConfidenceLevel.MEDIUM,
        ),
        entities=entities, failures=[],
    )


def test_json_writer_produces_three_files():
    a = _known_assessment()
    out = tempfile.mkdtemp()
    paths = JSONWriter().write(a, out)
    assert len(paths) == 3
    assert all(p.endswith(".json") for p in paths)


def test_json_landing_schema():
    a = _known_assessment()
    out = tempfile.mkdtemp()
    paths = JSONWriter().write(a, out)
    landing_path = [p for p in paths if "landing" in p][0]
    with open(landing_path) as f:
        data = json.load(f)
    for key in ["assessment_id", "generated_at", "project_id", "summary", "cost", "failures"]:
        assert key in data
    assert data["assessment_id"] == "assess-20260617-abc123"
    assert data["summary"]["total_entities"] == 2


def test_json_effort_tables_only():
    a = _known_assessment()
    out = tempfile.mkdtemp()
    paths = JSONWriter().write(a, out)
    effort_path = [p for p in paths if "effort" in p][0]
    with open(effort_path) as f:
        data = json.load(f)
    assert data["assessment_id"] == "assess-20260617-abc123"
    assert len(data["entities"]) == 1
    assert data["entities"][0]["full_name"] == "ds.orders"
    assert data["entities"][0]["population"] == "TABLE"


def test_json_query_includes_rebuilt():
    a = _known_assessment()
    out = tempfile.mkdtemp()
    paths = JSONWriter().write(a, out)
    query_path = [p for p in paths if "query" in p][0]
    with open(query_path) as f:
        data = json.load(f)
    assert len(data["entities"]) == 2
    names = {e["full_name"] for e in data["entities"]}
    assert names == {"ds.orders", "ds.active_users_v"}


def test_json_crossref_by_full_name():
    a = _known_assessment()
    out = tempfile.mkdtemp()
    paths = JSONWriter().write(a, out)
    all_names = set()
    for p in paths:
        with open(p) as f:
            data = json.load(f)
        if "entities" in data:
            for e in data["entities"]:
                all_names.add(e["full_name"])
    expected = {e.full_name for e in a.entities}
    assert all_names == expected


def test_json_none_fields_omitted():
    a = _known_assessment()
    out = tempfile.mkdtemp()
    paths = JSONWriter().write(a, out)
    query_path = [p for p in paths if "query" in p][0]
    with open(query_path) as f:
        data = json.load(f)
    view_entity = [e for e in data["entities"] if e["full_name"] == "ds.active_users_v"][0]
    assert "effort" not in view_entity
    assert "conversion" not in view_entity
    assert "load_sync_dml" not in view_entity


def test_json_enum_serialized_as_value():
    a = _known_assessment()
    out = tempfile.mkdtemp()
    paths = JSONWriter().write(a, out)
    landing_path = [p for p in paths if "landing" in p][0]
    with open(landing_path) as f:
        data = json.load(f)
    assert data["cost"]["bq_pricing_model"] == "CAPACITY"
    assert data["cost"]["compute_confidence"] == "MEDIUM"
