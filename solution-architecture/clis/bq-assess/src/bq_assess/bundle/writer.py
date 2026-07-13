"""Bundle writer — serializes a Bundle to a directory with checksummed manifest."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from enum import Enum

from bq_assess.bundle.models import Bundle, SCHEMA_VERSION, sha256_file
from bq_assess.core.disclaimer import FULL_DISCLAIMER, DISCLAIMER_VERSION
from bq_assess.models import EntityType


class BundleWriter:
    """Write a Bundle to a directory with a versioned, checksummed manifest."""

    def write(self, bundle: Bundle, out_dir: str) -> str:
        """Write the bundle; return the bundle directory path."""
        bundle_dir = os.path.join(out_dir, "bundle")
        os.makedirs(bundle_dir, exist_ok=True)

        files: dict[str, str] = {}  # filename -> sha256

        files["tables.json"] = self._write_tables(bundle, bundle_dir)
        files["routines.json"] = self._write_routines(bundle, bundle_dir)
        files["workload.json"] = self._write_workload(bundle, bundle_dir)
        files["pricing.json"] = self._write_pricing(bundle, bundle_dir)
        files["rates.json"] = self._write_rates(bundle, bundle_dir)
        files["failures.json"] = self._write_failures(bundle, bundle_dir)

        if bundle.queries is not None:
            files["queries.jsonl"] = self._write_queries(bundle, bundle_dir)

        self._write_manifest(bundle, files, bundle_dir)
        return bundle_dir

    def _write_tables(self, bundle: Bundle, bundle_dir: str) -> str:
        tables = []
        for e in bundle.entities:
            if e.entity_type == EntityType.ROUTINE:
                continue
            tables.append({
                "full_name": e.full_name,
                "dataset_id": e.dataset_id,
                "entity_id": e.entity_id,
                "entity_type": e.entity_type.value,
                "population": e.population.value,
                "num_rows": e.num_rows,
                "num_bytes": e.num_bytes,
                "physical_bytes": e.physical_bytes,
                "columns": [self._col_to_dict(c) for c in e.columns],
                "time_partitioning": self._tp_to_dict(e.time_partitioning),
                "range_partitioning": self._rp_to_dict(e.range_partitioning),
                "clustering_fields": e.clustering_fields,
                "view_query": e.view_query,
                "mview_query": e.mview_query,
                "depends_on": e.depends_on,
                "last_modified": e.last_modified.isoformat() if e.last_modified else None,
            })
        return self._dump_json(tables, bundle_dir, "tables.json")

    def _write_routines(self, bundle: Bundle, bundle_dir: str) -> str:
        routines = []
        for e in bundle.entities:
            if e.entity_type != EntityType.ROUTINE or e.routine is None:
                continue
            routines.append({
                "full_name": e.full_name,
                "dataset_id": e.dataset_id,
                "entity_id": e.entity_id,
                "population": e.population.value,
                "routine_type": e.routine.routine_type,
                "language": e.routine.language,
                "name": e.routine.name,
                "arguments": e.routine.arguments,
                "body": e.routine.body,
                "depends_on": e.depends_on,
                # Round-trip losslessness: the scanner may attach columns (TVF outputs),
                # sizes, and last_modified to routine entities — preserve them.
                "columns": [self._col_to_dict(c) for c in e.columns],
                "num_rows": e.num_rows,
                "num_bytes": e.num_bytes,
                "physical_bytes": e.physical_bytes,
                "last_modified": e.last_modified.isoformat() if e.last_modified else None,
            })
        return self._dump_json(routines, bundle_dir, "routines.json")

    def _write_workload(self, bundle: Bundle, bundle_dir: str) -> str:
        if bundle.workload is None:
            return self._dump_json(None, bundle_dir, "workload.json")
        return self._dump_json(asdict(bundle.workload), bundle_dir, "workload.json")

    def _write_pricing(self, bundle: Bundle, bundle_dir: str) -> str:
        if bundle.pricing is None:
            return self._dump_json(None, bundle_dir, "pricing.json")
        data = asdict(bundle.pricing)
        data = {k: (v.value if isinstance(v, Enum) else v) for k, v in data.items()}
        return self._dump_json(data, bundle_dir, "pricing.json")

    def _write_rates(self, bundle: Bundle, bundle_dir: str) -> str:
        return self._dump_json(bundle.rates, bundle_dir, "rates.json")

    def _write_failures(self, bundle: Bundle, bundle_dir: str) -> str:
        data = [asdict(f) for f in bundle.failures]
        return self._dump_json(data, bundle_dir, "failures.json")

    def _write_queries(self, bundle: Bundle, bundle_dir: str) -> str:
        path = os.path.join(bundle_dir, "queries.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for q in bundle.queries:
                row = {
                    "query": q.query,
                    "total_slot_ms": q.total_slot_ms,
                    "total_bytes_processed": q.total_bytes_processed,
                    "creation_time": q.creation_time,
                    "statement_type": q.statement_type,
                }
                if q.total_bytes_billed is not None:
                    row["total_bytes_billed"] = q.total_bytes_billed
                f.write(json.dumps(row, separators=(",", ":")) + "\n")
        return sha256_file(path)

    def _write_manifest(self, bundle: Bundle, files: dict[str, str], bundle_dir: str) -> None:
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "collector_version": bundle.collector_version,
            "project_id": bundle.project_id,
            "bq_location": bundle.bq_location,
            "aws_region": bundle.aws_region,
            "entity_count": len(bundle.entities),
            "storage_basis": bundle.storage_basis,
            "created_at": bundle.created_at or datetime.utcnow().isoformat(),
            "disclaimer_version": DISCLAIMER_VERSION,
            "disclaimer": FULL_DISCLAIMER,
            "files": files,
        }
        path = os.path.join(bundle_dir, "manifest.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    def _col_to_dict(self, col) -> dict:
        d = {"name": col.name, "field_type": col.field_type, "mode": col.mode}
        if col.fields:
            d["fields"] = [self._col_to_dict(f) for f in col.fields]
        return d

    def _tp_to_dict(self, tp) -> dict | None:
        if tp is None:
            return None
        return {"type": tp.type, "field": tp.field}

    def _rp_to_dict(self, rp) -> dict | None:
        if rp is None:
            return None
        return {"field": rp.field, "start": rp.start, "end": rp.end, "interval": rp.interval}

    def _dump_json(self, obj, bundle_dir: str, filename: str) -> str:
        path = os.path.join(bundle_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False, default=str)
        return sha256_file(path)

