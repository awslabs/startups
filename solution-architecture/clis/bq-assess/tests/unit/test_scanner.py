"""Unit tests for BigQuery scanner — credential validation, filtering, retry, and resilience."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import bigquery

from bq_assess.scanner import BigQueryScanner, ScannerError, _retry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scanner(**kwargs) -> BigQueryScanner:
    """Create a scanner with use_adc=True and inject a mock client."""
    scanner = BigQueryScanner(project_id="test-project", use_adc=True, **kwargs)
    scanner._client = MagicMock(spec=bigquery.Client)
    # Default: no routines in any dataset (tests that exercise tables override per-dataset).
    scanner._client.list_routines.return_value = []
    return scanner


def _make_schema_field(name: str, field_type: str = "STRING", mode: str = "NULLABLE", fields=()):
    """Build a mock SchemaField."""
    sf = MagicMock(spec=bigquery.SchemaField)
    sf.name = name
    sf.field_type = field_type
    sf.mode = mode
    sf.fields = [_make_schema_field(**f) if isinstance(f, dict) else f for f in fields]
    return sf


def _make_table(dataset_id: str, table_id: str, *, num_rows: int = 100, num_bytes: int = 2048):
    """Build a mock bigquery.Table with minimal metadata."""
    tbl = MagicMock(spec=bigquery.Table)
    tbl.table_id = table_id
    tbl.dataset_id = dataset_id
    tbl.table_type = "TABLE"
    tbl.num_rows = num_rows
    tbl.num_bytes = num_bytes
    tbl.schema = [_make_schema_field("id", "INT64", "REQUIRED")]
    tbl.time_partitioning = None
    tbl.range_partitioning = None
    tbl.clustering_fields = None
    tbl.view_query = None
    tbl.mview_query = None
    tbl.modified = datetime(2024, 6, 1, tzinfo=timezone.utc)
    return tbl


def _make_dataset_list_item(dataset_id: str):
    item = MagicMock(spec=bigquery.dataset.DatasetListItem)
    item.dataset_id = dataset_id
    return item


def _make_table_list_item(dataset_id: str, table_id: str):
    item = MagicMock(spec=bigquery.table.TableListItem)
    item.dataset_id = dataset_id
    item.table_id = table_id
    item.reference = MagicMock(spec=bigquery.TableReference)
    return item


# ---------------------------------------------------------------------------
# Credential validation
# ---------------------------------------------------------------------------

class TestValidateCredentials:
    """Requirement 2.1 — lightweight metadata query to verify read access."""

    def test_success_returns_true(self):
        scanner = _make_scanner()
        scanner._client.list_datasets.return_value = [_make_dataset_list_item("ds1")]

        assert scanner.validate_credentials() is True
        scanner._client.list_datasets.assert_called_once_with(max_results=1)

    def test_failure_raises_scanner_error(self):
        scanner = _make_scanner()
        scanner._client.list_datasets.side_effect = Exception("403 Forbidden")

        with pytest.raises(ScannerError, match="permissions"):
            scanner.validate_credentials()

    def test_failure_project_not_found(self):
        scanner = _make_scanner()
        scanner._client.list_datasets.side_effect = Exception("404 Not Found")

        with pytest.raises(ScannerError, match="not found"):
            scanner.validate_credentials()

    def test_failure_invalid_credentials(self):
        scanner = _make_scanner()
        scanner._client.list_datasets.side_effect = Exception("401 invalid credentials")

        with pytest.raises(ScannerError, match="Invalid credentials"):
            scanner.validate_credentials()

    def test_no_credentials_raises_scanner_error(self):
        """When neither credentials_path nor use_adc is set, ScannerError is raised."""
        scanner = BigQueryScanner(project_id="test-project")
        with pytest.raises(ScannerError, match="No credentials provided"):
            scanner.validate_credentials()


# ---------------------------------------------------------------------------
# Dataset filtering  (Requirement 3.2)
# ---------------------------------------------------------------------------

class TestDatasetFiltering:

    def test_filter_limits_to_specified_datasets(self):
        scanner = _make_scanner()
        client = scanner._client

        ds_a = _make_dataset_list_item("alpha")
        ds_b = _make_dataset_list_item("beta")
        ds_c = _make_dataset_list_item("gamma")
        client.list_datasets.return_value = [ds_a, ds_b, ds_c]

        tbl_a = _make_table_list_item("alpha", "t1")
        tbl_b = _make_table_list_item("beta", "t2")
        client.list_tables.side_effect = lambda ds_id: {
            "alpha": [tbl_a],
            "beta": [tbl_b],
        }.get(ds_id, [])

        client.get_table.side_effect = lambda ref: {
            tbl_a.reference: _make_table("alpha", "t1"),
            tbl_b.reference: _make_table("beta", "t2"),
        }[ref]

        results = list(scanner.scan(dataset_filter=["alpha", "beta"]))

        assert len(results) == 2
        dataset_ids = {r.dataset_id for r in results}
        assert dataset_ids == {"alpha", "beta"}
        # gamma should never have been listed
        listed_ds_ids = [call.args[0] for call in client.list_tables.call_args_list]
        assert "gamma" not in listed_ds_ids

    def test_no_filter_scans_all_datasets(self):
        scanner = _make_scanner()
        client = scanner._client

        ds_a = _make_dataset_list_item("alpha")
        ds_b = _make_dataset_list_item("beta")
        client.list_datasets.return_value = [ds_a, ds_b]

        tbl_a = _make_table_list_item("alpha", "t1")
        tbl_b = _make_table_list_item("beta", "t2")
        client.list_tables.side_effect = lambda ds_id: {
            "alpha": [tbl_a],
            "beta": [tbl_b],
        }.get(ds_id, [])

        client.get_table.side_effect = lambda ref: {
            tbl_a.reference: _make_table("alpha", "t1"),
            tbl_b.reference: _make_table("beta", "t2"),
        }[ref]

        results = list(scanner.scan())

        assert len(results) == 2
        dataset_ids = {r.dataset_id for r in results}
        assert dataset_ids == {"alpha", "beta"}


# ---------------------------------------------------------------------------
# Retry logic  (Requirement 15.1)
# ---------------------------------------------------------------------------

class TestRetryLogic:

    @patch("bq_assess.scanner.time.sleep")
    def test_retries_on_429_then_succeeds(self, mock_sleep):
        """Transient 429 on first call, success on second."""
        err = GoogleAPICallError("rate limited")
        err._code = 429  # noqa: SLF001
        err.code = 429

        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise err
            return "ok"

        result = _retry(fn)
        assert result == "ok"
        assert call_count == 2
        mock_sleep.assert_called_once()  # slept once between attempts

    @patch("bq_assess.scanner.time.sleep")
    def test_retries_on_500_then_succeeds(self, mock_sleep):
        err = GoogleAPICallError("internal error")
        err._code = 500
        err.code = 500

        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise err
            return "ok"

        result = _retry(fn)
        assert result == "ok"
        assert call_count == 3
        assert mock_sleep.call_count == 2

    @patch("bq_assess.scanner.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        err = GoogleAPICallError("service unavailable")
        err._code = 503
        err.code = 503

        with pytest.raises(GoogleAPICallError):
            _retry(lambda: (_ for _ in ()).throw(err))

        # 1 initial + 3 retries = 4 calls, 3 sleeps
        assert mock_sleep.call_count == 3

    @patch("bq_assess.scanner.time.sleep")
    def test_exponential_backoff_delays(self, mock_sleep):
        err = GoogleAPICallError("rate limited")
        err._code = 429
        err.code = 429

        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise err
            return "ok"

        _retry(fn)
        delays = [c.args[0] for c in mock_sleep.call_args_list]
        assert len(delays) == 3
        for i, actual in enumerate(delays):
            base = 1.0 * (2.0 ** i)
            assert base * 0.5 <= actual <= base * 1.5

    @patch("bq_assess.scanner.time.sleep")
    def test_non_retryable_error_raises_immediately(self, mock_sleep):
        """A 400 Bad Request should not be retried."""
        err = GoogleAPICallError("bad request")
        err._code = 400
        err.code = 400

        with pytest.raises(GoogleAPICallError):
            _retry(lambda: (_ for _ in ()).throw(err))

        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Per-table failure skipping  (Requirement 15.2)
# ---------------------------------------------------------------------------

class TestPerTableFailureSkipping:

    @patch("bq_assess.scanner.time.sleep")
    def test_failed_table_is_skipped_and_recorded(self, mock_sleep):
        scanner = _make_scanner()
        client = scanner._client

        ds = _make_dataset_list_item("ds1")
        client.list_datasets.return_value = [ds]

        tbl_ok = _make_table_list_item("ds1", "good_table")
        tbl_bad = _make_table_list_item("ds1", "bad_table")
        client.list_tables.return_value = [tbl_ok, tbl_bad]

        err = GoogleAPICallError("permanent failure")
        err._code = 400
        err.code = 400

        def get_table_side_effect(ref):
            if ref is tbl_bad.reference:
                raise err
            return _make_table("ds1", "good_table")

        client.get_table.side_effect = get_table_side_effect

        results = list(scanner.scan())

        # good_table yielded, bad_table skipped
        assert len(results) == 1
        assert results[0].entity_id == "good_table"

        # failure recorded
        assert len(scanner.failures) == 1
        assert scanner.failures[0].entity_name == "ds1.bad_table"
        assert "permanent failure" in scanner.failures[0].error

    @patch("bq_assess.scanner.time.sleep")
    def test_multiple_failures_still_yield_remaining(self, mock_sleep):
        scanner = _make_scanner()
        client = scanner._client

        ds = _make_dataset_list_item("ds1")
        client.list_datasets.return_value = [ds]

        tbl1 = _make_table_list_item("ds1", "t1")
        tbl2 = _make_table_list_item("ds1", "t2")
        tbl3 = _make_table_list_item("ds1", "t3")
        client.list_tables.return_value = [tbl1, tbl2, tbl3]

        err = GoogleAPICallError("fail")
        err._code = 400
        err.code = 400

        def get_table_side_effect(ref):
            if ref is tbl1.reference:
                raise err
            if ref is tbl3.reference:
                raise err
            return _make_table("ds1", "t2")

        client.get_table.side_effect = get_table_side_effect

        results = list(scanner.scan())

        assert len(results) == 1
        assert results[0].entity_id == "t2"
        assert len(scanner.failures) == 2
        failed_refs = {f.entity_name for f in scanner.failures}
        assert failed_refs == {"ds1.t1", "ds1.t3"}
