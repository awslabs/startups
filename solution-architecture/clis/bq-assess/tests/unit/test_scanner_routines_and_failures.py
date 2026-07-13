"""Unit tests filling the #11 (1.6) gaps not already covered by #6/#8/#9.

Most of the task-1.6 checklist (credential success/failure, dataset filter, retry,
per-table skip, cache overwrite) is already covered in ``test_scanner.py`` / ``test_cache.py``.
This module adds the genuinely-missing scanner branches:
- routine scanning success (R3.3) and routine-level failure resilience (R23.2)
- dataset-level list-tables failure recorded + continue (R23.2)
- view entity population/SQL captured at scan time (R3.2, R4.3)
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from google.api_core.exceptions import GoogleAPICallError
from google.cloud import bigquery

from bq_assess.core.scanner import BigQueryScanner
from bq_assess.models import EntityPopulation, EntityType


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------

def _make_scanner() -> BigQueryScanner:
    scanner = BigQueryScanner(project_id="test-project", use_adc=True)
    scanner._client = MagicMock(spec=bigquery.Client)
    scanner._client.list_routines.return_value = []
    return scanner


def _make_dataset_list_item(dataset_id: str):
    item = MagicMock(spec=bigquery.dataset.DatasetListItem)
    item.dataset_id = dataset_id
    return item


def _make_schema_field(name: str, field_type: str = "STRING", mode: str = "NULLABLE"):
    sf = MagicMock(spec=bigquery.SchemaField)
    sf.name = name
    sf.field_type = field_type
    sf.mode = mode
    sf.fields = []
    return sf


def _make_view(dataset_id: str, table_id: str, view_query: str):
    tbl = MagicMock(spec=bigquery.Table)
    tbl.table_id = table_id
    tbl.dataset_id = dataset_id
    tbl.table_type = "VIEW"
    tbl.num_rows = 0
    tbl.num_bytes = 0
    tbl.schema = [_make_schema_field("id", "INT64", "NULLABLE")]
    tbl.time_partitioning = None
    tbl.range_partitioning = None
    tbl.clustering_fields = None
    tbl.view_query = view_query
    tbl.mview_query = None
    tbl.modified = datetime(2024, 6, 1, tzinfo=timezone.utc)
    return tbl


def _make_table_list_item(dataset_id: str, table_id: str):
    item = MagicMock(spec=bigquery.table.TableListItem)
    item.dataset_id = dataset_id
    item.table_id = table_id
    item.reference = MagicMock(spec=bigquery.TableReference)
    return item


def _make_routine_list_item(dataset_id: str, routine_id: str):
    item = MagicMock()
    item.routine_id = routine_id
    item.dataset_id = dataset_id
    item.reference = MagicMock()
    return item


def _make_full_routine(routine_id: str, *, language="JAVASCRIPT", body="return x;"):
    r = MagicMock()
    r.routine_id = routine_id
    r.language = language
    arg = MagicMock()
    arg.name = "x"
    r.arguments = [arg]
    r.body = body
    r.type_ = "SCALAR_FUNCTION"
    r.modified = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return r


# ---------------------------------------------------------------------------
# Routine scanning (R3.3)
# ---------------------------------------------------------------------------


class TestRoutineScanning:
    def test_routine_yielded_as_rebuilt_entity(self):
        scanner = _make_scanner()
        client = scanner._client
        client.list_datasets.return_value = [_make_dataset_list_item("udfs")]
        client.list_tables.return_value = []
        rli = _make_routine_list_item("udfs", "to_upper")
        client.list_routines.return_value = [rli]
        client.get_routine.return_value = _make_full_routine("to_upper")

        results = list(scanner.scan())

        assert len(results) == 1
        e = results[0]
        assert e.entity_type is EntityType.ROUTINE
        assert e.population is EntityPopulation.REBUILT
        assert e.routine is not None
        assert e.routine.language == "JAVASCRIPT"
        assert e.routine.arguments == ["x"]
        assert e.full_name == "udfs.to_upper"
        assert scanner.failures == []

    @patch("bq_assess.core.scanner.time.sleep")
    def test_routine_failure_recorded_and_skipped(self, _sleep):
        """A routine that fails to fetch is recorded and does not abort the scan (R23.2)."""
        scanner = _make_scanner()
        client = scanner._client
        client.list_datasets.return_value = [_make_dataset_list_item("udfs")]
        client.list_tables.return_value = []

        good = _make_routine_list_item("udfs", "good_fn")
        bad = _make_routine_list_item("udfs", "bad_fn")
        client.list_routines.return_value = [bad, good]

        err = GoogleAPICallError("boom")
        err.code = 400

        def get_routine(ref):
            if ref is bad.reference:
                raise err
            return _make_full_routine("good_fn")

        client.get_routine.side_effect = get_routine

        results = list(scanner.scan())

        assert {e.entity_id for e in results} == {"good_fn"}
        assert len(scanner.failures) == 1
        assert scanner.failures[0].entity_name == "udfs.bad_fn"
        assert scanner.failures[0].stage == "scan"


# ---------------------------------------------------------------------------
# Dataset-level resilience (R23.2)
# ---------------------------------------------------------------------------


class TestDatasetLevelFailures:
    @patch("bq_assess.core.scanner.time.sleep")
    def test_list_tables_failure_recorded_and_continues(self, _sleep):
        """If list_tables fails for a dataset, record it and continue to the next dataset."""
        scanner = _make_scanner()
        client = scanner._client
        client.list_datasets.return_value = [
            _make_dataset_list_item("bad_ds"),
            _make_dataset_list_item("good_ds"),
        ]

        good_item = _make_table_list_item("good_ds", "t1")
        err = GoogleAPICallError("dataset boom")
        err.code = 400

        def list_tables(ds):
            if ds == "bad_ds":
                raise err
            return [good_item]

        client.list_tables.side_effect = list_tables

        good_table = MagicMock(spec=bigquery.Table)
        good_table.table_id = "t1"
        good_table.dataset_id = "good_ds"
        good_table.table_type = "TABLE"
        good_table.num_rows = 1
        good_table.num_bytes = 1
        good_table.schema = [_make_schema_field("id", "INT64", "REQUIRED")]
        good_table.time_partitioning = None
        good_table.range_partitioning = None
        good_table.clustering_fields = None
        good_table.view_query = None
        good_table.mview_query = None
        good_table.modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
        client.get_table.return_value = good_table

        results = list(scanner.scan())

        assert {e.entity_id for e in results} == {"t1"}
        # bad_ds recorded as a scan failure
        assert any(f.entity_name == "bad_ds" for f in scanner.failures)

    @patch("bq_assess.core.scanner.time.sleep")
    def test_list_routines_failure_recorded(self, _sleep):
        """If list_routines fails for a dataset, record it and continue (R23.2)."""
        scanner = _make_scanner()
        client = scanner._client
        client.list_datasets.return_value = [_make_dataset_list_item("ds")]
        client.list_tables.return_value = []

        err = GoogleAPICallError("routines boom")
        err.code = 400
        client.list_routines.side_effect = err

        results = list(scanner.scan())

        assert results == []
        assert any("routines" in f.entity_name for f in scanner.failures)


# ---------------------------------------------------------------------------
# View entity at scan time (R3.2, R4.3)
# ---------------------------------------------------------------------------


class TestViewScanning:
    def test_view_population_and_sql_captured(self):
        scanner = _make_scanner()
        client = scanner._client
        client.list_datasets.return_value = [_make_dataset_list_item("analytics")]
        item = _make_table_list_item("analytics", "active_users")
        client.list_tables.return_value = [item]
        client.get_table.return_value = _make_view(
            "analytics", "active_users", "SELECT id FROM analytics.users WHERE active"
        )

        results = list(scanner.scan())

        assert len(results) == 1
        e = results[0]
        assert e.entity_type is EntityType.VIEW
        assert e.population is EntityPopulation.REBUILT
        assert e.view_query is not None
        # best-effort dependency extracted from the view SQL (R4.5)
        assert "analytics.users" in e.depends_on
