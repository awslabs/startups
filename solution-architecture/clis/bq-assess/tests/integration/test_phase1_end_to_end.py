"""Phase 1 checkpoint (issue #12 / 1.7): scan → cache → load round-trip, end to end.

Drives the real ``BigQueryScanner`` (against a mocked BigQuery client) over a fixture
project containing the four entity kinds the checkpoint names — a plain/range-partitioned
TABLE, a VIEW, a MATERIALIZED_VIEW, and a JavaScript ROUTINE — then stores the scanned
``EntityMetadata`` in the real ``MetadataCache`` and loads it back, asserting the full
ingestion contract survives the round-trip.

No live BigQuery and no live filesystem cache beyond a tmp SQLite file — this is a wiring
test of scanner + classifier + cache together, not a unit test of any one of them.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from google.cloud import bigquery

from bq_assess.core.cache import MetadataCache
from bq_assess.core.scanner import BigQueryScanner
from bq_assess.models import EntityPopulation, EntityType


# ---------------------------------------------------------------------------
# Fixture: a mock BigQuery client describing one dataset with all four kinds
# ---------------------------------------------------------------------------

_DATASET = "sample_dataset"


def _schema_field(name, field_type="STRING", mode="NULLABLE", fields=()):
    sf = MagicMock(spec=bigquery.SchemaField)
    sf.name = name
    sf.field_type = field_type
    sf.mode = mode
    sf.fields = list(fields)
    return sf


def _table_list_item(table_id):
    item = MagicMock(spec=bigquery.table.TableListItem)
    item.dataset_id = _DATASET
    item.table_id = table_id
    item.reference = MagicMock(spec=bigquery.TableReference)
    item.reference._key = table_id  # marker so get_table can route
    return item


def _routine_list_item(routine_id):
    item = MagicMock()
    item.dataset_id = _DATASET
    item.routine_id = routine_id
    item.reference = MagicMock()
    item.reference._key = routine_id
    return item


def _range_partitioned_table():
    tbl = MagicMock(spec=bigquery.Table)
    tbl.table_id = "orders"
    tbl.dataset_id = _DATASET
    tbl.table_type = "TABLE"
    tbl.num_rows = 1_000_000
    tbl.num_bytes = 5_000_000
    tbl.schema = [
        _schema_field("order_id", "INT64", "REQUIRED"),
        _schema_field("customer_id", "INT64", "REQUIRED"),
        _schema_field(
            "items",
            "STRUCT",
            "REPEATED",
            fields=[_schema_field("sku", "STRING"), _schema_field("qty", "INT64")],
        ),
    ]
    tbl.time_partitioning = None
    rng = MagicMock()
    rng.start, rng.end, rng.interval = 0, 1000, 10
    rp = MagicMock()
    rp.field = "customer_id"
    rp.range_ = rng
    tbl.range_partitioning = rp
    tbl.clustering_fields = ["customer_id"]
    tbl.view_query = None
    tbl.mview_query = None
    tbl.modified = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return tbl


def _view():
    tbl = MagicMock(spec=bigquery.Table)
    tbl.table_id = "active_customers"
    tbl.dataset_id = _DATASET
    tbl.table_type = "VIEW"
    tbl.num_rows = 0
    tbl.num_bytes = 0
    tbl.schema = [_schema_field("customer_id", "INT64")]
    tbl.time_partitioning = None
    tbl.range_partitioning = None
    tbl.clustering_fields = None
    tbl.view_query = f"SELECT customer_id FROM {_DATASET}.orders WHERE active"
    tbl.mview_query = None
    tbl.modified = datetime(2025, 1, 2, tzinfo=timezone.utc)
    return tbl


def _materialized_view():
    tbl = MagicMock(spec=bigquery.Table)
    tbl.table_id = "daily_totals"
    tbl.dataset_id = _DATASET
    tbl.table_type = "MATERIALIZED_VIEW"
    tbl.num_rows = 0
    tbl.num_bytes = 0
    tbl.schema = [_schema_field("day", "DATE"), _schema_field("total", "FLOAT64")]
    tbl.time_partitioning = None
    tbl.range_partitioning = None
    tbl.clustering_fields = None
    tbl.view_query = None
    tbl.mview_query = f"SELECT day, SUM(total) FROM {_DATASET}.orders GROUP BY day"
    tbl.modified = datetime(2025, 1, 3, tzinfo=timezone.utc)
    return tbl


def _js_routine():
    r = MagicMock()
    r.routine_id = "js_normalize"
    r.language = "JAVASCRIPT"
    arg = MagicMock()
    arg.name = "raw"
    r.arguments = [arg]
    r.body = "return raw.trim().toLowerCase();"
    r.type_ = "SCALAR_FUNCTION"
    r.modified = datetime(2025, 1, 4, tzinfo=timezone.utc)
    return r


@pytest.fixture
def mock_scanner() -> BigQueryScanner:
    """A scanner whose mock client returns the four-kind fixture for one dataset."""
    scanner = BigQueryScanner(project_id="my-project", use_adc=True)
    client = MagicMock(spec=bigquery.Client)

    ds = MagicMock(spec=bigquery.dataset.DatasetListItem)
    ds.dataset_id = _DATASET
    client.list_datasets.return_value = [ds]

    table_items = [_table_list_item("orders"), _table_list_item("active_customers"), _table_list_item("daily_totals")]
    client.list_tables.return_value = table_items

    tables_by_key = {
        "orders": _range_partitioned_table(),
        "active_customers": _view(),
        "daily_totals": _materialized_view(),
    }
    client.get_table.side_effect = lambda ref: tables_by_key[ref._key]

    routine_items = [_routine_list_item("js_normalize")]
    client.list_routines.return_value = routine_items
    routines_by_key = {"js_normalize": _js_routine()}
    client.get_routine.side_effect = lambda ref: routines_by_key[ref._key]

    scanner._client = client
    return scanner


# ---------------------------------------------------------------------------
# The checkpoint test
# ---------------------------------------------------------------------------


def test_scan_all_four_kinds_then_cache_round_trip(mock_scanner, tmp_path):
    """End to end: scan view+mview+JS routine+range-partitioned table → cache → back."""
    scanned = list(mock_scanner.scan())

    # No failures; all four entities present
    assert mock_scanner.failures == []
    by_name = {e.full_name: e for e in scanned}
    assert set(by_name) == {
        f"{_DATASET}.orders",
        f"{_DATASET}.active_customers",
        f"{_DATASET}.daily_totals",
        f"{_DATASET}.js_normalize",
    }

    # Each required kind classified correctly
    orders = by_name[f"{_DATASET}.orders"]
    view = by_name[f"{_DATASET}.active_customers"]
    mview = by_name[f"{_DATASET}.daily_totals"]
    routine = by_name[f"{_DATASET}.js_normalize"]

    assert orders.entity_type is EntityType.TABLE
    assert orders.population is EntityPopulation.TABLE
    assert orders.range_partitioning is not None  # R3.8 captured distinctly
    assert orders.time_partitioning is None
    assert orders.range_partitioning.field == "customer_id"

    assert view.entity_type is EntityType.VIEW
    assert view.population is EntityPopulation.REBUILT
    assert view.view_query is not None
    assert f"{_DATASET}.orders" in view.depends_on  # best-effort dep (R4.5)

    assert mview.entity_type is EntityType.MATERIALIZED_VIEW
    assert mview.population is EntityPopulation.REBUILT
    assert mview.mview_query is not None

    assert routine.entity_type is EntityType.ROUTINE
    assert routine.population is EntityPopulation.REBUILT
    assert routine.routine is not None
    assert routine.routine.language == "JAVASCRIPT"

    # --- Round-trip through the real cache ---
    db_path = os.path.join(str(tmp_path), "phase1.db")
    cache = MetadataCache(db_path=db_path)
    cache.store("my-project", scanned)

    assert cache.has_cache("my-project")
    loaded = cache.load("my-project")
    assert loaded is not None

    loaded_by_name = {e.full_name: e for e in loaded}
    assert set(loaded_by_name) == set(by_name)

    # Structural equivalence on the distinguishing fields of each kind
    lo = loaded_by_name[f"{_DATASET}.orders"]
    assert lo.range_partitioning is not None
    assert lo.range_partitioning.field == "customer_id"
    assert lo.range_partitioning.interval == 10
    assert lo.clustering_fields == ["customer_id"]
    # nested struct/array preserved through scan + cache
    items_col = next(c for c in lo.columns if c.name == "items")
    assert items_col.field_type == "STRUCT"
    assert {f.name for f in items_col.fields} == {"sku", "qty"}

    lv = loaded_by_name[f"{_DATASET}.active_customers"]
    assert lv.entity_type is EntityType.VIEW
    assert lv.view_query is not None
    assert f"{_DATASET}.orders" in lv.depends_on

    lm = loaded_by_name[f"{_DATASET}.daily_totals"]
    assert lm.entity_type is EntityType.MATERIALIZED_VIEW
    assert lm.mview_query is not None

    lr = loaded_by_name[f"{_DATASET}.js_normalize"]
    assert lr.entity_type is EntityType.ROUTINE
    assert lr.routine is not None
    assert lr.routine.language == "JAVASCRIPT"
    assert lr.routine.body == "return raw.trim().toLowerCase();"
