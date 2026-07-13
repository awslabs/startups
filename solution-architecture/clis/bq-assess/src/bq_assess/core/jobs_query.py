"""Shared INFORMATION_SCHEMA.JOBS reader for the cost-input modules (R16/R17).

``PricingDetector`` (5.1) and ``WorkloadAnalyzer`` (5.2) both read project-wide job history
from BigQuery; this is the single place that builds the query and runs it, so the
project/region qualification, the completed-query lookback filter, and the SCRIPT exclusion
are defined once.

Two corrections this consolidates (5.x review):
- Uses ``INFORMATION_SCHEMA.JOBS_BY_PROJECT`` — the **whole-project** view — not the bare
  ``JOBS`` alias, which is ``JOBS_BY_USER`` and returns only the *calling identity's* jobs. A
  service account that did not submit the workload would otherwise see an empty job log and the
  Source would be silently mis-assessed (false on-demand / no workload).
- Always applies ``job_type='QUERY' AND state='DONE'`` and a ``creation_time`` lookback bound,
  matching the legacy ``analyzer.py`` idiom; the caller supplies only the SELECT list.

Degrades to ``[]`` on any error (e.g. missing ``bigquery.jobs.listAll``) — the callers treat
no-signal as no-data and never raise (R16.3 / R17.3).
"""

from __future__ import annotations

import logging
import time

from google.api_core.exceptions import GoogleAPICallError

from bq_assess.core import pricing_constants as k

logger = logging.getLogger(__name__)

_RETRYABLE_CODES = {429, 500, 503}
_MAX_RETRIES = 3
_INITIAL_DELAY = 1.0

DEFAULT_LOOKBACK_DAYS = 30


def read_jobs(
    client,
    project_id: str,
    select_clause: str,
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    location: str = "US",
    group_by: str | None = None,
) -> list:
    """Run ``<select_clause> FROM <project>.<region>.JOBS_BY_PROJECT WHERE <completed-query>``.

    ``select_clause`` is the full ``SELECT col, ...`` the caller needs (e.g.
    ``"SELECT reservation_id, edition, statement_type"``). ``group_by`` appends
    ``GROUP BY <expr>`` after the shared WHERE. Returns the row list, or ``[]`` if
    the query cannot be run — never raises.
    """
    sql = (
        f"{select_clause} "
        f"FROM `{project_id}`.`region-{location.lower()}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT "
        f"WHERE job_type = 'QUERY' AND state = 'DONE' "
        f"AND creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(days)} DAY) "
        f"AND {k.V5_JOBS_STATEMENT_TYPE_COLUMN} != '{k.V5_JOBS_SCRIPT_STATEMENT_TYPE}'"
    )
    if group_by:
        sql += f" GROUP BY {group_by}"
    try:
        return list(_retry_query(lambda: client.query(sql).result()))
    except Exception as exc:  # missing perms / any error → no signal, not a failure
        logger.warning("Could not read INFORMATION_SCHEMA.JOBS_BY_PROJECT: %s", exc)
        return []


def read_jobs_hourly(
    client,
    project_id: str,
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    location: str = "US",
) -> list:
    """Read the workload as HOURLY aggregates — ≤ 24×days rows regardless of query volume.

    BigQuery collapses per-job rows server-side into the same UTC-hour buckets
    ``WorkloadAnalyzer._compute`` previously built in Python, so a Source running millions
    of queries/month costs the client ≤720 rows instead of a multi-GB row stream (the
    10 PB-scale OOM found in the 2026-07-08 storm audit). ``missing_billed_jobs`` preserves
    the all-or-nothing ``has_billed_bytes`` semantics: any NULL ``total_bytes_billed`` in
    the window degrades the whole window to the processed-bytes fallback, exactly as the
    per-job path did. Returns ``[]`` on any error — never raises (R17.3).
    """
    select = (
        "SELECT TIMESTAMP_TRUNC(creation_time, HOUR) AS hour_bucket, "
        "SUM(total_slot_ms) AS total_slot_ms, "
        "COUNT(*) AS job_count, "
        "SUM(total_bytes_processed) AS total_bytes_processed, "
        "SUM(total_bytes_billed) AS total_bytes_billed, "
        "COUNTIF(total_bytes_billed IS NULL) AS missing_billed_jobs"
    )
    return read_jobs(
        client, project_id, select,
        days=days, location=location, group_by="hour_bucket",
    )


# Cap on distinct query texts exported to queries.jsonl. Ordered by total slot-ms so the
# heaviest statements always survive the cut; the collector logs when truncation occurs.
# Bounds the export the same way read_jobs_hourly bounds the workload read (no per-job
# row stream — the 2026-07-08 storm-audit OOM class).
QUERIES_EXPORT_LIMIT = 50_000


def read_jobs_queries(
    client,
    project_id: str,
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    location: str = "US",
    limit: int = QUERIES_EXPORT_LIMIT,
) -> list:
    """Read DISTINCT query texts + aggregate per-statement stats (bounded).

    Groups server-side by query text so the row count is bounded by workload
    *diversity*, not volume, then caps at ``limit`` ordered by total slot-ms
    (heaviest statements first). NULL-billed jobs are tracked per group via
    ``missing_billed_jobs`` — same all-or-nothing billed semantics as the hourly
    read. Returns ``[]`` on any error — never raises (R17.3).
    """
    select = (
        "SELECT query, "
        "SUM(total_slot_ms) AS total_slot_ms, "
        "COUNT(*) AS job_count, "
        "SUM(total_bytes_processed) AS total_bytes_processed, "
        "SUM(total_bytes_billed) AS total_bytes_billed, "
        "COUNTIF(total_bytes_billed IS NULL) AS missing_billed_jobs, "
        "ANY_VALUE(statement_type) AS statement_type, "
        "MAX(creation_time) AS creation_time"
    )
    return read_jobs(
        client, project_id, select,
        days=days, location=location,
        group_by=f"query ORDER BY total_slot_ms DESC LIMIT {int(limit)}",
    )


def read_reservation_groups(
    client,
    project_id: str,
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    location: str = "US",
) -> list:
    """Read the pricing-model signal as ``GROUP BY reservation_id, edition`` counts.

    A project has a handful of distinct (reservation_id, edition) pairs, so this returns
    a handful of rows where the per-job read returned millions. NULL-ness of
    ``reservation_id`` is preserved per group — the classification signal (V5) is intact.
    Returns ``[]`` on any error — never raises (R16.3).
    """
    select = (
        f"SELECT {k.V5_JOBS_RESERVATION_ID_COLUMN}, {k.V5_JOBS_EDITION_COLUMN}, "
        f"COUNT(*) AS job_count"
    )
    return read_jobs(
        client, project_id, select,
        days=days, location=location,
        group_by=f"{k.V5_JOBS_RESERVATION_ID_COLUMN}, {k.V5_JOBS_EDITION_COLUMN}",
    )


def _retry_query(fn):
    """Execute fn with exponential-backoff retries on transient BigQuery errors."""
    delay = _INITIAL_DELAY
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return fn()
        except GoogleAPICallError as exc:
            if exc.code not in _RETRYABLE_CODES or attempt == _MAX_RETRIES:
                raise
            logger.warning("Retryable error (attempt %d): %s", attempt + 1, exc)
            time.sleep(delay)
            delay *= 2
