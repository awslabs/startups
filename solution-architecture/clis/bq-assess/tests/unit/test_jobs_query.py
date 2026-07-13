# Feature: bq-assess-lakehouse, issue 5.x review fix: shared JOBS reader
"""Unit tests for the shared INFORMATION_SCHEMA.JOBS reader (core/jobs_query.py).

One place builds the project-wide job-history query that PricingDetector (5.1) and
WorkloadAnalyzer (5.2) both read — using JOBS_BY_PROJECT (not the per-user JOBS alias),
project- and region-qualified, with the completed-query lookback filter — and runs it under
the scanner's retry, degrading to [] on any error (never raises).
"""

from __future__ import annotations

from google.api_core.exceptions import Forbidden

from bq_assess.core.jobs_query import read_jobs


class _FakeQueryJob:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return iter(self._rows)


class _FakeClient:
    def __init__(self, *, rows=None, error=None):
        self._rows = rows if rows is not None else []
        self._error = error
        self.queries: list[str] = []

    def query(self, sql, *a, **k):
        self.queries.append(sql)
        if self._error is not None:
            raise self._error
        return _FakeQueryJob(self._rows)


def test_query_uses_jobs_by_project_not_per_user_alias() -> None:
    """The whole-project view, not the bare per-user JOBS alias (review #1)."""
    c = _FakeClient(rows=[{"x": 1}])
    read_jobs(c, "proj", "SELECT reservation_id", days=30, location="US")
    sql = c.queries[0]
    assert "INFORMATION_SCHEMA.JOBS_BY_PROJECT" in sql
    # Project- and region-qualified.
    assert "`proj`" in sql
    assert "`region-us`" in sql


def test_query_filters_completed_queries_over_lookback() -> None:
    """WHERE bounds to completed QUERY jobs over the lookback, excluding SCRIPT (review #2)."""
    c = _FakeClient(rows=[])
    read_jobs(c, "proj", "SELECT reservation_id", days=14, location="US")
    sql = c.queries[0]
    assert "job_type = 'QUERY'" in sql
    assert "state = 'DONE'" in sql
    assert "INTERVAL 14 DAY" in sql
    assert "statement_type != 'SCRIPT'" in sql


def test_returns_rows_on_success() -> None:
    rows = [{"a": 1}, {"a": 2}]
    assert read_jobs(_FakeClient(rows=rows), "proj", "SELECT a") == rows


def test_degrades_to_empty_on_error_never_raises() -> None:
    """Missing perms / any error → [] (callers treat no-signal as no-data), never raises."""
    c = _FakeClient(error=Forbidden("403 bigquery.jobs.listAll"))
    assert read_jobs(c, "proj", "SELECT a") == []


def test_select_clause_is_caller_supplied() -> None:
    """The caller supplies only the SELECT list; the FROM/WHERE skeleton is shared."""
    c = _FakeClient(rows=[])
    read_jobs(c, "proj", "SELECT total_slot_ms, creation_time")
    assert "SELECT total_slot_ms, creation_time" in c.queries[0]


def test_retryable_error_exhausts_retries_then_degrades_to_empty() -> None:
    """A retryable error (429/500/503) that persists through all retry attempts still
    degrades to [] — the retry logic re-raises on the final attempt, caught by the outer
    except in read_jobs (R16.3/R17.3 graceful degradation)."""
    from unittest.mock import patch
    from google.api_core.exceptions import ServiceUnavailable

    call_count = 0

    class _RetryClient:
        def query(self, sql, *a, **k):
            nonlocal call_count
            call_count += 1
            raise ServiceUnavailable("503 Backend unavailable")

    with patch("bq_assess.core.jobs_query.time.sleep"):
        result = read_jobs(_RetryClient(), "proj", "SELECT a")

    assert result == []
    assert call_count == 4  # initial + 3 retries
