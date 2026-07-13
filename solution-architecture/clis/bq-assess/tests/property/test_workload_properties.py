# Feature: bq-assess-lakehouse, Property 21: Slot utilization curve
"""Property-based test for the Workload Analyzer (issue 5.2 / 5.4).

Realizes the design.md correctness property for slot/workload analysis:

- **P21** slot utilization curve — Validates R17.1, R17.2

*For any* non-empty job set, ``SlotUtilization`` exposes avg/P50/P99/peak and an active-hour
fraction in ``[0, 1]`` derived from ``total_slot_ms`` and ``creation_time``. Inputs come from
the ``slot_jobs()`` strategy (conftest); a fake client returns the generated rows.
"""

from __future__ import annotations

from hypothesis import given, settings

from bq_assess.core.workload import WorkloadAnalyzer
from bq_assess.models import SlotUtilization
from tests.conftest import slot_jobs


class _FakeClient:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def query(self, sql: str, *args, **kwargs):
        rows = self._rows

        class _Job:
            def result(self_):
                return iter(rows)

        return _Job()


@settings(max_examples=200)
@given(jobs=slot_jobs())
def test_p21_slot_utilization_curve_invariants(jobs: list[dict]) -> None:
    """P21: for any non-empty job set the curve is well-defined and bounded."""
    result, raw_jobs = WorkloadAnalyzer().analyze_from_api(_FakeClient(jobs), "proj")

    # slot_jobs() always carries a usable creation_time, so a non-empty set never degrades.
    assert isinstance(result, SlotUtilization)

    # The active-hour fraction is a genuine fraction.
    assert 0.0 <= result.active_hour_fraction <= 1.0

    # Curve ordering invariant (avg is intentionally NOT constrained — bursty loads break it).
    assert result.p50_slots <= result.p99_slots <= result.peak_slots

    # total_slot_ms is the verbatim sum of inputs; all curve metrics are non-negative.
    assert result.total_slot_ms == sum(j["total_slot_ms"] for j in jobs)
    assert result.avg_slots >= 0.0
    assert result.peak_slots >= 0.0
    assert result.days_sampled >= 1

    # Hourly buckets returned for metadata export: every input job is counted, and the
    # bucket list never exceeds the job count (aggregation only merges, never invents).
    assert result.total_queries == len(jobs)
    assert 1 <= len(raw_jobs) <= len(jobs)
    assert all("hour_bucket" in b for b in raw_jobs)


@settings(max_examples=100)
@given(jobs=slot_jobs(min_size=0, max_size=0))
def test_p21_empty_returns_none(jobs: list[dict]) -> None:
    """No jobs → (None, []) (the no-data sentinel that trips the LOW-confidence cost range, R18.4)."""
    slots, raw = WorkloadAnalyzer().analyze_from_api(_FakeClient(jobs), "proj")
    assert slots is None
    assert raw == []
