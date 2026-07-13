"""SQLite-based local metadata cache for scanned EntityMetadata (R5).

Stores all scanned metadata — entity type, population, nested columns, BOTH partitionings,
view/mview SQL, routines, and depends_on — so the Assessment can be regenerated offline
without re-scanning the Source (R5.3). Schema follows design.md § SQLite Cache Schema.

store/load round-trip is structurally lossless (R5.4 / property P8, owned by issue #10).
Issue #9 / 1.4.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from bq_assess.models import (
    ColumnSchema,
    EntityMetadata,
    EntityPopulation,
    EntityType,
    RangePartitionConfig,
    RoutineMetadata,
    TimePartitionConfig,
)

_CREATE_SCAN_METADATA = """\
CREATE TABLE IF NOT EXISTS scan_metadata (
    project_id   TEXT PRIMARY KEY,
    scanned_at   TIMESTAMP NOT NULL,
    entity_count INTEGER  NOT NULL
);
"""

_CREATE_ENTITIES = """\
CREATE TABLE IF NOT EXISTS entities (
    project_id        TEXT NOT NULL,
    dataset_id        TEXT NOT NULL,
    entity_id         TEXT NOT NULL,
    full_name         TEXT NOT NULL,
    entity_type       TEXT NOT NULL,
    population        TEXT NOT NULL,
    num_rows          INTEGER,
    num_bytes         INTEGER,
    columns_json      TEXT NOT NULL,
    time_part_json    TEXT,
    range_part_json   TEXT,
    clustering_json   TEXT,
    view_query        TEXT,
    mview_query       TEXT,
    routine_json      TEXT,
    depends_on_json   TEXT,
    last_modified     TIMESTAMP,
    PRIMARY KEY (project_id, dataset_id, entity_id)
);
"""


# ---------------------------------------------------------------------------
# (De)serialization helpers
# ---------------------------------------------------------------------------


def _column_schema_to_dict(col: ColumnSchema) -> dict:
    """Recursively serialize a ColumnSchema (nesting preserved)."""
    return {
        "name": col.name,
        "field_type": col.field_type,
        "mode": col.mode,
        "fields": [_column_schema_to_dict(f) for f in col.fields],
    }


def _dict_to_column_schema(d: dict) -> ColumnSchema:
    """Recursively deserialize a dict back to a ColumnSchema."""
    return ColumnSchema(
        name=d["name"],
        field_type=d["field_type"],
        mode=d["mode"],
        fields=[_dict_to_column_schema(f) for f in d.get("fields", [])],
    )


def _routine_to_dict(r: RoutineMetadata) -> dict:
    return {
        "name": r.name,
        "language": r.language,
        "arguments": list(r.arguments),
        "body": r.body,
        "routine_type": r.routine_type,
    }


def _dict_to_routine(d: dict) -> RoutineMetadata:
    return RoutineMetadata(
        name=d["name"],
        language=d["language"],
        arguments=list(d.get("arguments", [])),
        body=d["body"],
        routine_type=d["routine_type"],
    )


class MetadataCache:
    """SQLite-based local storage for scanned EntityMetadata."""

    def __init__(self, db_path: str = ".bq-assess-cache.db") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(_CREATE_SCAN_METADATA)
        self._conn.execute(_CREATE_ENTITIES)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, project_id: str, entities: list[EntityMetadata]) -> None:
        """Store scanned metadata, replacing any existing data for the project (R5.1)."""
        cur = self._conn.cursor()
        cur.execute("DELETE FROM entities WHERE project_id = ?", (project_id,))
        cur.execute("DELETE FROM scan_metadata WHERE project_id = ?", (project_id,))

        for e in entities:
            cur.execute(
                "INSERT INTO entities "
                "(project_id, dataset_id, entity_id, full_name, entity_type, population, "
                "num_rows, num_bytes, columns_json, time_part_json, range_part_json, "
                "clustering_json, view_query, mview_query, routine_json, depends_on_json, "
                "last_modified) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    e.dataset_id,
                    e.entity_id,
                    e.full_name,
                    e.entity_type.value,
                    e.population.value,
                    e.num_rows,
                    e.num_bytes,
                    json.dumps([_column_schema_to_dict(c) for c in e.columns]),
                    self._dump_time_part(e.time_partitioning),
                    self._dump_range_part(e.range_partitioning),
                    json.dumps(e.clustering_fields) if e.clustering_fields is not None else None,
                    e.view_query,
                    e.mview_query,
                    json.dumps(_routine_to_dict(e.routine)) if e.routine is not None else None,
                    json.dumps(e.depends_on),
                    e.last_modified.isoformat() if e.last_modified is not None else None,
                ),
            )

        cur.execute(
            "INSERT INTO scan_metadata (project_id, scanned_at, entity_count) VALUES (?, ?, ?)",
            (project_id, datetime.now(timezone.utc).isoformat(), len(entities)),
        )
        self._conn.commit()

    def load(self, project_id: str) -> list[EntityMetadata] | None:
        """Load cached metadata for a project; None if no cache exists (R5.3)."""
        if not self.has_cache(project_id):
            return None

        cur = self._conn.cursor()
        cur.execute(
            "SELECT dataset_id, entity_id, full_name, entity_type, population, num_rows, "
            "num_bytes, columns_json, time_part_json, range_part_json, clustering_json, "
            "view_query, mview_query, routine_json, depends_on_json, last_modified "
            "FROM entities WHERE project_id = ?",
            (project_id,),
        )

        result: list[EntityMetadata] = []
        for row in cur.fetchall():
            (
                dataset_id, entity_id, full_name, entity_type, population, num_rows,
                num_bytes, columns_json, time_part_json, range_part_json, clustering_json,
                view_query, mview_query, routine_json, depends_on_json, last_modified_str,
            ) = row

            result.append(EntityMetadata(
                entity_id=entity_id,
                dataset_id=dataset_id,
                full_name=full_name,
                entity_type=EntityType(entity_type),
                population=EntityPopulation(population),
                num_rows=num_rows,
                num_bytes=num_bytes,
                columns=[_dict_to_column_schema(d) for d in json.loads(columns_json)],
                time_partitioning=self._load_time_part(time_part_json),
                range_partitioning=self._load_range_part(range_part_json),
                clustering_fields=json.loads(clustering_json) if clustering_json is not None else None,
                view_query=view_query,
                mview_query=mview_query,
                routine=_dict_to_routine(json.loads(routine_json)) if routine_json is not None else None,
                depends_on=json.loads(depends_on_json) if depends_on_json is not None else [],
                last_modified=datetime.fromisoformat(last_modified_str) if last_modified_str else None,
            ))

        return result

    def has_cache(self, project_id: str) -> bool:
        """Check if cached data exists for a project (R5.2)."""
        cur = self._conn.cursor()
        cur.execute("SELECT 1 FROM scan_metadata WHERE project_id = ? LIMIT 1", (project_id,))
        return cur.fetchone() is not None

    # ------------------------------------------------------------------
    # Partition (de)serialization
    # ------------------------------------------------------------------

    @staticmethod
    def _dump_time_part(tp: TimePartitionConfig | None) -> str | None:
        if tp is None:
            return None
        return json.dumps({"type": tp.type, "field": tp.field})

    @staticmethod
    def _load_time_part(raw: str | None) -> TimePartitionConfig | None:
        if raw is None:
            return None
        d = json.loads(raw)
        return TimePartitionConfig(type=d["type"], field=d["field"])

    @staticmethod
    def _dump_range_part(rp: RangePartitionConfig | None) -> str | None:
        if rp is None:
            return None
        return json.dumps(
            {"field": rp.field, "start": rp.start, "end": rp.end, "interval": rp.interval}
        )

    @staticmethod
    def _load_range_part(raw: str | None) -> RangePartitionConfig | None:
        if raw is None:
            return None
        d = json.loads(raw)
        return RangePartitionConfig(
            field=d["field"], start=d["start"], end=d["end"], interval=d["interval"]
        )
