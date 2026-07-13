"""Bundle data model — the typed hand-off artifact."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from bq_assess.models import (
    EntityMetadata,
    FailureRecord,
    PricingDetection,
    SlotUtilization,
)

SCHEMA_VERSION = 1


def sha256_file(path: str | Path) -> str:
    """Checksum a file — the bundle's integrity contract, shared by writer + loader."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class QueryRecord:
    """One anonymized query + per-job stats (queries.jsonl row)."""
    query: str
    total_slot_ms: int = 0
    total_bytes_processed: int = 0
    total_bytes_billed: int | None = None  # None = column unavailable
    statement_type: str | None = None
    creation_time: str | None = None


@dataclass
class Bundle:
    """The complete hand-off artifact between collector and report generator."""
    project_id: str
    bq_location: str
    aws_region: str
    entities: list[EntityMetadata]
    failures: list[FailureRecord] = field(default_factory=list)
    workload: SlotUtilization | None = None
    pricing: PricingDetection | None = None
    rates: dict | None = None  # PricingRates serialized via price_lookup.rates_to_dict
    queries: list[QueryRecord] | None = None
    storage_basis: str = "assumed"  # measured | mixed | assumed (from StorageStats.basis)
    collector_version: str = ""
    created_at: str = ""
