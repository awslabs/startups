# Feature: bq-assess-lakehouse, issue 5.2: WorkloadAnalyzer (R17)
"""Unit tests for the Workload Analyzer (slot-time utilization curve).

Drives ``WorkloadAnalyzer.analyze_from_api`` / ``analyze_from_file`` (R17): extract
``total_slot_ms`` / ``total_bytes_processed`` / ``creation_time`` over the lookback window,
compute the avg/P50/P99/peak slot curve + active-hour fraction, and return ``None`` (never a
zero-struct, never raise) when there is no usable workload — the ``None`` that trips the
LOW-confidence cost range downstream (R18.4).

Locked metric decisions (see SCRUM_NOTES § Issue 5.2):
- days_sampled = distinct UTC dates with a slot-bearing job
- avg_slots = total_slot_ms / (days_sampled * 86_400_000)
- per-hour slot series over [first, last] active hour with idle zero-fill → P50/P99/peak
- active_hour_fraction = busy_hours / (days_sampled * 24), clamped [0, 1]
"""

from __future__ import annotations

from datetime import datetime, timezone

from google.api_core.exceptions import Forbidden

from bq_assess.core.workload import WorkloadAnalyzer
from bq_assess.models import SlotUtilization


class _FakeQueryJob:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def result(self):
        return iter(self._rows)


class _FakeClient:
    """BigQuery client double: returns canned JOBS rows, or raises *query_error*."""

    def __init__(self, *, rows: list[dict] | None = None, query_error: Exception | None = None) -> None:
        self._rows = rows if rows is not None else []
        self._query_error = query_error
        self.queries: list[str] = []

    def query(self, sql: str, *args, **kwargs) -> _FakeQueryJob:
        self.queries.append(sql)
        if self._query_error is not None:
            raise self._query_error
        return _FakeQueryJob(self._rows)


def _job(*, slot_ms=3_600_000, bytes_=10**9, creation_time=None):
    """Build one JOBS row dict for a deterministic unit test."""
    return {
        "total_slot_ms": slot_ms,
        "total_bytes_processed": bytes_,
        "creation_time": creation_time or datetime(2025, 6, 1, 10, tzinfo=timezone.utc),
    }


def _analyze(rows, *, days=30, location="US"):
    slots, _raw = WorkloadAnalyzer().analyze_from_api(_FakeClient(rows=rows), "proj", days=days, location=location)
    return slots


# --- No-data contract (load-bearing: feeds R18.4 cost range) --------------------------

def test_empty_jobs_returns_none() -> None:
    """No jobs → None (not a zero-struct, no raise). This None trips the cost range (R18.4)."""
    assert _analyze([]) is None


# --- Core metric computation ----------------------------------------------------------

def test_single_job_one_bucket_curve() -> None:
    """One job of exactly one slot-hour in a single UTC hour → unit curve, 1 day sampled."""
    result = _analyze([_job(slot_ms=3_600_000)])

    assert isinstance(result, SlotUtilization)
    assert result.total_slot_ms == 3_600_000          # verbatim sum
    assert result.days_sampled == 1
    # One bucket carrying one slot-hour ⇒ concurrency 1.0 everywhere on the curve.
    assert result.p50_slots == 1.0
    assert result.p99_slots == 1.0
    assert result.peak_slots == 1.0


def test_total_slot_ms_is_verbatim_sum() -> None:
    """total_slot_ms is the plain integer sum — no conversion."""
    jobs = [_job(slot_ms=10), _job(slot_ms=20), _job(slot_ms=30)]
    assert _analyze(jobs).total_slot_ms == 60


_HOUR = 3_600_000


def _at(day, hour):
    return datetime(2025, 6, day, hour, tzinfo=timezone.utc)


def test_all_curve_metrics_present_and_typed() -> None:
    """avg/p50/p99/peak/fraction are floats; total_slot_ms/days_sampled are ints (R17.2)."""
    r = _analyze([_job(creation_time=_at(1, 10)), _job(creation_time=_at(1, 11))])
    for v in (r.avg_slots, r.p50_slots, r.p99_slots, r.peak_slots, r.active_hour_fraction):
        assert isinstance(v, float)
    assert isinstance(r.total_slot_ms, int)
    assert isinstance(r.days_sampled, int)


def test_curve_ordering_invariant() -> None:
    """p50 <= p99 <= peak holds (P21). avg is NOT constrained — bursty loads break avg<=p50."""
    jobs = [
        _job(slot_ms=1 * _HOUR, creation_time=_at(1, 0)),
        _job(slot_ms=5 * _HOUR, creation_time=_at(1, 1)),
        _job(slot_ms=9 * _HOUR, creation_time=_at(1, 2)),
    ]
    r = _analyze(jobs)
    assert r.p50_slots <= r.p99_slots <= r.peak_slots


def test_active_hour_fraction_in_unit_interval() -> None:
    """active_hour_fraction is bounded [0,1] (P21) and low for a clustered workload."""
    # One busy hour, but jobs land on 3 distinct dates → days_sampled=3 → 72 nominal hours.
    jobs = [
        _job(creation_time=_at(1, 9)),
        _job(creation_time=_at(2, 9)),
        _job(creation_time=_at(3, 9)),
    ]
    r = _analyze(jobs)
    assert 0.0 <= r.active_hour_fraction <= 1.0
    assert r.days_sampled == 3
    # 3 busy hours / (3 days * 24h) = 3/72.
    assert r.active_hour_fraction == 3 / 72


def test_all_zero_slot_ms_yields_zero_curve_not_none() -> None:
    """Jobs present but every slot_ms==0 → zero curve, NOT None (jobs existed)."""
    jobs = [_job(slot_ms=0, creation_time=_at(1, 10)), _job(slot_ms=0, creation_time=_at(1, 11))]
    r = _analyze(jobs)
    assert r is not None
    assert r.avg_slots == 0.0
    assert r.peak_slots == 0.0
    assert r.active_hour_fraction == 0.0       # busy = slot_ms>0, so no busy hours


def test_clustered_load_peak_exceeds_avg_and_p50_is_low() -> None:
    """A spike in one hour across a multi-day window: peak >> avg, and idle zero-fill → P50≈0.
    This is the over-provisioning signal the cost step reads (D1a/D1c)."""
    # 10 slot-hours all in a single hour on day 1; nothing else, but window spans to day 3.
    jobs = [_job(slot_ms=10 * 3_600_000, creation_time=_at(1, 9)),
            _job(slot_ms=0, creation_time=_at(3, 9))]
    r = _analyze(jobs)
    assert r.peak_slots == 10.0
    assert r.peak_slots > r.avg_slots          # spike dwarfs the day-normalized average
    assert r.p50_slots == 0.0                  # most hours in the span are idle (zero-fill)


# --- API read: SQL shape + graceful degradation (R17.1, R17.3) ------------------------

def test_api_sql_pulls_fields_over_lookback() -> None:
    """The api query selects the slot fields it consumes from the whole-project view over
    `days`, excluding SCRIPT parents (R17.1; project/region-qualified, location matches pricing)."""
    client = _FakeClient(rows=[_job()])
    WorkloadAnalyzer().analyze_from_api(client, "proj", days=30, location="EU")
    sql = client.queries[0]
    assert "total_slot_ms" in sql
    assert "creation_time" in sql
    # Whole-project view (not the per-user JOBS alias), project- and region-qualified.
    assert "`proj`.`region-eu`.INFORMATION_SCHEMA.JOBS_BY_PROJECT" in sql
    assert "INTERVAL 30 DAY" in sql
    assert "statement_type != 'SCRIPT'" in sql


def test_missing_jobs_listall_returns_none_no_raise() -> None:
    """Missing bigquery.jobs.listAll (Forbidden) → (None, []), never raises (R17.3 degradation).
    The descriptive permission message is the CLI's job (R17.3 names THE CLI)."""
    client = _FakeClient(query_error=Forbidden("403 Access Denied: bigquery.jobs.listAll"))
    slots, raw = WorkloadAnalyzer().analyze_from_api(client, "proj")
    assert slots is None
    assert raw == []


def test_rows_with_null_creation_time_are_skipped() -> None:
    """A row whose creation_time is NULL can't be bucketed → skipped; null slot_ms → 0."""
    jobs = [
        {"total_slot_ms": None, "total_bytes_processed": 0, "creation_time": _at(1, 10)},
        {"total_slot_ms": _HOUR, "total_bytes_processed": 0, "creation_time": None},
    ]
    r = _analyze(jobs)
    # Only the first row is usable (second has no timestamp); its null slot_ms coerces to 0.
    assert r is not None
    assert r.total_slot_ms == 0


# --- File path: analyze_from_file (R1.3 --query-logs, R17.4) --------------------------

import json  # noqa: E402


def _write(tmp_path, obj):
    p = tmp_path / "jobs.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def test_file_missing_returns_none(tmp_path) -> None:
    """A nonexistent path → (None, []) (no raise; diverges from analyzer.py per the | None contract)."""
    slots, raw = WorkloadAnalyzer().analyze_from_file(tmp_path / "nope.json")
    assert slots is None
    assert raw == []


def test_file_malformed_or_unusable_object_returns_none(tmp_path) -> None:
    """Invalid JSON → (None, []). A bare JSON object is accepted as a one-entry log
    (2026-07-08: a single-line JSONL export parses as a bare dict) but still yields
    (None, []) when the entry carries no usable timestamp."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    slots, raw = WorkloadAnalyzer().analyze_from_file(bad)
    assert slots is None
    assert raw == []
    slots2, raw2 = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, {"a": 1}))
    assert slots2 is None
    assert raw2 == []


def test_file_bare_object_with_valid_bucket_is_accepted(tmp_path) -> None:
    """A single-line jobs_hourly.jsonl export parses as a bare JSON object — it must be
    treated as a one-entry log, not rejected as an invalid format (2026-07-08 fix; the
    exporter round-trip depends on it)."""
    entry = {"hour_bucket": "2025-06-02T09:00:00Z", "total_slot_ms": _HOUR,
             "job_count": 2, "total_bytes_processed": 10**9, "total_bytes_billed": 10**9}
    slots, raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entry))
    assert slots is not None
    assert slots.total_queries == 2
    assert len(raw) == 1


def test_file_empty_array_returns_none(tmp_path) -> None:
    """An empty array → no usable jobs → (None, [])."""
    slots, raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, []))
    assert slots is None
    assert raw == []


def test_file_all_unusable_entries_returns_none(tmp_path) -> None:
    """A non-empty array whose entries all lack a usable creation_time → (None, [])."""
    entries = [{"total_slot_ms": 100, "creation_time": "not-a-date"},
               {"total_slot_ms": 200}]
    slots, raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    assert slots is None
    assert raw == []


def test_file_and_api_parity(tmp_path) -> None:
    """The same logical jobs via file and api produce field-identical SlotUtilization —
    one shared normalizer behind both paths, including the billed-basis rule."""
    times = [_at(1, 9), _at(1, 10), _at(2, 9)]
    api_rows = [
        {**_job(slot_ms=_HOUR, creation_time=t), "total_bytes_billed": 0} for t in times
    ]
    file_entries = [
        {"total_slot_ms": _HOUR, "total_bytes_processed": 10**9, "total_bytes_billed": 0,
         "creation_time": t.isoformat()}
        for t in times
    ]
    api_result = _analyze(api_rows)
    file_result, _raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, file_entries))
    assert file_result == api_result


def test_api_per_job_rows_without_billed_key_degrade(tmp_path) -> None:
    """Per-job shaped API rows lacking the billed column degrade the window — the same
    'absent means unavailable' rule as file entries, NOT a hardcoded billed basis
    (2026-07-08 review: the old hardcoded True zeroed the scan estimate for NULL-billed
    jobs). Same rows WITH billed keep the basis."""
    without = _analyze([_job(slot_ms=_HOUR)])
    assert without is not None
    assert without.has_billed_bytes is False
    with_billed = _analyze([{**_job(slot_ms=_HOUR), "total_bytes_billed": 5 * 10**8}])
    assert with_billed is not None
    assert with_billed.has_billed_bytes is True
    assert with_billed.total_bytes_billed == 5 * 10**8


def test_file_naive_and_aware_timestamps_bucket_together(tmp_path) -> None:
    """A naive timestamp is treated as UTC (D3), bucketing with its explicit +00:00 twin."""
    entries = [
        {"total_slot_ms": _HOUR, "creation_time": "2025-06-01T10:00:00"},        # naive
        {"total_slot_ms": _HOUR, "creation_time": "2025-06-01T10:30:00+00:00"},  # aware, same hr
    ]
    r, _raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    # Both land in the single 10:00 UTC bucket → 2 slot-hours in one hour → peak 2.0.
    assert r is not None
    assert r.peak_slots == 2.0


def test_file_zulu_suffix_timestamps_parse(tmp_path) -> None:
    """BigQuery exports stamp creation_time with a trailing 'Z' — must parse on py3.9+ (review #3)."""
    entries = [
        {"total_slot_ms": _HOUR, "creation_time": "2025-06-01T10:00:00Z"},
        {"total_slot_ms": _HOUR, "creation_time": "2025-06-01T10:30:00.123456Z"},
    ]
    r, _raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    assert r is not None                       # NOT silently dropped → None
    assert r.peak_slots == 2.0                 # both land in the same UTC hour bucket


def test_file_non_numeric_slot_ms_does_not_raise(tmp_path) -> None:
    """A non-numeric total_slot_ms degrades to 0, never raises (review #8)."""
    entries = [
        {"total_slot_ms": "not-a-number", "creation_time": "2025-06-01T10:00:00Z"},
        {"total_slot_ms": -500, "creation_time": "2025-06-01T11:00:00Z"},   # negative clamps to 0
    ]
    r, _raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    assert r is not None
    assert r.total_slot_ms == 0                # garbage → 0, negative → 0


def test_file_query_text_is_anonymized(tmp_path) -> None:
    """R17.4/R22.4: a `query` field in the export is anonymized (literals stripped) — reuses
    QueryAnalyzer.anonymize_query rather than re-implementing the regex."""
    analyzer = WorkloadAnalyzer()
    raw = "SELECT * FROM t WHERE name = 'secret' AND n = 42"
    cleaned = analyzer.anonymize_query(raw)
    assert "secret" not in cleaned
    assert "42" not in cleaned
    assert "'?'" in cleaned


def test_mixed_export_degrades_to_processed_fallback(tmp_path) -> None:
    """One new-format job in a legacy export must NOT flip the window to the billed basis
    (that would silently drop every legacy job's scan volume) — all-or-nothing."""
    entries = [
        {"total_slot_ms": _HOUR, "total_bytes_processed": 10**12,
         "creation_time": _at(1, 9).isoformat()},                      # legacy: no billed
        {"total_slot_ms": _HOUR, "total_bytes_processed": 10**9,
         "total_bytes_billed": 0, "creation_time": _at(1, 10).isoformat()},  # new format
    ]
    slots, _ = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    assert slots is not None
    assert slots.has_billed_bytes is False


def test_all_carrying_export_keeps_billed_basis(tmp_path) -> None:
    entries = [
        {"total_slot_ms": _HOUR, "total_bytes_processed": 10**9,
         "total_bytes_billed": 0, "creation_time": _at(1, 9).isoformat()},
        {"total_slot_ms": _HOUR, "total_bytes_processed": 10**9,
         "total_bytes_billed": 2 * 10**9, "creation_time": _at(1, 10).isoformat()},
    ]
    slots, _ = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    assert slots is not None
    assert slots.has_billed_bytes is True
    assert slots.total_bytes_billed == 2 * 10**9


# --- Hourly aggregation (2026-07-08 storm audit: 10 PB-scale OOM fix) ------------------

def test_api_reads_hourly_aggregates() -> None:
    """The live path GROUPs BY hour server-side — bounded rows regardless of query volume."""
    client = _FakeClient(rows=[])
    WorkloadAnalyzer().analyze_from_api(client, "proj", days=30, location="US")
    sql = client.queries[0]
    assert "TIMESTAMP_TRUNC(creation_time, HOUR)" in sql
    assert "GROUP BY hour_bucket" in sql
    assert "SUM(total_slot_ms)" in sql
    assert "COUNTIF(total_bytes_billed IS NULL)" in sql
    # user_email must NOT cross the wire on the aggregated path.
    assert "user_email" not in sql


def test_hourly_rows_produce_same_curve_as_per_job_rows() -> None:
    """Equivalence: pre-aggregated hourly rows yield the same SlotUtilization as the
    per-job rows they summarize — aggregation is output-identical, the audit's key claim."""
    t0 = datetime(2025, 6, 2, 9, tzinfo=timezone.utc)
    per_job = [
        {"total_slot_ms": _HOUR, "total_bytes_processed": 10**9,
         "total_bytes_billed": 2 * 10**9, "creation_time": t0},
        {"total_slot_ms": 2 * _HOUR, "total_bytes_processed": 3 * 10**9,
         "total_bytes_billed": 10**9, "creation_time": t0.replace(minute=30)},
        {"total_slot_ms": _HOUR, "total_bytes_processed": 10**9,
         "total_bytes_billed": 10**9, "creation_time": t0.replace(hour=14)},
    ]
    hourly = [
        {"hour_bucket": t0, "total_slot_ms": 3 * _HOUR, "job_count": 2,
         "total_bytes_processed": 4 * 10**9, "total_bytes_billed": 3 * 10**9,
         "missing_billed_jobs": 0},
        {"hour_bucket": t0.replace(hour=14), "total_slot_ms": _HOUR, "job_count": 1,
         "total_bytes_processed": 10**9, "total_bytes_billed": 10**9,
         "missing_billed_jobs": 0},
    ]
    from_jobs, _ = WorkloadAnalyzer().analyze_from_api(_FakeClient(rows=per_job), "proj")
    from_hourly, _ = WorkloadAnalyzer().analyze_from_api(_FakeClient(rows=hourly), "proj")
    assert from_jobs == from_hourly


def test_hourly_bucket_with_missing_billed_degrades_window() -> None:
    """missing_billed_jobs > 0 in ANY bucket flips the window off the billed basis —
    same all-or-nothing rule as the per-job fold."""
    rows = [
        {"hour_bucket": datetime(2025, 6, 2, 9, tzinfo=timezone.utc),
         "total_slot_ms": _HOUR, "job_count": 5, "total_bytes_processed": 10**9,
         "total_bytes_billed": 10**9, "missing_billed_jobs": 0},
        {"hour_bucket": datetime(2025, 6, 2, 10, tzinfo=timezone.utc),
         "total_slot_ms": _HOUR, "job_count": 5, "total_bytes_processed": 10**9,
         "total_bytes_billed": 10**9, "missing_billed_jobs": 2},
    ]
    slots, _ = WorkloadAnalyzer().analyze_from_api(_FakeClient(rows=rows), "proj")
    assert slots is not None
    assert slots.has_billed_bytes is False
    assert slots.total_queries == 10


def test_file_accepts_hourly_aggregate_format(tmp_path) -> None:
    """analyze_from_file consumes the exporter's hourly format (hour_bucket key)."""
    entries = [
        {"hour_bucket": "2025-06-02T09:00:00Z", "total_slot_ms": 2 * _HOUR,
         "job_count": 3, "total_bytes_processed": 10**9, "total_bytes_billed": 10**9},
        {"hour_bucket": "2025-06-02T11:00:00Z", "total_slot_ms": _HOUR,
         "job_count": 1, "total_bytes_processed": 10**9, "total_bytes_billed": 0},
    ]
    slots, raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    assert slots is not None
    assert slots.total_queries == 4
    assert slots.total_slot_ms == 3 * _HOUR
    assert slots.has_billed_bytes is True      # both entries carry the billed key
    assert slots.peak_slots == 2.0
    assert len(raw) == 2


def test_file_mixed_hourly_and_per_job_entries_merge(tmp_path) -> None:
    """A concatenated export (hourly + legacy per-job) merges into one window."""
    entries = [
        {"hour_bucket": "2025-06-02T09:00:00Z", "total_slot_ms": _HOUR,
         "job_count": 2, "total_bytes_processed": 10**9, "total_bytes_billed": 10**9},
        {"total_slot_ms": _HOUR, "total_bytes_processed": 10**9,
         "creation_time": "2025-06-02T09:30:00Z"},   # legacy, same hour, no billed key
    ]
    slots, raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    assert slots is not None
    assert slots.total_queries == 3
    assert slots.total_slot_ms == 2 * _HOUR
    assert slots.has_billed_bytes is False     # legacy entry lacks billed → window degrades
    assert len(raw) == 1                        # merged into one bucket


# --- 2026-07-08 review fixes (hourly-aggregation merge) ---------------------------------

def test_file_null_hour_bucket_falls_back_to_creation_time(tmp_path) -> None:
    """An entry with hour_bucket=null but a valid creation_time is consumed via the
    per-job branch, not dropped (review: key-presence dispatch lost whole workloads
    from producers emitting both columns)."""
    entries = [
        {"hour_bucket": None, "creation_time": "2025-06-02T09:30:00Z",
         "total_slot_ms": _HOUR, "total_bytes_processed": 10**9},
        {"hour_bucket": None, "creation_time": "2025-06-02T10:30:00Z",
         "total_slot_ms": _HOUR, "total_bytes_processed": 10**9},
    ]
    slots, raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    assert slots is not None
    assert slots.total_queries == 2
    assert slots.total_slot_ms == 2 * _HOUR


def test_partial_billed_bucket_keeps_sum_and_degrades(tmp_path) -> None:
    """A bucket with a partial billed sum (missing_billed_jobs > 0 but < job_count)
    keeps the sum in the window total while degrading the basis — and the count
    round-trips through the exporter (review: dropping the value flipped the cost
    basis between a live run and its re-imported export)."""
    entries = [
        {"hour_bucket": "2025-06-02T09:00:00Z", "total_slot_ms": _HOUR, "job_count": 10,
         "total_bytes_processed": 10**12, "total_bytes_billed": 8 * 10**11,
         "missing_billed_jobs": 2},
    ]
    slots, raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    assert slots is not None
    assert slots.has_billed_bytes is False           # degraded basis
    assert slots.total_bytes_billed == 8 * 10**11    # partial sum preserved
    assert raw[0]["missing_billed_jobs"] == 2


def test_per_job_null_billed_is_unavailable_not_zero() -> None:
    """The per-job billed rule (_per_job_fields): an explicit NULL billed value means
    'unavailable' and degrades the window, while a genuine 0 from a carrying source
    keeps the billed basis (review: NULL must never launder into $0 billed)."""
    t = datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc)
    null_billed = _analyze([{"total_slot_ms": _HOUR, "creation_time": t,
                             "total_bytes_processed": 10**9, "total_bytes_billed": None}])
    assert null_billed is not None
    assert null_billed.has_billed_bytes is False    # NULL → unavailable
    genuine_zero = _analyze([{"total_slot_ms": _HOUR, "creation_time": t,
                              "total_bytes_processed": 10**9, "total_bytes_billed": 0}])
    assert genuine_zero is not None
    assert genuine_zero.has_billed_bytes is True    # genuine 0 → carrying


def test_garbage_missing_billed_count_degrades_not_promotes(tmp_path) -> None:
    """A corrupt missing_billed_jobs (negative / non-numeric) is a broken signal about
    missing billed data — it must degrade the window (fail toward the processed
    overestimate), never assert a billed-carrying basis (2026-07-08 review: _safe_int's
    clamp-to-0 promoted garbage to has_billed_bytes=True with billed=0, which cost.py
    reads as a genuine $0 scan month)."""
    for garbage in (-2, "not-a-number"):
        entries = [
            {"hour_bucket": "2025-06-02T09:00:00Z", "total_slot_ms": _HOUR,
             "job_count": 10, "total_bytes_processed": 10**9,
             "total_bytes_billed": 0, "missing_billed_jobs": garbage},
        ]
        slots, raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
        assert slots is not None
        assert slots.has_billed_bytes is False, f"garbage={garbage!r} must degrade"
        assert raw[0]["missing_billed_jobs"] == 10


def test_corrupt_far_future_timestamp_is_dropped_not_series_inflating(tmp_path) -> None:
    """A parseable-but-corrupt timestamp (year 9999) must be DROPPED, not zero-fill the
    hourly series across ~70M idle hours — the OOM class the hourly aggregation was
    built to remove (2026-07-08 storm assess, MRI-4). The real workload survives."""
    entries = [
        {"hour_bucket": "2025-06-02T09:00:00Z", "total_slot_ms": _HOUR, "job_count": 1,
         "total_bytes_processed": 10**9},
        {"hour_bucket": "2025-06-02T10:00:00Z", "total_slot_ms": _HOUR, "job_count": 1,
         "total_bytes_processed": 10**9},
        {"hour_bucket": "9999-01-01T00:00:00Z", "total_slot_ms": 1, "job_count": 1,
         "total_bytes_processed": 1},
    ]
    slots, raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    assert slots is not None
    assert slots.total_queries == 2                 # outlier's stats excluded entirely
    assert slots.total_slot_ms == 2 * _HOUR
    assert len(raw) == 2
    # Epoch-adjacent outlier drops the same way (outlier on the other side of median).
    entries[2] = {"hour_bucket": "1970-01-01T00:00:00Z", "total_slot_ms": 1,
                  "job_count": 1, "total_bytes_processed": 1}
    slots2, raw2 = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    assert slots2 is not None
    assert slots2.total_queries == 2
    assert len(raw2) == 2


def test_single_entry_workload_is_never_dropped_as_outlier(tmp_path) -> None:
    """The outlier guard is relative to the median — a one-entry workload has no peers
    to be an outlier against and must pass through untouched."""
    entries = [{"hour_bucket": "2025-06-02T09:00:00Z", "total_slot_ms": _HOUR,
                "job_count": 3, "total_bytes_processed": 10**9}]
    slots, raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    assert slots is not None
    assert slots.total_queries == 3
    assert len(raw) == 1


def test_float_formatted_numeric_strings_are_parsed_not_zeroed(tmp_path) -> None:
    """Float-formatted numeric strings ("3600000.0", "1e6") from spreadsheet-mediated
    exports must parse, not silently zero the compute curve — the underestimate
    direction the module forbids (2026-07-08 storm assess, MRI-5). True garbage still
    coerces to 0."""
    from bq_assess.core.workload import _safe_int

    entries = [
        {"hour_bucket": "2025-06-02T09:00:00Z", "total_slot_ms": "3600000.0",
         "job_count": "2.0", "total_bytes_processed": "1e9"},
    ]
    slots, raw = WorkloadAnalyzer().analyze_from_file(_write(tmp_path, entries))
    assert slots is not None
    assert slots.total_slot_ms == _HOUR
    assert slots.total_queries == 2
    assert slots.total_bytes_processed == 10**9
    assert _safe_int("not-a-number") == 0
    assert _safe_int(float("inf")) == 0
    assert _safe_int(float("nan")) == 0


def test_merge_preserves_degraded_legacy_bucket() -> None:
    """_merge_buckets must not un-degrade a legacy-shaped bucket (has_billed_bytes=False,
    no missing_billed_jobs key) when merging — the count is derived from the flag, not
    defaulted to 0 (2026-07-08 review: the 0-default silently flipped merged degraded
    buckets to billed-carrying)."""
    from bq_assess.core.workload import _merge_buckets

    hour = datetime(2025, 6, 2, 9, tzinfo=timezone.utc)
    legacy_degraded = {"hour_bucket": hour, "total_slot_ms": _HOUR, "job_count": 2,
                       "total_bytes_processed": 10**9, "total_bytes_billed": 0,
                       "has_billed_bytes": False}   # pre-2026-07-08 shape: no count
    clean = {"hour_bucket": hour, "total_slot_ms": _HOUR, "job_count": 3,
             "total_bytes_processed": 10**9, "total_bytes_billed": 10**9,
             "missing_billed_jobs": 0, "has_billed_bytes": True}
    for ordering in ([legacy_degraded, clean], [clean, legacy_degraded]):
        merged = _merge_buckets(list(ordering))
        assert len(merged) == 1
        assert merged[0]["has_billed_bytes"] is False, f"order={ordering[0]['job_count']}"
        assert merged[0]["missing_billed_jobs"] == 2
