"""Iceberg Converter — BigQuery schema → Iceberg DDL (R6, R7, R8, R23.3).

Emits CREATE TABLE in Iceberg SQL syntax with:
- Native nesting: STRUCT→struct, ARRAY→list, ARRAY<STRUCT>→list<struct> (R6.2, P10)
- Partition/sort mapping per ADR-0003: clean=annotation, non-clean=flagged (R7, P12)
- Lossy Cast detection with warnings, never silent (R8, P11)
- No DDL for REBUILT entities (R4.4, P6)

Type mapping per design.md § Authoritative BigQuery → Iceberg Type Mapping.
"""

from __future__ import annotations

import logging

from bq_assess.models import (
    ColumnSchema,
    ConversionResult,
    EntityMetadata,
    EntityPopulation,
    LossyCast,
    PartitionMapping,
)
from bq_assess.targets.iceberg.constants import (
    BQ_TO_ICEBERG_PARTITION_TRANSFORM,
    V6_JSON_ICEBERG_TYPE,
    V6_JSON_IS_LOSSY,
    V6_JSON_LOSS_DESCRIPTION,
    V6_TIME_ICEBERG_TYPE,
    V6_TIME_IS_LOSSY,
    V6_TIME_LOSS_DESCRIPTION,
)

logger = logging.getLogger(__name__)

# ---- Clean type map (round-trippable, P9) ----

CLEAN_TYPE_MAP: dict[str, str] = {
    "STRING": "string",
    "INT64": "long",
    "INTEGER": "long",
    "FLOAT64": "double",
    "FLOAT": "double",
    "BOOL": "boolean",
    "BOOLEAN": "boolean",
    "BYTES": "binary",
    "DATE": "date",
    "TIMESTAMP": "timestamptz",
    "DATETIME": "timestamp",
    "NUMERIC": "decimal(38,9)",
}

# ---- Lossy type map (contribute to Effort score) ----

LOSSY_TYPE_MAP: dict[str, tuple[str, str]] = {
    "GEOGRAPHY": (
        "string",
        "No native Iceberg GEOGRAPHY; stored as WKT string. Spatial semantics lost.",
    ),
    "INTERVAL": (
        "string",
        "No native Iceberg INTERVAL; stored as ISO 8601 duration string.",
    ),
}

if V6_TIME_IS_LOSSY:
    LOSSY_TYPE_MAP["TIME"] = (V6_TIME_ICEBERG_TYPE, V6_TIME_LOSS_DESCRIPTION)
if V6_JSON_IS_LOSSY:
    LOSSY_TYPE_MAP["JSON"] = (V6_JSON_ICEBERG_TYPE, V6_JSON_LOSS_DESCRIPTION)

_NESTED_TYPES = {"STRUCT", "RECORD"}

_BIGNUMERIC_ICEBERG = "decimal(38,18)"
_BIGNUMERIC_LOSS = (
    "BIGNUMERIC (76 digits: 38 integer + 38 fractional) exceeds Iceberg/Redshift max "
    "precision (38). Mapped to decimal(38,18): 20 integer + 18 fractional digits retained."
)


class IcebergConverter:
    """Convert BigQuery EntityMetadata to Iceberg CREATE TABLE DDL.

    Contract (design.md § Component Interfaces):
        def convert(self, entity: EntityMetadata) -> ConversionResult
    """

    def convert(self, entity: EntityMetadata) -> ConversionResult:
        """Convert entity schema to Iceberg DDL.

        - REBUILT entities → empty DDL, success=True (R4.4, P6)
        - On exception → success=False (maps to Effort MANUAL, R23.3)
        """
        if entity.population == EntityPopulation.REBUILT:
            return ConversionResult(
                ddl="",
                partition_mapping=None,
                lossy_casts=[],
                warnings=[],
                success=True,
            )

        try:
            return self._convert_table(entity)
        except Exception as exc:
            logger.error("Iceberg conversion failed for %s: %s", entity.full_name, exc)
            return ConversionResult(
                ddl="",
                partition_mapping=None,
                lossy_casts=[],
                warnings=[f"Conversion failed: {exc}"],
                success=False,
            )

    # ------------------------------------------------------------------

    def _convert_table(self, entity: EntityMetadata) -> ConversionResult:
        lossy_casts: list[LossyCast] = []
        warnings: list[str] = []

        # Map columns
        col_defs: list[str] = []
        for col in entity.columns:
            iceberg_type = self._resolve_type(col, lossy_casts)
            nullable = " NOT NULL" if col.mode == "REQUIRED" else ""
            col_defs.append(f"  {col.name} {iceberg_type}{nullable}")

        columns_sql = ",\n".join(col_defs)

        # Partition/sort mapping (R7, ADR-0003)
        partition_mapping = self._derive_partition_mapping(entity)

        # Build DDL
        partition_clause = ""
        if partition_mapping and partition_mapping.iceberg_transforms:
            transforms = ", ".join(partition_mapping.iceberg_transforms)
            partition_clause = f"\nPARTITION BY ({transforms})"

        sort_clause = ""
        if partition_mapping and partition_mapping.sort_order:
            sorts = ", ".join(partition_mapping.sort_order)
            sort_clause = f"\nSORT BY ({sorts})"

        ddl = f"CREATE TABLE {entity.full_name} (\n{columns_sql}\n){partition_clause}{sort_clause};"

        # Lossy cast warnings
        for lc in lossy_casts:
            warnings.append(
                f"Lossy cast: column '{lc.column}' ({lc.source_type}) → "
                f"{lc.iceberg_type}: {lc.loss_description}"
            )

        # Non-clean partition/sort warnings
        if partition_mapping and not partition_mapping.auto_derived:
            for flag in partition_mapping.decision_flags:
                warnings.append(f"Partition/sort decision required: {flag}")

        return ConversionResult(
            ddl=ddl,
            partition_mapping=partition_mapping,
            lossy_casts=lossy_casts,
            warnings=warnings,
            success=True,
        )

    # ------------------------------------------------------------------
    # Type resolution (handles nesting recursively)
    # ------------------------------------------------------------------

    def _resolve_type(self, col: ColumnSchema, lossy: list[LossyCast]) -> str:
        """Resolve a column to its Iceberg type string, preserving nesting (P10)."""
        field_type = col.field_type.upper()

        # REPEATED → list<element> (R6.2)
        if col.mode == "REPEATED":
            if field_type in _NESTED_TYPES:
                inner = self._struct_fields(col.fields, lossy)
                return f"list<struct<{inner}>>"
            else:
                elem = self._scalar_type(col, lossy)
                return f"list<{elem}>"

        # STRUCT/RECORD → struct<...> (R6.2)
        if field_type in _NESTED_TYPES:
            inner = self._struct_fields(col.fields, lossy)
            return f"struct<{inner}>"

        return self._scalar_type(col, lossy)

    def _struct_fields(self, fields: list[ColumnSchema], lossy: list[LossyCast]) -> str:
        """Render struct fields recursively.

        Nested-field nullability is honored per R6.4: a REQUIRED sub-field gets a
        ``NOT NULL`` marker just like a top-level column; NULLABLE/REPEATED stay optional.
        """
        parts: list[str] = []
        for f in fields:
            f_type = self._resolve_type(f, lossy)
            nullable = " NOT NULL" if f.mode == "REQUIRED" else ""
            parts.append(f"{f.name}: {f_type}{nullable}")
        return ", ".join(parts)

    def _scalar_type(self, col: ColumnSchema, lossy: list[LossyCast]) -> str:
        """Map a scalar BigQuery type to Iceberg (R6.1, R8)."""
        field_type = col.field_type.upper()

        # Clean
        if field_type in CLEAN_TYPE_MAP:
            return CLEAN_TYPE_MAP[field_type]

        # BIGNUMERIC — always treated as lossy (can't know precision from schema)
        if field_type == "BIGNUMERIC":
            lossy.append(LossyCast(
                column=col.name,
                source_type="BIGNUMERIC",
                iceberg_type=_BIGNUMERIC_ICEBERG,
                loss_description=_BIGNUMERIC_LOSS,
            ))
            return _BIGNUMERIC_ICEBERG

        # Known lossy
        if field_type in LOSSY_TYPE_MAP:
            iceberg_type, loss_desc = LOSSY_TYPE_MAP[field_type]
            lossy.append(LossyCast(
                column=col.name,
                source_type=field_type,
                iceberg_type=iceberg_type,
                loss_description=loss_desc,
            ))
            return iceberg_type

        # Unknown type → string fallback + lossy warning (R8.4)
        lossy.append(LossyCast(
            column=col.name,
            source_type=field_type,
            iceberg_type="string",
            loss_description=f"Unknown BigQuery type '{field_type}'; fallback to string.",
        ))
        return "string"

    # ------------------------------------------------------------------
    # Partition / sort mapping (R7, ADR-0003)
    # ------------------------------------------------------------------

    def _derive_partition_mapping(self, entity: EntityMetadata) -> PartitionMapping | None:
        """Derive Iceberg partition transforms + sort order."""
        transforms: list[str] = []
        sort_order: list[str] = []
        auto_derived = True
        decision_flags: list[str] = []

        # Time partitioning (R7.1, R7.3)
        if entity.time_partitioning is not None:
            tp = entity.time_partitioning
            if tp.field is not None:
                # Explicit-field → clean (R7.1, zero effort)
                transform = BQ_TO_ICEBERG_PARTITION_TRANSFORM.get(tp.type.upper(), "day")
                transforms.append(f"{transform}({tp.field})")
            else:
                # Ingestion-time → non-clean (R7.3). Emit a syntactically valid
                # transform suggestion; the review caveat lives in decision_flags
                # (kept out of the transform list so the DDL stays valid).
                auto_derived = False
                decision_flags.append(
                    "ingestion-time partition (no real column) — "
                    "suggested day(_ingestion_time); review before applying"
                )
                transforms.append("day(_ingestion_time)")

        # Range partitioning (R7.4)
        if entity.range_partitioning is not None:
            rp = entity.range_partitioning
            auto_derived = False
            decision_flags.append(
                f"range partition on '{rp.field}' ({rp.start}..{rp.end}, "
                f"interval={rp.interval}) — no clean Iceberg equivalent; "
                f"suggested bucket(16, {rp.field}) is not equivalent to range, review before applying"
            )
            transforms.append(f"bucket(16, {rp.field})")

        # Clustering → sort order (R7.2, R7.5)
        if entity.clustering_fields:
            for field in entity.clustering_fields:
                sort_order.append(field)
            # BQ allows max 4 clustering fields; >4 would be ambiguous (R7.5)
            if len(entity.clustering_fields) > 4:
                auto_derived = False
                decision_flags.append("ambiguous multi-column clustering")

        if not transforms and not sort_order:
            return None

        return PartitionMapping(
            iceberg_transforms=transforms,
            sort_order=sort_order,
            auto_derived=auto_derived,
            decision_flags=decision_flags,
        )
