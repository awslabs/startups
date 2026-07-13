# Feature: bq-assess-lakehouse, Property 3: Dataset filter scoping
# Feature: bq-assess-lakehouse, Property 4: Scanned metadata completeness
# Feature: bq-assess-lakehouse, Property 5: Entity classification partitions the population
# Feature: bq-assess-lakehouse, Property 7: Range partitioning is captured distinctly
# Feature: bq-assess-lakehouse, Property 27: Scanner retry on transient errors
# Feature: bq-assess-lakehouse, Property 28: Pipeline resilience
"""Property-based tests for the scanner and entity classification (issue #8 / 1.3).

Realizes the design.md correctness properties for Phase 1 ingestion:

- **P3** dataset filter scoping            — Validates R3.4
- **P4** scanned metadata completeness     — Validates R3.1, R3.2, R3.3
- **P5** classification partition          — Validates R4.1, R4.2, R4.3
- **P7** range partitioning captured       — Validates R3.8
- **P27** scanner retry on transient errors — Validates R23.1
- **P28** pipeline resilience              — Validates R23.2

Each property is realized by exactly one Hypothesis test. Scanner tests drive a mocked
BigQuery client; classification (P5) exercises the real ``core/classifier``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import hypothesis.strategies as st
import pytest
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import bigquery
from hypothesis import HealthCheck, assume, given, settings

from bq_assess.core.classifier import classify_population
from bq_assess.core.scanner import BigQueryScanner, _retry
from bq_assess.models import EntityPopulation, EntityType

_identifier = st.from_regex(r"[a-z][a-z0-9_]{0,9}", fullmatch=True)


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------


def _make_scanner() -> BigQueryScanner:
    scanner = BigQueryScanner(project_id="prop-project", use_adc=True)
    scanner._client = MagicMock(spec=bigquery.Client)
    scanner._client.list_routines.return_value = []
    return scanner


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


def _make_schema_field(name: str, field_type: str = "STRING", mode: str = "NULLABLE"):
    sf = MagicMock(spec=bigquery.SchemaField)
    sf.name = name
    sf.field_type = field_type
    sf.mode = mode
    sf.fields = []
    return sf


def _make_table(
    dataset_id: str,
    table_id: str,
    *,
    num_rows: int = 100,
    num_bytes: int = 2048,
    table_type: str = "TABLE",
    range_partitioning=None,
):
    tbl = MagicMock(spec=bigquery.Table)
    tbl.table_id = table_id
    tbl.dataset_id = dataset_id
    tbl.table_type = table_type
    tbl.num_rows = num_rows
    tbl.num_bytes = num_bytes
    tbl.schema = [_make_schema_field("id", "INT64", "REQUIRED")]
    tbl.time_partitioning = None
    tbl.range_partitioning = range_partitioning
    tbl.clustering_fields = None
    tbl.view_query = None
    tbl.mview_query = None
    tbl.modified = datetime(2024, 6, 1, tzinfo=timezone.utc)
    return tbl


def _make_range_partitioning(field: str, start: int, end: int, interval: int):
    rng = MagicMock()
    rng.start = start
    rng.end = end
    rng.interval = interval
    rp = MagicMock()
    rp.field = field
    rp.range_ = rng
    return rp


# ---------------------------------------------------------------------------
# P3: Dataset filter scoping  — Validates R3.4
# ---------------------------------------------------------------------------


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    all_datasets=st.lists(_identifier, min_size=1, max_size=8, unique=True),
    filter_ratio=st.floats(min_value=0.1, max_value=1.0),
)
def test_p3_dataset_filter_scoping(all_datasets: list[str], filter_ratio: float):
    """A non-empty filter yields only matching datasets; no filter yields all."""
    scanner = _make_scanner()
    client = scanner._client
    client.list_datasets.return_value = [_make_dataset_list_item(d) for d in all_datasets]

    table_items = {d: _make_table_list_item(d, f"t_{d}") for d in all_datasets}
    table_objects = {id(tli.reference): _make_table(d, f"t_{d}") for d, tli in table_items.items()}
    client.list_tables.side_effect = lambda ds: [table_items[ds]] if ds in table_items else []
    client.get_table.side_effect = lambda ref: table_objects[id(ref)]

    n_filter = max(1, int(len(all_datasets) * filter_ratio))
    dataset_filter = all_datasets[:n_filter]

    filtered = {e.dataset_id for e in scanner.scan(dataset_filter=dataset_filter)}
    assert filtered == set(dataset_filter)

    scanner.failures = []
    all_scanned = {e.dataset_id for e in scanner.scan(dataset_filter=None)}
    assert all_scanned == set(all_datasets)


# ---------------------------------------------------------------------------
# P4: Scanned metadata completeness  — Validates R3.1, R3.2, R3.3
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    dataset_id=_identifier,
    table_id=_identifier,
    num_rows=st.integers(min_value=0, max_value=10**9),
    num_bytes=st.integers(min_value=0, max_value=10**12),
)
def test_p4_scanned_metadata_completeness(
    dataset_id: str, table_id: str, num_rows: int, num_bytes: int
):
    """Required fields are non-null; partition/clustering/SQL fields are present (may be None)."""
    scanner = _make_scanner()
    client = scanner._client
    client.list_datasets.return_value = [_make_dataset_list_item(dataset_id)]
    client.list_tables.return_value = [_make_table_list_item(dataset_id, table_id)]
    client.get_table.return_value = _make_table(
        dataset_id, table_id, num_rows=num_rows, num_bytes=num_bytes
    )

    results = list(scanner.scan())
    assert len(results) == 1
    meta = results[0]

    # Required fields non-null (design.md P4)
    assert meta.entity_id is not None
    assert meta.dataset_id is not None
    assert meta.full_name is not None
    assert meta.entity_type is not None
    assert meta.population is not None
    assert meta.num_bytes is not None
    assert meta.columns is not None and len(meta.columns) > 0

    # Partition/clustering/SQL fields present (attribute exists; value may be None)
    for attr in (
        "time_partitioning",
        "range_partitioning",
        "clustering_fields",
        "view_query",
        "mview_query",
        "routine",
        "last_modified",
    ):
        assert hasattr(meta, attr)


# ---------------------------------------------------------------------------
# P5: Entity classification partitions the population — Validates R4.1, R4.2, R4.3
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(entity_type=st.sampled_from(list(EntityType)))
def test_p5_classification_partitions_population(entity_type: EntityType):
    """population is TABLE iff type ∈ {TABLE, EXTERNAL}, else REBUILT — never both."""
    population = classify_population(entity_type)
    is_table_type = entity_type in (EntityType.TABLE, EntityType.EXTERNAL)

    if is_table_type:
        assert population is EntityPopulation.TABLE
    else:
        assert population is EntityPopulation.REBUILT

    # Exactly one population — the mapping is a function (no entity is both).
    assert population in (EntityPopulation.TABLE, EntityPopulation.REBUILT)
    assert (population is EntityPopulation.TABLE) == is_table_type


# ---------------------------------------------------------------------------
# P7: Range partitioning is captured distinctly — Validates R3.8
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    dataset_id=_identifier,
    table_id=_identifier,
    field=_identifier,
    start=st.integers(min_value=0, max_value=10**6),
    span=st.integers(min_value=1, max_value=10**6),
    interval=st.integers(min_value=1, max_value=10**5),
)
def test_p7_range_partitioning_captured(
    dataset_id, table_id, field, start, span, interval
):
    """A range-partitioned table populates range_partitioning and is not unpartitioned."""
    scanner = _make_scanner()
    client = scanner._client
    rp = _make_range_partitioning(field, start, start + span, interval)
    table = _make_table(dataset_id, table_id, range_partitioning=rp)  # time_partitioning stays None

    client.list_datasets.return_value = [_make_dataset_list_item(dataset_id)]
    client.list_tables.return_value = [_make_table_list_item(dataset_id, table_id)]
    client.get_table.return_value = table

    meta = next(iter(scanner.scan()))

    assert meta.range_partitioning is not None
    assert meta.range_partitioning.field == field
    assert meta.range_partitioning.start == start
    assert meta.range_partitioning.end == start + span
    assert meta.range_partitioning.interval == interval
    # Distinct from time partitioning — not mistaken for unpartitioned (R3.8)
    assert meta.time_partitioning is None
    is_unpartitioned = (
        meta.time_partitioning is None and meta.range_partitioning is None
    )
    assert not is_unpartitioned


# ---------------------------------------------------------------------------
# P27: Scanner retry on transient errors — Validates R23.1
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    status_code=st.sampled_from([429, 500, 503]),
    failures_before_success=st.integers(min_value=0, max_value=3),
)
@patch("bq_assess.core.scanner.time.sleep")
def test_p27_retry_then_succeeds(mock_sleep, status_code, failures_before_success):
    """Transient errors are retried with exponential backoff, at most 3 retries."""
    err = GoogleAPICallError(f"transient {status_code}")
    err.code = status_code

    calls = 0

    def fn():
        nonlocal calls
        calls += 1
        if calls <= failures_before_success:
            raise err
        return "ok"

    assert _retry(fn) == "ok"
    assert calls == failures_before_success + 1
    actual_delays = [c.args[0] for c in mock_sleep.call_args_list]
    assert len(actual_delays) == failures_before_success
    for i, actual in enumerate(actual_delays):
        base = 1.0 * (2.0 ** i)
        assert base * 0.5 <= actual <= base * 1.5


@settings(max_examples=50)
@given(status_code=st.sampled_from([429, 500, 503]))
@patch("bq_assess.core.scanner.time.sleep")
def test_p27_retry_caps_at_3_then_raises(mock_sleep, status_code):
    """A persistently failing transient error raises after exactly 3 retries (4 attempts)."""
    err = GoogleAPICallError(f"persistent {status_code}")
    err.code = status_code

    calls = 0

    def fn():
        nonlocal calls
        calls += 1
        raise err

    with pytest.raises(GoogleAPICallError):
        _retry(fn)
    assert calls == 4  # 1 initial + 3 retries
    assert mock_sleep.call_count == 3


# ---------------------------------------------------------------------------
# P28: Pipeline resilience — Validates R23.2
# ---------------------------------------------------------------------------


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    n_tables=st.integers(min_value=2, max_value=10),
    k_failures=st.integers(min_value=1, max_value=9),
)
@patch("bq_assess.core.scanner.time.sleep")
def test_p28_pipeline_resilience(mock_sleep, n_tables, k_failures):
    """K of N entities fail → (N−K) results yielded and exactly K FailureRecords."""
    assume(k_failures < n_tables)

    scanner = _make_scanner()
    client = scanner._client
    client.list_datasets.return_value = [_make_dataset_list_item("ds")]

    items = [_make_table_list_item("ds", f"t{i}") for i in range(n_tables)]
    client.list_tables.return_value = items

    fail_idx = set(range(k_failures))
    err = GoogleAPICallError("permanent")
    err.code = 400  # non-retryable → immediate per-entity failure
    ref_to_idx = {id(it.reference): i for i, it in enumerate(items)}

    def get_table(ref):
        idx = ref_to_idx[id(ref)]
        if idx in fail_idx:
            raise err
        return _make_table("ds", f"t{idx}")

    client.get_table.side_effect = get_table

    results = list(scanner.scan())

    assert len(results) == n_tables - k_failures
    assert len(scanner.failures) == k_failures
    for fr in scanner.failures:
        assert fr.entity_name is not None
        assert fr.stage == "scan"
        assert fr.error is not None
