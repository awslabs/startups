"""Unit tests for report/html_writer.py — single combined HTML report (R20)."""
from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone

from bq_assess.models import (
    Assessment,
    AssessmentSummary,
    BQPricingModel,
    ConfidenceLevel,
    ConfidenceSource,
    ComplexityCategory,
    ComplexityResult,
    ConversionResult,
    CostComparison,
    CostLine,
    EffortCategory,
    EffortResult,
    EntityPopulation,
    EntityReport,
    EntityType,
)
from bq_assess.report.html_writer import HTMLWriter


def _known_assessment(
    compute_confidence=ConfidenceLevel.HIGH, sql_confidence=ConfidenceLevel.HIGH
):
    entities = [
        EntityReport(
            full_name="ds.orders",
            entity_type=EntityType.TABLE,
            population=EntityPopulation.TABLE,
            rows=1_000_000,
            size_gb=42.5,
            depends_on=[],
            effort=EffortResult(
                category=EffortCategory.ASSISTED,
                score=45,
                flags=["time_partitioning"],
                reasoning="partitioned",
                confidence=ConfidenceLevel.HIGH,
            ),
            conversion=ConversionResult(
                ddl="CREATE TABLE ds.orders (id long);",
                partition_mapping=None,
                lossy_casts=[],
                warnings=[],
                success=True,
            ),
            load_sync_dml="COPY INTO ds.orders FROM 's3://bucket'",
            complexity=ComplexityResult(
                category=ComplexityCategory.ADAPT,
                score=60,
                constructs=[],
                flags=["UNNEST"],
                reasoning="uses UNNEST",
                confidence=ConfidenceLevel.MEDIUM,
                confidence_source=ConfidenceSource.QUERY_LOGS,
            ),
            rewrite_guidance=["Replace UNNEST"],
            placement=None,
        ),
        EntityReport(
            full_name="ds.view1",
            entity_type=EntityType.VIEW,
            population=EntityPopulation.REBUILT,
            rows=0,
            size_gb=0.0,
            depends_on=["ds.orders"],
            effort=None,
            conversion=None,
            load_sync_dml=None,
            complexity=ComplexityResult(
                category=ComplexityCategory.REWRITE,
                score=80,
                constructs=[],
                flags=["JS_UDF"],
                reasoning="JS",
                confidence=ConfidenceLevel.LOW,
                confidence_source=ConfidenceSource.VIEW_DEFINITION,
            ),
            rewrite_guidance=["Rewrite JS UDF"],
            placement=None,
        ),
    ]
    return Assessment(
        assessment_id="assess-20260617-abc123",
        generated_at=datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc),
        project_id="my-project",
        summary=AssessmentSummary(
            total_entities=2,
            total_tables=1,
            total_size_gb=42.5,
            effort_counts={"AUTO": 0, "ASSISTED": 1, "MANUAL": 0},
            complexity_counts={"PORTABLE": 0, "ADAPT": 1, "REWRITE": 1},
            sql_surface_confidence=sql_confidence,
        ),
        cost=CostComparison(
            bq_pricing_model=BQPricingModel.CAPACITY,
            bigquery_monthly=105000.0,
            bigquery_breakdown=[
                CostLine(
                    label="BQ cap",
                    monthly=105000.0,
                    monthly_low=None,
                    monthly_high=None,
                    confidence=ConfidenceLevel.HIGH,
                    source_note="V4",
                )
            ],
            aws_lines=[
                CostLine(
                    label="S3",
                    monthly=50.0,
                    monthly_low=None,
                    monthly_high=None,
                    confidence=ConfidenceLevel.HIGH,
                    source_note="V2",
                )
            ],
            aws_monthly_low=26250.0,
            aws_monthly_high=26250.0,
            monthly_delta_low=78750.0,
            monthly_delta_high=78750.0,
            annual_savings_low=945000.0,
            annual_savings_high=945000.0,
            migration_onetime=15000.0,
            breakeven_months_low=0.19,
            breakeven_months_high=0.19,
            compute_confidence=compute_confidence,
        ),
        entities=entities,
        failures=[],
    )


def test_html_renders_single_file():
    a = _known_assessment()
    out = tempfile.mkdtemp()
    paths = HTMLWriter().write(a, out)
    assert len(paths) == 1
    assert paths[0].endswith(".html")
    assert os.path.exists(paths[0])
    assert os.path.basename(paths[0]) == "my-project-assessment.html"


def test_html_contains_all_tabs():
    a = _known_assessment()
    out = tempfile.mkdtemp()
    paths = HTMLWriter().write(a, out)
    with open(paths[0]) as f:
        html = f.read()
    assert 'id="tab-landing"' in html
    assert 'id="tab-effort"' in html
    assert 'id="tab-query"' in html


def test_html_offline_no_external_urls():
    a = _known_assessment()
    out = tempfile.mkdtemp()
    paths = HTMLWriter().write(a, out)
    with open(paths[0]) as f:
        html = f.read()
    assert "http://" not in html
    assert "https://" not in html


def test_html_low_confidence_banner_compute():
    a = _known_assessment(compute_confidence=ConfidenceLevel.LOW)
    out = tempfile.mkdtemp()
    paths = HTMLWriter().write(a, out)
    with open(paths[0]) as f:
        html = f.read()
    assert "Low Confidence Cost Estimate" in html


def test_html_low_confidence_banner_sql_surface():
    a = _known_assessment(sql_confidence=ConfidenceLevel.LOW)
    out = tempfile.mkdtemp()
    paths = HTMLWriter().write(a, out)
    with open(paths[0]) as f:
        html = f.read()
    assert "Low Confidence SQL Analysis" in html


def test_html_no_csv_emitted():
    a = _known_assessment()
    out = tempfile.mkdtemp()
    HTMLWriter().write(a, out)
    files = os.listdir(out)
    assert not any(f.endswith(".csv") for f in files)


def test_html_mobile_viewport():
    a = _known_assessment()
    out = tempfile.mkdtemp()
    paths = HTMLWriter().write(a, out)
    with open(paths[0]) as f:
        html = f.read()
    assert 'name="viewport"' in html
    assert "@media (max-width: 768px)" in html


def test_html_storage_basis_measured():
    """When storage_basis='measured', template receives correct basis."""
    a = _known_assessment()
    out = tempfile.mkdtemp()
    paths = HTMLWriter().write(a, out, storage_basis="measured")
    with open(paths[0]) as f:
        html = f.read()
    # The template's conditional text for measured storage
    assert "measured physical bytes" in html.lower()


def test_html_storage_basis_assumed():
    """When storage_basis='assumed' (default), template interpolates physical_ratio."""
    from bq_assess.engine.redshift import cost_constants as k
    a = _known_assessment()
    out = tempfile.mkdtemp()
    paths = HTMLWriter().write(a, out, storage_basis="assumed")
    with open(paths[0]) as f:
        html = f.read()
    # The template's conditional text for assumed storage — should have interpolated ratio
    assert str(k.ASSUMED_PHYSICAL_RATIO) in html


def _render_html(assessment) -> str:
    out = tempfile.mkdtemp()
    paths = HTMLWriter().write(assessment, out)
    with open(paths[0]) as f:
        return f.read()


def test_html_has_csp_with_script_nonce():
    """The report ships a CSP that only allows the nonce'd inline script (no unsafe-inline)."""
    html = _render_html(_known_assessment())
    m = re.search(r"script-src 'nonce-([A-Za-z0-9_-]+)'", html)
    assert m, "CSP header missing a script nonce"
    nonce = m.group(1)
    # The one legitimate inline <script> must carry the matching nonce...
    assert f'<script nonce="{nonce}">' in html
    # ...and there must be NO bare <script> that a compliant browser would run.
    assert "<script>" not in html
    # unsafe-inline for scripts would defeat the whole point.
    assert "'unsafe-inline'" not in re.search(r"script-src[^;]*", html).group(0)


def test_html_csp_nonce_is_per_render():
    """Each rendered file gets a fresh, unguessable nonce (never a fixed constant)."""
    h1 = _render_html(_known_assessment())
    h2 = _render_html(_known_assessment())
    n1 = re.search(r"script-src 'nonce-([A-Za-z0-9_-]+)'", h1).group(1)
    n2 = re.search(r"script-src 'nonce-([A-Za-z0-9_-]+)'", h2).group(1)
    assert n1 != n2
    assert len(n1) >= 16


def test_html_malicious_identifier_is_neutralized():
    """A BigQuery identifier attempting <code> breakout + <script> injection is escaped.

    Regression for the storm-aws deep-audit XSS finding: DDL/DML rendered from
    attacker-controlled entity names must never produce an executable <script>.
    """
    a = _known_assessment()
    payload = "ds.evil</code><script>alert(document.domain)</script><code>t"
    a.entities[0].full_name = payload
    a.entities[0].conversion.ddl = f"CREATE TABLE {payload} (id long);"
    a.entities[0].load_sync_dml = f"INSERT INTO {payload} SELECT * FROM src;"
    html = _render_html(a)
    # The raw injected script must not survive as executable markup anywhere —
    # entity data now ships inside a JSON data block, where Jinja's |tojson
    # escapes `<` as \\u003c so the payload can never close the block or form a tag.
    assert "<script>alert(document.domain)</script>" not in html
    assert "</code><script>" not in html
    assert "\\u003cscript\\u003ealert(document.domain)\\u003c/script\\u003e" in html
    # And the only executable <script> tag is still the nonce'd one.
    assert "<script>" not in html
    # The client-side renderer must insert entity data as text, never as markup.
    assert "innerHTML" not in html


