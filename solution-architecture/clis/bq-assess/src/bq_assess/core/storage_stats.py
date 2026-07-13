"""Physical-bytes resolution from INFORMATION_SCHEMA.TABLE_STORAGE.

Queries `current_physical_bytes` per table (compressed Parquet footprint, excluding
time-travel and fail-safe). Falls back to ASSUMED_PHYSICAL_RATIO × logical when
the view is unreadable or rows are missing.

The TABLE_STORAGE query filters to only the datasets that contain sized entities
(num_bytes > 0), reducing query cost and improving performance on large projects.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from bq_assess.core.jobs_query import _retry_query

logger = logging.getLogger(__name__)

# Assumed physical/logical ratio when TABLE_STORAGE is unreadable — deliberately
# conservative (typical Parquet compression is 2-5×). Lives here (not the cost engine)
# because physical-bytes resolution is a collection-time concern; the engine re-exports
# it for its storage-cost notes.
ASSUMED_PHYSICAL_RATIO: float = 0.75


@dataclass
class StorageStats:
    physical_map: dict[str, int]   # full_name → physical bytes
    measured_count: int            # sized entities with a TABLE_STORAGE row
    assumed_count: int             # sized entities that got the ratio fallback
    source_note: str

    @property
    def basis(self) -> str:
        if self.measured_count and not self.assumed_count:
            return "measured"
        if self.measured_count:
            return "mixed"
        return "assumed"


def resolve_physical_bytes(client, project_id: str, location: str, entities) -> StorageStats:
    """Resolve physical bytes for all entities; measured when possible, ratio fallback otherwise."""
    measured_map: dict[str, int] = {}
    try:
        measured_map = _query_table_storage(client, project_id, location, entities)
    except Exception as exc:
        logger.warning("Could not read INFORMATION_SCHEMA.TABLE_STORAGE: %s", exc)

    physical_map: dict[str, int] = {}
    measured_count = 0
    assumed_count = 0

    for entity in entities:
        if entity.num_bytes == 0:
            physical_map[entity.full_name] = 0
        elif entity.full_name in measured_map:
            physical_map[entity.full_name] = measured_map[entity.full_name]
            measured_count += 1
        else:
            physical_map[entity.full_name] = round(entity.num_bytes * ASSUMED_PHYSICAL_RATIO)
            assumed_count += 1

    if measured_count and assumed_count:
        source_note = (
            f"{measured_count} tables measured from TABLE_STORAGE; "
            f"{assumed_count} sized at {ASSUMED_PHYSICAL_RATIO}× logical fallback."
        )
    elif measured_count:
        source_note = f"Physical bytes measured from TABLE_STORAGE ({measured_count} tables)."
    else:
        source_note = (
            f"TABLE_STORAGE unavailable — all entities sized at "
            f"{ASSUMED_PHYSICAL_RATIO}× logical (conservative; typical compression is 2–5×)."
        )

    return StorageStats(
        physical_map=physical_map,
        measured_count=measured_count,
        assumed_count=assumed_count,
        source_note=source_note,
    )


def _query_table_storage(client, project_id: str, location: str, entities) -> dict[str, int]:
    """Query TABLE_STORAGE and return {full_name: current_physical_bytes}.

    Filters to datasets containing sized entities (num_bytes > 0) to reduce query cost.
    """
    # Derive the set of datasets with sized entities
    dataset_ids = sorted({e.dataset_id for e in entities if e.num_bytes > 0})

    sql = (
        f"SELECT table_schema, table_name, current_physical_bytes "
        f"FROM `{project_id}`.`region-{location.lower()}`.INFORMATION_SCHEMA.TABLE_STORAGE"
    )

    # Add WHERE clause if we have datasets to filter
    if dataset_ids:
        quoted_datasets = ", ".join(f"'{ds}'" for ds in dataset_ids)
        sql += f" WHERE table_schema IN ({quoted_datasets})"

    rows = _retry_query(lambda: client.query(sql).result())
    result: dict[str, int] = {}
    for row in rows:
        full_name = f"{row.table_schema}.{row.table_name}"
        result[full_name] = int(row.current_physical_bytes or 0)
    return result


def effective_physical_bytes(num_bytes: int, physical_bytes: int | None) -> int:
    """Physical bytes if resolved; else the conservative ASSUMED_PHYSICAL_RATIO fallback."""
    if physical_bytes is not None:
        return int(physical_bytes)
    return round(num_bytes * ASSUMED_PHYSICAL_RATIO)
