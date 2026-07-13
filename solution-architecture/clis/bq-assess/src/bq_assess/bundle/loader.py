"""Bundle loader — directory or .zip → Bundle, with strict manifest verification.

Verification order is deliberate: manifest first (schema_version, then per-file
checksums), THEN deserialization. A corrupt or version-skewed bundle fails loudly
before any of its content is trusted.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from bq_assess.bundle.models import Bundle, SCHEMA_VERSION, QueryRecord, sha256_file
from bq_assess.models import (
    ColumnSchema,
    EntityMetadata,
    EntityPopulation,
    EntityType,
    FailureRecord,
    PricingDetection,
    BQPricingModel,
    ConfidenceLevel,
    RangePartitionConfig,
    RoutineMetadata,
    SlotUtilization,
    TimePartitionConfig,
)

# Files every manifest must list. queries.jsonl is optional: its optionality is
# expressed by absence from the manifest — once listed, it must exist and match.
REQUIRED_FILES = (
    "tables.json",
    "routines.json",
    "workload.json",
    "pricing.json",
    "rates.json",
    "failures.json",
)


class BundleError(Exception):
    """Raised when a bundle fails verification or deserialization."""


class BundleLoader:
    """Load and strictly verify a bundle directory or zip."""

    def load(self, bundle_path: str) -> Bundle:
        """Load a bundle from a directory or .zip; verify manifest first.

        Zip inputs are extracted to a temp dir that is removed before returning —
        the Bundle is fully materialized in memory, so nothing references the
        extracted files afterwards (and error paths must not leak them either).
        """
        path = Path(bundle_path)
        if not path.exists():
            raise BundleError(f"Bundle path not found: {bundle_path}")

        self._tmp_dir: Path | None = None
        try:
            if path.is_file() and path.suffix.lower() == ".zip":
                bundle_dir = self._extract_zip(path)
            elif path.is_dir():
                bundle_dir = path
            else:
                raise BundleError(
                    f"Bundle path must be a directory or .zip file: {bundle_path}"
                )

            manifest = self._verify_manifest(bundle_dir)
            return self._deserialize(bundle_dir, manifest)
        finally:
            if self._tmp_dir is not None:
                shutil.rmtree(self._tmp_dir, ignore_errors=True)
                self._tmp_dir = None

    # ------------------------------------------------------------------
    # Zip handling
    # ------------------------------------------------------------------

    def _extract_zip(self, zip_path: Path) -> Path:
        """Extract a bundle zip to a temp dir; find the manifest at any depth.

        Customers zip with arbitrary nesting (`zip -r bundle.zip bundle-out/bundle`
        stores entries two levels deep) — search recursively rather than guessing.
        The temp dir is tracked on self and removed by load()'s finally block.
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="bq-assess-bundle-"))
        self._tmp_dir = tmp_dir
        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp_dir)
        except zipfile.BadZipFile as exc:
            raise BundleError(f"Not a valid zip file: {zip_path}") from exc

        manifests = sorted(tmp_dir.rglob("manifest.json"))
        if not manifests:
            raise BundleError(f"No manifest.json found anywhere in zip: {zip_path}")
        if len(manifests) > 1:
            raise BundleError(
                f"Multiple manifest.json files found in zip ({len(manifests)}) — "
                f"zip exactly one bundle directory: {zip_path}"
            )
        return manifests[0].parent

    # ------------------------------------------------------------------
    # Manifest verification (strict)
    # ------------------------------------------------------------------

    def _verify_manifest(self, bundle_dir: Path) -> dict:
        manifest_path = bundle_dir / "manifest.json"
        if not manifest_path.exists():
            raise BundleError(f"manifest.json not found in bundle: {bundle_dir}")

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise BundleError(f"Failed to parse manifest.json: {exc}") from exc

        version = manifest.get("schema_version")
        if version != SCHEMA_VERSION:
            raise BundleError(
                f"Bundle schema version mismatch: bundle is v{version} "
                f"(collector {manifest.get('collector_version', 'unknown')}), "
                f"this tool expects v{SCHEMA_VERSION}. "
                f"Re-collect with a matching collector version or use a matching bq-assess."
            )

        files: dict = manifest.get("files", {})
        for filename in REQUIRED_FILES:
            if filename not in files:
                raise BundleError(f"manifest.json is missing required file entry: {filename}")

        # Every manifest-listed file must exist and match. Optionality is expressed
        # by ABSENCE from the manifest (the writer only lists queries.jsonl when it
        # wrote it) — a listed-but-missing file is always truncation or tampering,
        # and silently skipping it would let a stripped bundle pass "strict"
        # verification while the report quietly degrades.
        for filename, expected_sha in files.items():
            fpath = bundle_dir / filename
            if not fpath.exists():
                raise BundleError(
                    f"Bundle file listed in manifest is missing: {filename} — "
                    f"the bundle is incomplete (truncated zip or partial copy). "
                    f"Ask the bundle provider to re-send it."
                )
            actual_sha = sha256_file(fpath)
            if actual_sha != expected_sha:
                raise BundleError(
                    f"Checksum mismatch for {filename}: bundle may be corrupt or "
                    f"tampered (expected {expected_sha[:12]}…, got {actual_sha[:12]}…). "
                    f"Ask the bundle provider to re-send the bundle."
                )

        return manifest

    # ------------------------------------------------------------------
    # Deserialization
    # ------------------------------------------------------------------

    def _deserialize(self, bundle_dir: Path, manifest: dict) -> Bundle:
        entities = self._load_entities(bundle_dir)
        failures = self._load_failures(bundle_dir)
        workload = self._load_workload(bundle_dir)
        pricing = self._load_pricing(bundle_dir)
        rates = self._load_json(bundle_dir / "rates.json")
        queries = self._load_queries(bundle_dir)

        return Bundle(
            project_id=manifest.get("project_id", ""),
            bq_location=manifest.get("bq_location", "US"),
            aws_region=manifest.get("aws_region", "us-east-1"),
            entities=entities,
            failures=failures,
            workload=workload,
            pricing=pricing,
            rates=rates,
            queries=queries,
            storage_basis=manifest.get("storage_basis", "assumed"),
            collector_version=manifest.get("collector_version", ""),
            created_at=manifest.get("created_at", ""),
        )

    def _load_entities(self, bundle_dir: Path) -> list[EntityMetadata]:
        entities: list[EntityMetadata] = []

        tables = self._load_json(bundle_dir / "tables.json") or []
        for t in tables:
            try:
                entities.append(EntityMetadata(
                    entity_id=t.get("entity_id", t["full_name"].split(".")[-1]),
                    dataset_id=t.get("dataset_id", t["full_name"].split(".")[0]),
                    full_name=t["full_name"],
                    entity_type=EntityType(t["entity_type"]),
                    population=EntityPopulation(t.get("population", "TABLE")),
                    num_rows=t.get("num_rows") or 0,
                    num_bytes=t.get("num_bytes") or 0,
                    columns=[self._dict_to_col(c) for c in t.get("columns", [])],
                    time_partitioning=self._dict_to_tp(t.get("time_partitioning")),
                    range_partitioning=self._dict_to_rp(t.get("range_partitioning")),
                    clustering_fields=t.get("clustering_fields"),
                    view_query=t.get("view_query"),
                    mview_query=t.get("mview_query"),
                    routine=None,
                    depends_on=t.get("depends_on", []),
                    last_modified=self._parse_dt(t.get("last_modified")),
                    physical_bytes=t.get("physical_bytes"),
                ))
            except (KeyError, ValueError) as exc:
                raise BundleError(f"Malformed table entry in tables.json: {exc}") from exc

        routines = self._load_json(bundle_dir / "routines.json") or []
        for r in routines:
            try:
                entities.append(EntityMetadata(
                    entity_id=r.get("entity_id", r["full_name"].split(".")[-1]),
                    dataset_id=r.get("dataset_id", r["full_name"].split(".")[0]),
                    full_name=r["full_name"],
                    entity_type=EntityType.ROUTINE,
                    population=EntityPopulation(r.get("population", "REBUILT")),
                    num_rows=r.get("num_rows") or 0,
                    num_bytes=r.get("num_bytes") or 0,
                    columns=[self._dict_to_col(c) for c in r.get("columns", [])],
                    time_partitioning=None,
                    range_partitioning=None,
                    clustering_fields=None,
                    view_query=None,
                    mview_query=None,
                    routine=RoutineMetadata(
                        name=r.get("name", r["full_name"].split(".")[-1]),
                        language=r.get("language", "SQL"),
                        arguments=r.get("arguments", []),
                        body=r.get("body", ""),
                        routine_type=r.get("routine_type", "SCALAR_FUNCTION"),
                    ),
                    depends_on=r.get("depends_on", []),
                    last_modified=self._parse_dt(r.get("last_modified")),
                    physical_bytes=r.get("physical_bytes"),
                ))
            except (KeyError, ValueError) as exc:
                raise BundleError(f"Malformed routine entry in routines.json: {exc}") from exc

        return entities

    def _load_failures(self, bundle_dir: Path) -> list[FailureRecord]:
        data = self._load_json(bundle_dir / "failures.json") or []
        return [
            FailureRecord(
                entity_name=f.get("entity_name", ""),
                stage=f.get("stage", ""),
                error=f.get("error", ""),
            )
            for f in data
        ]

    def _load_workload(self, bundle_dir: Path) -> SlotUtilization | None:
        data = self._load_json(bundle_dir / "workload.json")
        if data is None:
            return None
        valid = {f for f in SlotUtilization.__dataclass_fields__}
        try:
            return SlotUtilization(**{k: v for k, v in data.items() if k in valid})
        except TypeError as exc:
            # Missing required field — a hand-edited or version-skewed workload.json
            # must fail as a bundle error (with re-collect guidance), not a traceback.
            raise BundleError(
                f"Malformed workload.json (missing/invalid fields): {exc}. "
                f"Re-collect the bundle with a matching collector version."
            ) from exc

    def _load_pricing(self, bundle_dir: Path) -> PricingDetection | None:
        data = self._load_json(bundle_dir / "pricing.json")
        if data is None:
            return None
        try:
            return PricingDetection(
                model=BQPricingModel(data.get("model", "UNKNOWN")),
                confidence=ConfidenceLevel(data.get("confidence", "LOW")),
                source_note=data.get("source_note", ""),
                edition=data.get("edition"),
                baseline_slots=data.get("baseline_slots"),
                max_slots=data.get("max_slots"),
                commitment_slots=data.get("commitment_slots"),
                commitment_plan=data.get("commitment_plan"),
            )
        except (TypeError, ValueError) as exc:
            raise BundleError(f"Malformed pricing.json: {exc}") from exc

    def _load_queries(self, bundle_dir: Path) -> list[QueryRecord] | None:
        path = bundle_dir / "queries.jsonl"
        if not path.exists():
            return None
        records: list[QueryRecord] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # skip malformed lines rather than fail the whole load
                records.append(QueryRecord(
                    query=row.get("query", ""),
                    total_slot_ms=row.get("total_slot_ms", 0),
                    total_bytes_processed=row.get("total_bytes_processed", 0),
                    total_bytes_billed=row.get("total_bytes_billed"),
                    statement_type=row.get("statement_type"),
                    creation_time=row.get("creation_time"),
                ))
        return records

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_json(self, path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, OSError) as exc:
            raise BundleError(f"Failed to parse {path.name}: {exc}") from exc

    def _dict_to_col(self, d: dict) -> ColumnSchema:
        return ColumnSchema(
            name=d["name"],
            field_type=d["field_type"],
            mode=d["mode"],
            fields=[self._dict_to_col(f) for f in d.get("fields", [])],
        )

    @staticmethod
    def _dict_to_tp(d: dict | None) -> TimePartitionConfig | None:
        if d is None:
            return None
        return TimePartitionConfig(type=d["type"], field=d.get("field"))

    @staticmethod
    def _dict_to_rp(d: dict | None) -> RangePartitionConfig | None:
        if d is None:
            return None
        return RangePartitionConfig(
            field=d["field"], start=d["start"], end=d["end"], interval=d["interval"]
        )

    @staticmethod
    def _parse_dt(raw: str | None) -> datetime | None:
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return None

