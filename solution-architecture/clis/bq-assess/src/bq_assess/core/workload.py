"""Slot-time and workload analysis — the BigQuery compute-consumption curve (R17).

``WorkloadAnalyzer`` reads the workload from ``INFORMATION_SCHEMA.JOBS`` (live,
``analyze_from_api``) or an exported query-log JSON file (``analyze_from_file``) over a
lookback window, and derives a Slot Time utilization curve: average / P50 / P99 / peak
concurrent slots plus an active-hour fraction (idle vs busy). The result grounds the AWS
compute estimate (R18) in real utilization.

Scale note (2026-07-08, storm audit): the live path reads HOURLY aggregates
(``jobs_query.read_jobs_hourly`` — ≤ 24×days rows) rather than per-job rows. Every curve
metric was already derived from hourly buckets or grand sums, so aggregating server-side
removes the multi-GB row stream a busy Source produced (the 10 PB-scale OOM risk). The
file path accepts BOTH formats: legacy per-job entries (``creation_time`` key) are
bucketed client-side; hourly-aggregate entries (parseable ``hour_bucket`` value, as
written by the metadata exporter) pass straight through.

Billed-basis policy (single rule, every input shape): a bucket is billed-carrying iff
every job it summarizes carried a non-NULL ``total_bytes_billed`` — tracked as
``missing_billed_jobs`` on each bucket (NULL column value live; absent key in a file
entry). Any missing job degrades the window to the processed-bytes fallback (a labelled
overestimate, never a silent underestimate). Intentional behavior change from the
per-job era, which counted NULL billed as $0 on the billed basis: under capacity
(reservation) pricing GCP documents total_bytes_billed as "informational only" — the
value is untrustworthy regardless of whether it arrives as NULL, 0, or a non-billable
number — so such a Source now degrades honestly instead of reporting a genuine-looking
$0 scan volume.

Returns ``SlotUtilization | None``: ``None`` (never a zeroed struct, never raised) when there
is no usable workload — empty job set, missing ``bigquery.jobs.listAll`` (api), or a
missing/empty/malformed file. That ``None`` is what trips the LOW-confidence cost *range*
downstream (R18.4 / P22); a zero-struct would silently defeat it.

Metric definitions (deterministic; SCRUM_NOTES § Issue 5.2):
- ``days_sampled`` = distinct UTC dates carrying a slot-bearing job.
- ``avg_slots`` = ``total_slot_ms / (days_sampled * 86_400_000)`` — mean concurrency over the
  active-day window.
- per-hour slot series over ``[first, last]`` active hour with idle hours zero-filled; ``p50``
  / ``p99`` are percentiles of that series, ``peak`` its max. Bursty load ⇒ low P50, high peak.
- ``active_hour_fraction`` = ``busy_hours / (days_sampled * 24)`` clamped to ``[0, 1]``
  (busy = hour buckets with slot_ms > 0) — the over-provisioning signal R18 reads.

Slot *concurrency* is a per-hour bucket average (``slot_ms / 3.6M``): JOBS carries no per-job
duration, so instantaneous concurrency is not recoverable — documented approximation.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bq_assess.core import jobs_query
from bq_assess.core.analyzer import QueryAnalyzer
from bq_assess.models import SlotUtilization

logger = logging.getLogger(__name__)

_HOUR_MS = 3_600_000
_DAY_MS = 86_400_000

# Sanity cap on how far a bucket may sit from the workload's median hour. The lookback
# is ≤ 1 year, so a bucket > ~3 years out is corrupt-by-construction (e.g. a year-9999
# timestamp) — and one such bucket would make the zero-filled hourly series span
# millions of hours, resurrecting the OOM the hourly aggregation removed.
_MAX_SPAN_HOURS = 3 * 366 * 24


def parse_json_or_jsonl(text: str) -> list[dict] | None:
    """Parse text as a JSON array/object, falling back to JSONL (one object per line).

    The single parser for query-log files: WorkloadAnalyzer.analyze_from_file and the
    collector's statement extraction MUST accept the same formats — the old exporter
    wrote JSONL, and one stage silently reading [] where the other succeeded was a
    real bug (2026-07-08 review).
    """
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # A single-line JSONL file (e.g. a one-bucket export) parses as a bare
            # object — treat it as a one-entry log, not an invalid format.
            return [data]
        # Valid JSON but not an array/object — reject (not a valid query-log format)
        return None
    except (json.JSONDecodeError, ValueError):
        pass
    # Try JSONL: one JSON object per line
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    if not lines:
        return None
    entries = []
    skipped = 0
    for line in lines:
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                entries.append(obj)
            else:
                skipped += 1
        except (json.JSONDecodeError, ValueError):
            skipped += 1
    if skipped:
        logger.warning("Skipped %d unparseable lines in JSONL query-log file", skipped)
    return entries if entries else None


class WorkloadAnalyzer:
    """Compute the slot-utilization curve for a Source (R17)."""

    def analyze_from_api(self, client, project_id: str, days: int = 30, location: str = "US"):
        """Read HOURLY workload aggregates over the lookback and compute the curve.

        Returns (SlotUtilization | None, hourly_buckets: list[dict]). hourly_buckets is the
        normalized bucket list for metadata export (≤ 24×days entries — bounded regardless
        of the Source's query volume). Returns (None, []) when no usable workload is
        readable (R17.3 graceful degradation; never raises).
        """
        rows = self._read_jobs(client, project_id, days, location)
        buckets = self._normalize_hourly_rows(rows)
        if not buckets:
            return None, []
        return self._compute(buckets), buckets

    def analyze_from_file(self, path):
        """Compute the curve from an exported query-log JSON file (R1.3 ``--query-logs``).

        Accepts BOTH formats, per entry:
        - **hourly aggregate** (parseable ``hour_bucket`` value) — as written by the
          metadata exporter's ``jobs_hourly.jsonl``; passes through as a bucket.
        - **per-job** (``creation_time`` value) — old ``jobs.jsonl`` exports and
          hand-built logs; bucketed client-side.
        An entry with a null/unparseable ``hour_bucket`` falls through to the
        ``creation_time`` branch rather than being dropped.

        Returns (SlotUtilization | None, hourly_buckets: list[dict]). Returns (None, [])
        when the file is missing/unreadable/malformed or yields no usable entries.

        R17.4 note: the slot-utilization path consumes only slot/byte totals + timestamps
        and never reads, stores, or reports query text, so there is no query text to anonymize
        here. Query-text anonymization (R17.4 / R22.4) lives on the separate query-analysis path
        (``QueryAnalyzer.anonymize_query``); ``WorkloadAnalyzer.anonymize_query`` delegates to it
        for any caller that does handle query text, but this method does not.
        """
        p = Path(path)
        if not p.exists():
            return None, []
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Could not read query-log file %s: %s", p, exc)
            return None, []
        data = self._parse_json_or_jsonl(text)
        if data is None:
            return None, []

        buckets = _normalize_entries(data)
        if not buckets:
            return None, []
        return self._compute(buckets), buckets

    def _parse_json_or_jsonl(self, text: str) -> list[dict] | None:
        """Parse text as JSON array, falling back to JSONL (one JSON object per line)."""
        return parse_json_or_jsonl(text)

    def anonymize_query(self, query_text: str) -> str:
        """Strip literal values from query text (R17.4 / R22.4).

        Delegates to ``QueryAnalyzer.anonymize_query`` — single source of truth for the
        anonymization regex; the Workload Analyzer does not re-implement it.
        """
        return QueryAnalyzer().anonymize_query(query_text)

    def _read_jobs(self, client, project_id: str, days: int, location: str) -> list:
        """Read hourly workload aggregates from project-wide job history over the lookback.

        Delegates to ``core.jobs_query.read_jobs_hourly`` (JOBS_BY_PROJECT, completed-query
        lookback, project/region-qualified, GROUP BY hour) — ≤ 24×days rows regardless of
        the Source's query volume. Returns ``[]`` if the query cannot be run (e.g. missing
        ``jobs.listAll``) — the caller treats no-signal as no-workload (returns None),
        never an error (R17.3).
        """
        return jobs_query.read_jobs_hourly(
            client, project_id, days=days, location=location,
        )

    def _normalize_hourly_rows(self, rows) -> list[dict]:
        """Map raw rows (dict or BigQuery Row) to hourly bucket dicts; drop unusable ones.

        Delegates to the module-level ``_normalize_entries`` — the single dual-format
        normalizer shared with ``analyze_from_file``, so the live and file paths cannot
        drift apart on shape or billed-basis rules.
        """
        return _normalize_entries(rows)

    def _compute(self, buckets: list[dict]) -> SlotUtilization:
        """Derive the SlotUtilization curve from hourly buckets (>= 1; see metric defs above)."""
        total_slot_ms = 0
        total_bytes_processed = 0
        total_bytes_billed = 0
        total_queries = 0
        # The window counts as billed-carrying only if EVERY bucket carries billed bytes
        # for every job in it. OR-folding would let one new-format bucket in a mixed
        # export flip the whole window to a billed total that covers only the carrying
        # jobs — silently dropping every legacy job's scan volume. All-or-nothing degrades
        # safely: mixed windows fall back to processed bytes (a labelled overestimate
        # rather than a silent underestimate).
        has_billed_bytes = True
        hour_slot_ms: dict[datetime, int] = defaultdict(int)
        slot_dates: set = set()
        all_dates: set = set()
        for b in buckets:
            ms = b["total_slot_ms"]
            total_slot_ms += ms
            total_bytes_processed += b.get("total_bytes_processed", 0)
            total_bytes_billed += b.get("total_bytes_billed", 0)
            total_queries += b.get("job_count", 1)
            has_billed_bytes = has_billed_bytes and b.get("has_billed_bytes", False)
            hour = b["hour_bucket"]
            hour_slot_ms[hour] += ms
            all_dates.add(hour.date())
            if ms > 0:
                slot_dates.add(hour.date())

        # days_sampled = distinct UTC dates with a slot-bearing job (>=1 so denominators hold).
        days_sampled = max(len(slot_dates), 1)

        # lookback_days = calendar span from first to last job date (for QPD denominator).
        if all_dates:
            lookback_days = max((max(all_dates) - min(all_dates)).days + 1, 1)
        else:
            lookback_days = days_sampled

        # Per-hour concurrency series over [first, last] active hour, idle hours zero-filled.
        # Sort once; derive peak/p50/p99 from the single ordered series.
        ordered = sorted(_hourly_series(hour_slot_ms))
        peak_slots = ordered[-1] if ordered else 0.0
        p50_slots = _percentile(ordered, 50)
        p99_slots = _percentile(ordered, 99)

        avg_slots = total_slot_ms / (days_sampled * _DAY_MS)

        busy_hours = sum(1 for ms in hour_slot_ms.values() if ms > 0)
        active_hour_fraction = min(1.0, max(0.0, busy_hours / (days_sampled * 24)))

        return SlotUtilization(
            avg_slots=avg_slots,
            p50_slots=p50_slots,
            p99_slots=p99_slots,
            peak_slots=peak_slots,
            active_hour_fraction=active_hour_fraction,
            total_slot_ms=total_slot_ms,
            days_sampled=days_sampled,
            total_bytes_processed=total_bytes_processed,
            total_bytes_billed=total_bytes_billed,
            has_billed_bytes=has_billed_bytes,
            total_queries=total_queries,
            lookback_days=lookback_days,
        )


def _normalize_entries(rows) -> list[dict]:
    """Normalize dual-format rows (dict or BigQuery Row) into merged hourly buckets.

    The single normalizer behind BOTH input paths (live API rows, file entries), so the
    format dispatch and the billed-basis rule exist exactly once:
    - a parseable ``hour_bucket`` value (datetime live, ISO string in a file) → hourly
      bucket; a null/unparseable ``hour_bucket`` falls through to ``creation_time``
      rather than dropping the entry.
    - a parseable ``creation_time`` → single-job bucket, merged client-side.

    ``missing_billed_jobs`` = jobs in the bucket with no billed data: the explicit count
    on hourly rows, and 1 per per-job row whose billed value is NULL/absent — NULL from a
    live Row and an absent key in a file entry both mean "billed unavailable", never a
    genuine zero. A billed column absent from an hourly entry means no job in it carries
    billed data. The count rides on the bucket so the exporter can round-trip partial
    billed sums without laundering them into genuine zeros.
    """
    buckets: list[dict] = []
    for row in rows:
        hour_ts = _coerce_ts(_row_get(row, "hour_bucket", None))
        if hour_ts is not None:
            job_count = max(_safe_int(_row_get(row, "job_count", 1)), 1)
            billed_raw = _row_get(row, "total_bytes_billed", None)
            if billed_raw is None:
                missing = job_count
            else:
                missing = _missing_count(
                    _row_get(row, "missing_billed_jobs", 0), job_count
                )
            buckets.append({
                "hour_bucket": _hour_floor(hour_ts),
                "total_slot_ms": _safe_int(_row_get(row, "total_slot_ms", 0)),
                "job_count": job_count,
                "total_bytes_processed": _safe_int(_row_get(row, "total_bytes_processed", 0)),
                "total_bytes_billed": _safe_int(billed_raw),
                "missing_billed_jobs": missing,
                "has_billed_bytes": missing == 0,
            })
            continue
        fields = _per_job_fields(row)
        if fields is None:
            continue  # no usable timestamp in either format → unusable entry
        missing = 0 if fields["has_billed_bytes"] else 1
        buckets.append({
            "hour_bucket": _hour_floor(fields["creation_time"]),
            "total_slot_ms": fields["total_slot_ms"],
            "job_count": 1,
            "total_bytes_processed": fields["total_bytes_processed"],
            "total_bytes_billed": fields["total_bytes_billed"],
            "missing_billed_jobs": missing,
            "has_billed_bytes": missing == 0,
        })
    return _merge_buckets(_drop_outlier_buckets(buckets))


def _drop_outlier_buckets(buckets: list[dict]) -> list[dict]:
    """Drop buckets implausibly far (> ``_MAX_SPAN_HOURS``) from the median bucket hour.

    A parseable-but-corrupt timestamp (year 9999, epoch-zero) would otherwise stretch the
    zero-filled ``_hourly_series`` across millions of idle hours — an unbounded allocation
    from a single bad file entry. Anchoring on the median keeps the real workload and
    sheds the outlier regardless of which side it lands on. Dropping (vs clamping) keeps
    the corrupt entry's stats out of the curve entirely; the warning names the count.
    """
    if len(buckets) <= 1:
        return buckets
    hours = sorted(b["hour_bucket"] for b in buckets)
    median = hours[len(hours) // 2]
    kept = [
        b for b in buckets
        if abs((b["hour_bucket"] - median).total_seconds()) / 3600 <= _MAX_SPAN_HOURS
    ]
    if len(kept) < len(buckets):
        logger.warning(
            "Dropped %d workload entr%s with timestamps > %d hours from the median "
            "bucket (corrupt timestamps would unboundedly inflate the hourly series)",
            len(buckets) - len(kept), "y" if len(buckets) - len(kept) == 1 else "ies",
            _MAX_SPAN_HOURS,
        )
    return kept


def _per_job_fields(row) -> dict | None:
    """Coerce one per-job row (dict or BigQuery Row) to normalized fields; None if it
    has no usable ``creation_time``. The single place the per-job billed rule lives:
    a NULL/absent billed value means "billed unavailable", never a genuine zero."""
    creation = _coerce_ts(_row_get(row, "creation_time", None))
    if creation is None:
        return None
    billed_raw = _row_get(row, "total_bytes_billed", None)
    return {
        "total_slot_ms": _safe_int(_row_get(row, "total_slot_ms", 0)),
        "creation_time": creation,
        "total_bytes_processed": _safe_int(_row_get(row, "total_bytes_processed", 0)),
        "total_bytes_billed": _safe_int(billed_raw),
        "has_billed_bytes": billed_raw is not None,
    }


def _missing_count(raw, job_count: int) -> int:
    """Coerce a ``missing_billed_jobs`` value, degrading on garbage.

    A negative or non-numeric count is a corrupt signal about missing billed data — fail
    toward the processed-bytes fallback (all jobs missing), never toward asserting a
    billed-carrying basis (the silent-underestimate direction the policy forbids).
    Clamped to [0, job_count].
    """
    try:
        n = int(raw)
    except (ValueError, TypeError):
        return job_count
    if n < 0:
        return job_count
    return min(n, job_count)


def _bucket_missing(b: dict) -> int:
    """A bucket's missing-billed count, deriving from ``has_billed_bytes`` when the
    count is absent (pre-2026-07-08 bucket shape) — a legacy degraded bucket must not
    default to 0 and silently un-degrade on merge."""
    missing = b.get("missing_billed_jobs")
    if missing is not None:
        return missing
    return 0 if b.get("has_billed_bytes", False) else b.get("job_count", 1)


def _merge_buckets(buckets: list[dict]) -> list[dict]:
    """Merge bucket entries sharing an hour — the single accumulator for bucket fields.

    ``missing_billed_jobs`` sums across merged entries and ``has_billed_bytes`` is derived
    from it, so a merged bucket is billed-carrying iff every summarized job carried billed
    data (same rule as ``_normalize_entries``). Buckets lacking the count (legacy shape)
    derive it from their ``has_billed_bytes`` flag via ``_bucket_missing``.
    """
    if not buckets:
        return []
    by_hour: dict[datetime, dict] = {}
    for b in buckets:
        hour = b["hour_bucket"]
        m = by_hour.get(hour)
        if m is None:
            m = by_hour[hour] = dict(b)
            m["missing_billed_jobs"] = _bucket_missing(b)
            m["has_billed_bytes"] = m["missing_billed_jobs"] == 0
            continue
        m["total_slot_ms"] += b["total_slot_ms"]
        m["job_count"] += b.get("job_count", 1)
        m["total_bytes_processed"] += b.get("total_bytes_processed", 0)
        m["total_bytes_billed"] += b.get("total_bytes_billed", 0)
        m["missing_billed_jobs"] += _bucket_missing(b)
        m["has_billed_bytes"] = m["missing_billed_jobs"] == 0
    return list(by_hour.values())


def _coerce_ts(value):
    """Coerce a timestamp value (datetime from a live Row, ISO string from a file, or
    None) to a datetime; None if absent/unparseable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return _parse_iso8601(value)


def _hour_floor(dt: datetime) -> datetime:
    """Truncate a datetime to its UTC hour — the bucket key."""
    return _to_utc(dt).replace(minute=0, second=0, microsecond=0)


def _to_utc(dt):
    """Normalize a datetime to UTC; treat naive datetimes as already-UTC (Decision D3)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso8601(value):
    """Parse an ISO-8601 timestamp, tolerating a trailing ``Z``; return None if unparseable.

    ``datetime.fromisoformat`` only accepts the ``Z`` (Zulu) suffix on Python 3.11+, but the
    project supports 3.9+ and BigQuery exports stamp ``creation_time`` with ``Z`` — so normalize
    ``Z`` → ``+00:00`` first. Never raises (R17.3): a bad value yields None and is skipped.
    """
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _safe_int(value) -> int:
    """Coerce a value to a non-negative int; 0 on None/garbage/negative. Never raises (R17.3).

    Accepts float-formatted numeric strings ("3600000.0", "1e6") — third-party query-log
    exports (spreadsheet/CSV-mediated) stringify numbers that way, and zeroing them would
    silently erase compute from the curve (the underestimate direction the module forbids).
    """
    try:
        n = int(value)
    except (ValueError, TypeError, OverflowError):
        # OverflowError: json.loads accepts the bare Infinity literal → float('inf').
        try:
            n = int(float(value))
        except (ValueError, TypeError, OverflowError):
            return 0
    return n if n > 0 else 0


def _hourly_series(hour_slot_ms: dict) -> list[float]:
    """Concurrency per hour over [first, last] active hour, idle hours zero-filled.

    Concurrency in a bucket = slot_ms / 3.6M (a per-hour average, not instantaneous — JOBS
    carries no per-job duration). Bursty load ⇒ many zero hours ⇒ low P50, high peak.
    """
    if not hour_slot_ms:
        return []
    hours = sorted(hour_slot_ms)
    first, last = hours[0], hours[-1]
    span_hours = int((last - first).total_seconds() // 3600) + 1
    series = []
    for i in range(span_hours):
        bucket = first + timedelta(hours=i)
        series.append(hour_slot_ms.get(bucket, 0) / _HOUR_MS)
    return series


def _percentile(ordered: list[float], pct: int) -> float:
    """Percentile of a PRE-SORTED value series via linear interpolation (deterministic).

    Caller sorts once and passes the ordered series (peak/p50/p99 share one sort). Single-element
    (or empty) series return that value (or 0.0) — guards the n==1 case so the P21 test is stable.
    """
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def _row_get(row, key, default):
    """Read a column from either a dict or a BigQuery Row (attribute access)."""
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)
