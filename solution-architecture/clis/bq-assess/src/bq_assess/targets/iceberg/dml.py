"""Load/Sync DML Generator — initial load + ongoing MERGE on Iceberg (R12).

Emits per-Table:
- Initial-load SQL by volume tier (INSERT…SELECT / staged COPY / partition-wise)
- Ongoing-upsert MERGE when a sync signal is present
- Text only — never executes (R12.3)
- None for REBUILT entities (R12.5)
- Non-clean partition caveat inline when flagged (R12.4)

V8 confirmed (2026-06-15): INSERT, UPDATE, MERGE all work on partitioned S3 Tables
(Iceberg) from Redshift Serverless. Supported transforms: identity, year, month, day,
hour, bucket, truncate.
"""

from __future__ import annotations

from bq_assess.models import (
    ConversionResult,
    EffortResult,
    EntityMetadata,
    EntityPopulation,
)

# Volume tier thresholds (bytes)
SMALL_THRESHOLD = 1 * 1024**3        # 1 GB — single INSERT…SELECT
LARGE_THRESHOLD = 100 * 1024**3      # 100 GB — staged COPY via S3


class DMLGenerator:
    """Generate Load/Sync DML for migrating Tables to Iceberg (R12).

    Contract (design.md § Component Interfaces):
        def generate(self, entity: EntityMetadata, effort: EffortResult,
                     conversion: ConversionResult | None) -> str | None
    """

    def generate(
        self,
        entity: EntityMetadata,
        effort: EffortResult,
        conversion: ConversionResult | None = None,
    ) -> str | None:
        """Generate load/sync DML for an entity.

        Returns:
            DML text for Tables, or None for REBUILT entities (R12.5).
        """
        # No DML for views/MVs/UDFs (R12.5)
        if entity.population == EntityPopulation.REBUILT:
            return None

        parts: list[str] = []

        # Non-clean partition caveat (R12.4)
        if conversion and conversion.partition_mapping:
            pm = conversion.partition_mapping
            if not pm.auto_derived:
                parts.append(self._partition_caveat(pm.decision_flags))

        # Initial load (R12.1)
        parts.append(self._initial_load(entity))

        # Ongoing sync via MERGE if sync signal present (R12.2)
        if self._has_sync_signal(entity):
            parts.append(self._merge_upsert(entity))

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Initial load by volume tier (R12.1)
    # ------------------------------------------------------------------

    def _initial_load(self, entity: EntityMetadata) -> str:
        target = entity.full_name
        # Assume source is accessible via external schema or federated query
        source = f"bq_source.{entity.full_name.replace('.', '_')}"

        if entity.num_bytes <= SMALL_THRESHOLD:
            return self._load_small(target, source)
        elif entity.num_bytes <= LARGE_THRESHOLD:
            return self._load_large(target, source, entity)
        else:
            return self._load_huge(target, source, entity)

    def _load_small(self, target: str, source: str) -> str:
        return (
            f"-- Initial load (small table, single INSERT…SELECT)\n"
            f"INSERT INTO {target}\n"
            f"SELECT * FROM {source};"
        )

    def _load_large(self, target: str, source: str, entity: EntityMetadata) -> str:
        s3_path = f"s3://migration-staging/{entity.full_name.replace('.', '/')}/"
        return (
            f"-- Initial load (large table, staged via S3)\n"
            f"-- Step 1: Export from BigQuery to S3 staging\n"
            f"--   bq extract → {s3_path}\n"
            f"-- Step 2: COPY into Iceberg table\n"
            f"COPY {target}\n"
            f"FROM '{s3_path}'\n"
            f"FORMAT PARQUET;"
        )

    def _load_huge(self, target: str, source: str, entity: EntityMetadata) -> str:
        s3_path = f"s3://migration-staging/{entity.full_name.replace('.', '/')}/"
        partition_hint = ""
        if entity.time_partitioning and entity.time_partitioning.field:
            field = entity.time_partitioning.field
            partition_hint = (
                f"\n-- Recommend: partition-wise export by {field} to parallelize load"
            )
        return (
            f"-- Initial load (huge table, partition-by-partition via S3)\n"
            f"-- Step 1: Export partitions from BigQuery to S3 staging{partition_hint}\n"
            f"--   bq extract --partition → {s3_path}<partition>/\n"
            f"-- Step 2: COPY each partition into Iceberg table\n"
            f"COPY {target}\n"
            f"FROM '{s3_path}'\n"
            f"FORMAT PARQUET;\n"
            f"-- Repeat per partition for parallel ingestion"
        )

    # ------------------------------------------------------------------
    # Ongoing sync via MERGE (R12.2, V8 confirmed)
    # ------------------------------------------------------------------

    def _has_sync_signal(self, entity: EntityMetadata) -> bool:
        """Detect if a table needs ongoing sync (CDC/append pattern).

        Signals: ingestion-time partition (append pattern), or presence of
        time-partitioning on a real field (implies ongoing data arrival).
        """
        if entity.time_partitioning is not None:
            return True
        # Could also detect updated_at/created_at columns as sync signals
        sync_columns = {"updated_at", "created_at", "modified_at", "ingestion_time"}
        col_names = {col.name.lower() for col in entity.columns}
        return bool(sync_columns & col_names)

    def _merge_upsert(self, entity: EntityMetadata) -> str:
        target = entity.full_name
        staging = f"staging.{entity.full_name.replace('.', '_')}_delta"

        # Detect merge key (prefer _id columns or first REQUIRED column)
        merge_key = self._detect_merge_key(entity)

        col_names = [col.name for col in entity.columns]
        update_cols = [c for c in col_names if c != merge_key]

        update_clause = ",\n    ".join(
            f"target.{c} = source.{c}" for c in update_cols[:10]  # cap for readability
        )
        if len(update_cols) > 10:
            update_clause += "\n    -- ... (remaining columns omitted for brevity)"

        insert_cols = ", ".join(col_names[:10])
        if len(col_names) > 10:
            insert_cols += ", ..."
        insert_vals = ", ".join(f"source.{c}" for c in col_names[:10])
        if len(col_names) > 10:
            insert_vals += ", ..."

        return (
            f"-- Ongoing sync (MERGE upsert, V8 confirmed on partitioned Iceberg)\n"
            f"MERGE INTO {target} AS target\n"
            f"USING {staging} AS source\n"
            f"ON target.{merge_key} = source.{merge_key}\n"
            f"WHEN MATCHED THEN UPDATE SET\n"
            f"    {update_clause}\n"
            f"WHEN NOT MATCHED THEN INSERT ({insert_cols})\n"
            f"    VALUES ({insert_vals});"
        )

    def _detect_merge_key(self, entity: EntityMetadata) -> str:
        """Best-effort merge key detection."""
        # Prefer columns ending in _id or named 'id'
        for col in entity.columns:
            if col.name.lower() == "id" or col.name.lower().endswith("_id"):
                return col.name
        # Fall back to first REQUIRED column
        for col in entity.columns:
            if col.mode == "REQUIRED":
                return col.name
        # Last resort: first column
        return entity.columns[0].name

    # ------------------------------------------------------------------
    # Partition caveat (R12.4)
    # ------------------------------------------------------------------

    def _partition_caveat(self, decision_flags: list[str]) -> str:
        flags_text = "; ".join(decision_flags)
        return (
            f"-- ⚠️ REVIEW REQUIRED: partition/sort mapping was flagged as non-clean.\n"
            f"-- Flags: {flags_text}\n"
            f"-- Verify the target table's partition layout before running this DML.\n"
            f"-- The suggested transform may not match your access pattern."
        )
