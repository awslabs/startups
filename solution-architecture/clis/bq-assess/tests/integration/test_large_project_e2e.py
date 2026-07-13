"""Component integration stress test: 50,000 entities through scoring + reports.

Simulates a large customer environment (like montu-au-raw-prod with 25k+ entities)
at double scale to verify the pipeline stages complete without hanging or OOM.

Key regressions this catches:
- Relationship inference cap (100k hard limit prevents combinatorial explosion)
- Complexity scoring performance with large relationship graphs
- Report generation for very large HTML/JSON outputs
- Cache round-trip at scale

NOTE: This test sequences stages manually (not via the CLI pipeline) to isolate
component performance from network I/O. It validates that each stage handles 50k
entities within time bounds, NOT that the CLI wires stages correctly.

A separate smaller test validates the mocked scanner + connection pool path.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from google.cloud import bigquery

from bq_assess.core.cache import MetadataCache
from bq_assess.core.relationships import RelationshipInferrer
from bq_assess.core.scanner import BigQueryScanner
from bq_assess.core.sql_surface import SQLSurfaceAnalyzer
from bq_assess.engine.redshift.rewrite import RewriteGuide
from bq_assess.models import (
    Assessment,
    AssessmentSummary,
    BQPricingModel,
    ColumnSchema,
    ComplexityCategory,
    ComplexityResult,
    ConfidenceLevel,
    ConfidenceSource,
    ConversionResult,
    CostComparison,
    CostLine,
    EntityMetadata,
    EntityPopulation,
    EntityReport,
    EntityType,
    RoutineMetadata,
)
from bq_assess.report.html_writer import HTMLWriter
from bq_assess.report.json_writer import JSONWriter
from bq_assess.scoring.complexity import ComplexityScorer
from bq_assess.scoring.effort import EffortScorer
from bq_assess.targets.iceberg.converter import IcebergConverter

NUM_TABLES = 49_700
NUM_VIEWS = 250
NUM_ROUTINES = 50
TOTAL_ENTITIES = NUM_TABLES + NUM_VIEWS + NUM_ROUTINES
NUM_SHARED_ID_COLUMNS = 300

PIPELINE_TIMEOUT_SECONDS = 60


@pytest.fixture(scope="module")
def entities_50k():
    """Build 50,000 EntityMetadata objects mimicking a large BQ project.

    Tables share overlapping _id columns via a sliding window (10 columns per table,
    300 total). This produces enough column co-occurrence to trigger the relationship
    inferrer's combinatorial path and validate that the 100k hard cap holds.
    """
    now = datetime.now(timezone.utc)
    id_columns = [f"entity_{i}_id" for i in range(NUM_SHARED_ID_COLUMNS)]

    tables = []
    for i in range(NUM_TABLES):
        start = i % (NUM_SHARED_ID_COLUMNS - 10)
        cols = [
            ColumnSchema(name=id_columns[j], field_type="STRING", mode="NULLABLE")
            for j in range(start, start + 10)
        ]
        cols.append(ColumnSchema(name="created_at", field_type="TIMESTAMP", mode="NULLABLE"))
        tables.append(EntityMetadata(
            entity_id=f"table_{i}",
            dataset_id=f"ds_{i // 500}",
            full_name=f"ds_{i // 500}.table_{i}",
            entity_type=EntityType.TABLE,
            population=EntityPopulation.TABLE,
            num_rows=10_000 + (i * 7 % 1_000_000),
            num_bytes=1_000_000 + (i * 13 % 100_000_000),
            columns=cols,
            time_partitioning=None,
            range_partitioning=None,
            clustering_fields=["created_at"] if i % 5 == 0 else None,
            view_query=None,
            mview_query=None,
            routine=None,
            depends_on=[],
            last_modified=now,
        ))

    views = []
    for i in range(NUM_VIEWS):
        sql = (
            f"SELECT t1.entity_{i % 50}_id FROM ds_0.table_{i} t1 "
            f"JOIN ds_1.table_{i + 500} t2 "
            f"ON t1.entity_{i % 50}_id = t2.entity_{i % 50}_id "
            f"WHERE t1.created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)"
        )
        views.append(EntityMetadata(
            entity_id=f"view_{i}",
            dataset_id="analytics",
            full_name=f"analytics.view_{i}",
            entity_type=EntityType.VIEW,
            population=EntityPopulation.REBUILT,
            num_rows=0,
            num_bytes=0,
            columns=[ColumnSchema(name="id", field_type="STRING", mode="NULLABLE")],
            time_partitioning=None,
            range_partitioning=None,
            clustering_fields=None,
            view_query=sql,
            mview_query=None,
            routine=None,
            depends_on=[],
            last_modified=now,
        ))

    routines = []
    for i in range(NUM_ROUTINES):
        body = (
            f"BEGIN DECLARE v INT64; "
            f"SET v = (SELECT COUNT(*) FROM ds_0.table_{i}); "
            f"EXCEPTION WHEN ERROR THEN SELECT @@error.message; END;"
        )
        routines.append(EntityMetadata(
            entity_id=f"proc_{i}",
            dataset_id="ops",
            full_name=f"ops.proc_{i}",
            entity_type=EntityType.ROUTINE,
            population=EntityPopulation.REBUILT,
            num_rows=0,
            num_bytes=0,
            columns=[],
            time_partitioning=None,
            range_partitioning=None,
            clustering_fields=None,
            view_query=None,
            mview_query=None,
            routine=RoutineMetadata(
                name=f"proc_{i}", language="SQL", arguments=[], body=body, routine_type="PROCEDURE"
            ),
            depends_on=[],
            last_modified=now,
        ))

    return tables + views + routines


class TestLargeProjectPipeline:
    """Component integration: relationships → scoring → translation → reports at 50k scale."""

    def test_entity_count(self, entities_50k):
        """Fixture produces exactly 50,000 entities."""
        assert len(entities_50k) == TOTAL_ENTITIES

    def test_relationship_inference_capped(self, entities_50k):
        """Relationship inference stays under 100k with 300 shared _id columns."""
        tables = [e for e in entities_50k if e.population == EntityPopulation.TABLE]

        t0 = time.time()
        result = RelationshipInferrer().infer(tables)
        elapsed = time.time() - t0

        assert len(result.relationships) <= 100_000
        assert len(result.relationships) > 0
        assert elapsed < 5.0, f"Relationship inference took {elapsed:.1f}s (limit: 5s)"
        assert len(result.likely_join_keys) > 0

    def test_full_pipeline_completes(self, entities_50k, tmp_path):
        """All pipeline components (scoring, conversion, reports) handle 50k entities under 60s."""
        t_start = time.time()
        tables = [e for e in entities_50k if e.population == EntityPopulation.TABLE]

        # Stage 3: SQL surface analysis
        analyzer = SQLSurfaceAnalyzer()
        all_constructs = {}
        for e in entities_50k:
            sql = e.view_query or e.mview_query or (e.routine.body if e.routine else None)
            if sql:
                c = analyzer.detect(sql)
                if c:
                    all_constructs[e.full_name] = c

        # Stage 4: Iceberg conversion
        converter = IcebergConverter()
        conversions = {}
        for e in tables:
            conversions[e.full_name] = converter.convert(e)

        # Stage 5: Effort scoring
        effort_scorer = EffortScorer()
        dummy_conv = ConversionResult(
            ddl="", partition_mapping=None, lossy_casts=[], warnings=[], success=True
        )
        efforts = {}
        for e in tables:
            efforts[e.full_name] = effort_scorer.score(
                e, conversions.get(e.full_name, dummy_conv)
            )

        # Stage 6: Relationship inference
        rel_result = RelationshipInferrer().infer(tables)
        assert len(rel_result.relationships) <= 100_000

        # Stage 7: Complexity scoring
        dep_counts = ComplexityScorer.build_dep_counts(rel_result)
        complexity_scorer = ComplexityScorer()
        complexities = {}
        for e in entities_50k:
            complexities[e.full_name] = complexity_scorer.score(
                e, all_constructs.get(e.full_name, []),
                relationships=None, dep_counts=dep_counts,
            )

        # Stage 12b: SQL translation
        rg = RewriteGuide()
        translation_cache = {}
        for e in entities_50k:
            sql = e.view_query or e.mview_query or (e.routine.body if e.routine else None)
            if sql and sql not in translation_cache:
                translation_cache[sql] = rg.translate(sql)

        # Stage 14: Report generation
        reports = []
        for e in entities_50k:
            reports.append(EntityReport(
                full_name=e.full_name,
                entity_type=e.entity_type,
                population=e.population,
                rows=e.num_rows,
                size_gb=e.num_bytes / (1024 ** 3),
                depends_on=e.depends_on,
                effort=efforts.get(e.full_name),
                conversion=conversions.get(e.full_name),
                load_sync_dml=None,
                complexity=complexities.get(e.full_name, ComplexityResult(
                    category=ComplexityCategory.PORTABLE, score=0, constructs=[],
                    flags=[], reasoning="", confidence=ConfidenceLevel.MEDIUM,
                    confidence_source=ConfidenceSource.SCHEMA_ONLY,
                )),
                rewrite_guidance=[],
                physical_bytes=e.physical_bytes,
            ))

        cost = CostComparison(
            bq_pricing_model=BQPricingModel.ON_DEMAND,
            bigquery_monthly=8000.0,
            bigquery_breakdown=[CostLine(
                label="On-demand queries", monthly=8000.0,
                monthly_low=8000.0, monthly_high=8000.0,
                confidence=ConfidenceLevel.HIGH,
                source_note="BQ on-demand pricing 2024-06",
            )],
            aws_lines=[CostLine(
                label="Redshift Serverless", monthly=5000.0,
                monthly_low=4500.0, monthly_high=6000.0,
                confidence=ConfidenceLevel.MEDIUM,
                source_note="RS serverless estimate",
            )],
            aws_monthly_low=4500.0, aws_monthly_high=6000.0,
            monthly_delta_low=2000.0, monthly_delta_high=3500.0,
            annual_savings_low=24000.0, annual_savings_high=42000.0,
            migration_onetime=75000.0,
            breakeven_months_low=21.4, breakeven_months_high=37.5,
            compute_confidence=ConfidenceLevel.MEDIUM,
        )

        effort_counts = {"AUTO": 0, "ASSISTED": 0, "MANUAL": 0}
        for r in reports:
            if r.effort:
                effort_counts[r.effort.category.value] += 1

        complexity_counts = {"PORTABLE": 0, "ADAPT": 0, "REWRITE": 0}
        for r in reports:
            if r.complexity:
                complexity_counts[r.complexity.category.value] += 1

        assessment = Assessment(
            assessment_id="stress-50k",
            generated_at=datetime.now(timezone.utc),
            project_id="stress-test-50k",
            summary=AssessmentSummary(
                total_entities=TOTAL_ENTITIES,
                total_tables=len(tables),
                total_size_gb=sum(t.num_bytes for t in tables) / (1024 ** 3),
                effort_counts=effort_counts,
                complexity_counts=complexity_counts,
                sql_surface_confidence=ConfidenceLevel.MEDIUM,
            ),
            cost=cost,
            entities=reports,
            failures=[],
        )

        out_dir = str(tmp_path / "reports")
        os.makedirs(out_dir)
        html_paths = HTMLWriter().write(assessment, out_dir)
        json_paths = JSONWriter().write(assessment, out_dir)

        t_total = time.time() - t_start

        # Verify outputs. The HTML must stay browser-loadable at 50k entities —
        # an upper bound, since the client-side renderer exists to keep the
        # embedded payload small (shrinking it further is an improvement, not a bug).
        assert len(html_paths) > 0
        html_size_mb = os.path.getsize(html_paths[0]) / (1024 * 1024)
        assert html_size_mb < 100.0, (
            f"50k-entity report is {html_size_mb:.0f} MB — too large to load in a browser"
        )
        # And it must actually carry the entity payload (not silently render empty).
        with open(html_paths[0], encoding="utf-8") as f:
            html = f.read()
        assert 'id="report-data"' in html
        assert len(json_paths) > 0
        assert t_total < PIPELINE_TIMEOUT_SECONDS, (
            f"Full pipeline took {t_total:.1f}s (limit: {PIPELINE_TIMEOUT_SECONDS}s)"
        )

    def test_cache_round_trip_50k(self, entities_50k, tmp_path):
        """50k entities survive a cache store/load round-trip."""
        db_path = str(tmp_path / "stress.db")
        cache = MetadataCache(db_path=db_path)

        cache.store("stress-test-50k", entities_50k)
        assert cache.has_cache("stress-test-50k")

        loaded = cache.load("stress-test-50k")
        assert loaded is not None
        assert len(loaded) == TOTAL_ENTITIES

        loaded_names = {e.full_name for e in loaded}
        original_names = {e.full_name for e in entities_50k}
        assert loaded_names == original_names


class TestScannerConnectionPool:
    """Verify scanner connection pool expansion with mocked client."""

    def test_pool_expanded_to_match_concurrency(self):
        """Connection pool is sized to concurrency + 10 on client init."""
        from requests.adapters import HTTPAdapter

        scanner = BigQueryScanner(
            project_id="test-pool", use_adc=True, max_concurrent_requests=50
        )
        client = MagicMock(spec=bigquery.Client)
        client._http = MagicMock()
        scanner._client = None

        scanner._expand_connection_pool(client)

        mount_calls = client._http.mount.call_args_list
        assert len(mount_calls) == 2
        for call in mount_calls:
            adapter = call[0][1]
            assert isinstance(adapter, HTTPAdapter)
            assert adapter._pool_connections >= 60
            assert adapter._pool_maxsize >= 60

    def test_scanner_scan_with_mock_client(self):
        """Scanner with mocked client produces correct entities (small scale)."""
        scanner = BigQueryScanner(
            project_id="test-small", use_adc=True, max_concurrent_requests=10
        )
        client = MagicMock(spec=bigquery.Client)

        ds = MagicMock(spec=bigquery.dataset.DatasetListItem)
        ds.dataset_id = "test_ds"
        client.list_datasets.return_value = [ds]

        def _make_field(name, ftype="STRING"):
            sf = MagicMock(spec=bigquery.SchemaField)
            sf.name = name
            sf.field_type = ftype
            sf.mode = "NULLABLE"
            sf.fields = []
            return sf

        items = []
        table_objs = {}
        for i in range(100):
            item = MagicMock(spec=bigquery.table.TableListItem)
            item.dataset_id = "test_ds"
            item.table_id = f"t_{i}"
            ref = MagicMock(spec=bigquery.TableReference)
            ref.table_id = f"t_{i}"
            item.reference = ref
            items.append(item)

            tbl = MagicMock(spec=bigquery.Table)
            tbl.table_id = f"t_{i}"
            tbl.dataset_id = "test_ds"
            tbl.table_type = "TABLE"
            tbl.num_rows = 1000
            tbl.num_bytes = 50000
            tbl.schema = [_make_field("id"), _make_field("name")]
            tbl.time_partitioning = None
            tbl.range_partitioning = None
            tbl.clustering_fields = None
            tbl.view_query = None
            tbl.mview_query = None
            tbl.modified = datetime(2025, 1, 1, tzinfo=timezone.utc)
            table_objs[f"t_{i}"] = tbl

        client.list_tables.return_value = items
        client.get_table.side_effect = lambda ref: table_objs[ref.table_id]
        client.list_routines.return_value = []

        scanner._client = client
        entities = list(scanner.scan())

        assert len(entities) == 100
        assert scanner.failures == []
