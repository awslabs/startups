"""Unit tests for report/templates/combined.html.j2 — template source validation."""
from __future__ import annotations

from pathlib import Path


TEMPLATES = Path(__file__).parent.parent.parent / "src" / "bq_assess" / "report" / "templates"


def test_storage_assumptions_conditional_exists():
    """Storage Assumptions section has storage_basis == 'measured' conditional."""
    raw = (TEMPLATES / "combined.html.j2").read_text()
    assert 'storage_basis == "measured"' in raw
    assert "Storage Assumptions" in raw


def test_storage_assumptions_measured_content():
    """When storage_basis='measured', assumptions mention TABLE_STORAGE."""
    raw = (TEMPLATES / "combined.html.j2").read_text()
    assert "TABLE_STORAGE" in raw
    assert "measured physical bytes" in raw


def test_storage_assumptions_fallback_content():
    """When storage_basis != 'measured', assumptions interpolate pricing.physical_ratio."""
    raw = (TEMPLATES / "combined.html.j2").read_text()
    assert "pricing.physical_ratio" in raw
    assert "Parquet compression" in raw


def test_total_size_stat_shows_both_bases():
    """Total Size card shows BigQuery logical headline plus projected S3 size with a basis tooltip."""
    raw = (TEMPLATES / "combined.html.j2").read_text()
    assert "Total Size" in raw
    assert "summary.total_logical_size_gb" in raw   # headline = customer's console number
    assert "summary.total_size_gb" in raw           # secondary = projected S3 footprint
    assert "on S3 Iceberg" in raw
    assert "matches your BigQuery console" in raw   # tooltip explains both numbers


def test_entity_size_has_reconciliation_tooltip():
    """Per-entity size column has reconciliation tooltip showing logical vs physical.

    Entity rows render client-side, so the tooltip is built by the report's JS
    renderer rather than a Jinja data-tip attribute.
    """
    raw = (TEMPLATES / "combined.html.j2").read_text()
    # The physical_size_gb rendering should have a tooltip showing logical_size_gb
    assert "e.physical_size_gb" in raw
    assert "e.logical_size_gb" in raw
    assert "'BigQuery logical: '" in raw
