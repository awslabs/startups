"""Shared data models for bq-assess — normative dataclasses and enums.

These are the NORMATIVE models for the lakehouse assessment, implemented exactly per
``.kiro/specs/phase1-assessment-tool/design.md`` § Data Models. Canonical glossary names
(CONTEXT.md); nested types preserved (no flattening).

All legacy code has been migrated to these models as of Phase 8 (8.1). Module-local types
(e.g., ``QueryAnalysis``, ``RelationshipResult``) were moved to their respective consumer
modules (``core/analyzer.py``, ``core/relationships.py``) where they remain internal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# ---- Enums -----------------------------------------------------------------


class EntityType(Enum):
    TABLE = "TABLE"
    EXTERNAL = "EXTERNAL"            # treated as Table (moves)
    VIEW = "VIEW"
    MATERIALIZED_VIEW = "MATERIALIZED_VIEW"
    ROUTINE = "ROUTINE"             # UDF / stored procedure


class EntityPopulation(Enum):
    TABLE = "TABLE"                 # scored on both axes
    REBUILT = "REBUILT"             # view/mv/udf — Query Complexity only, Effort = 0


class EffortCategory(Enum):         # Migration Effort axis (R9)
    AUTO = "AUTO"
    ASSISTED = "ASSISTED"
    MANUAL = "MANUAL"


class ComplexityCategory(Enum):     # Query Complexity axis (R11)
    PORTABLE = "PORTABLE"
    ADAPT = "ADAPT"
    REWRITE = "REWRITE"


class ConfidenceLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ConfidenceSource(Enum):
    QUERY_LOGS = "query_logs"
    VIEW_DEFINITION = "view_definition"
    NAMING_HEURISTIC = "naming_heuristic"
    SCHEMA_ONLY = "schema_only"
    MANUAL_INPUT = "manual_input"
    SAFE_DEFAULT = "safe_default"


class BQPricingModel(Enum):
    ON_DEMAND = "ON_DEMAND"         # bytes scanned
    CAPACITY = "CAPACITY"           # slot reservations / Editions
    UNKNOWN = "UNKNOWN"             # → default on-demand, LOW confidence (R16.3)


# ---- Scanned metadata ------------------------------------------------------


@dataclass
class ColumnSchema:
    name: str
    field_type: str                 # BigQuery type name
    mode: str                       # NULLABLE | REQUIRED | REPEATED
    fields: list["ColumnSchema"] = field(default_factory=list)  # nested STRUCT/RECORD


@dataclass
class TimePartitionConfig:
    type: str                       # DAY | HOUR | MONTH | YEAR
    field: str | None               # None => ingestion-time (_PARTITIONTIME) => non-clean (R7.3)


@dataclass
class RangePartitionConfig:         # R3.8 — previously uncaptured
    field: str
    start: int
    end: int
    interval: int


@dataclass
class RoutineMetadata:              # R3.3 — UDFs / stored procedures
    name: str
    language: str                   # SQL | JAVASCRIPT | ...
    arguments: list[str]
    body: str
    routine_type: str               # SCALAR_FUNCTION | PROCEDURE | ...


@dataclass
class EntityMetadata:
    entity_id: str
    dataset_id: str
    full_name: str                  # "dataset.entity" (the shared cross-file key, R19.5)
    entity_type: EntityType
    population: EntityPopulation
    num_rows: int                   # 0 for views/mviews/routines
    num_bytes: int
    columns: list[ColumnSchema]
    time_partitioning: TimePartitionConfig | None
    range_partitioning: RangePartitionConfig | None
    clustering_fields: list[str] | None
    view_query: str | None          # views (R3.2)
    mview_query: str | None         # materialized views (R3.2)
    routine: RoutineMetadata | None  # routines (R3.3)
    depends_on: list[str]           # FQNs of Tables this entity references (R4.5)
    last_modified: datetime
    physical_bytes: int | None = None  # populated by storage_stats; None = not yet resolved


# ---- Conversion / scoring results -----------------------------------------


@dataclass
class PartitionMapping:             # R7
    iceberg_transforms: list[str]   # e.g. ["day(event_date)"]
    sort_order: list[str]
    auto_derived: bool              # True = clean annotation; False = flagged decision
    decision_flags: list[str]       # partition_decision_required / sort_decision_required


@dataclass
class LossyCast:                    # R8
    column: str
    source_type: str
    iceberg_type: str
    loss_description: str


@dataclass
class ConversionResult:
    ddl: str                        # "" for non-Tables
    partition_mapping: PartitionMapping | None
    lossy_casts: list[LossyCast]
    warnings: list[str]
    success: bool


@dataclass
class EffortResult:                 # R9 — Tables only
    category: EffortCategory
    score: int
    flags: list[str]
    reasoning: str
    confidence: ConfidenceLevel


@dataclass
class DetectedConstruct:            # R10.3
    construct_class: str            # UNNEST | FUNCTION_DRIFT | ARRAY_FN | STRUCT_NAV | JS_UDF | ...
    snippet: str                    # anonymized (R10.4 / R22.4)
    description: str


@dataclass
class ComplexityResult:             # R11
    category: ComplexityCategory
    score: int
    constructs: list[DetectedConstruct]
    flags: list[str]
    reasoning: str
    confidence: ConfidenceLevel
    confidence_source: ConfidenceSource


@dataclass
class TranslationResult:            # Best-effort BQ→Redshift SQL translation
    redshift_sql: str               # translated SQL (or original + comment if failed)
    confidence: str                 # "HIGH" | "LOW"
    warnings: list[str]             # e.g. ["JavaScript UDF requires manual rewrite"]


@dataclass
class PlacementRecommendation:      # R14
    home: str                       # "REDSHIFT" | "ICEBERG_CATALOG"
    signals: list[str]
    confidence: ConfidenceLevel
    refresh_unverified: bool        # True for Iceberg-MV until V7 confirmed


# ---- Cost ------------------------------------------------------------------


@dataclass
class PricingDetection:             # R16 — what PricingDetector.detect() returns
    # The bare BQPricingModel enum cannot carry the figures R16.2 and the confidence
    # R16.3/P20 require, so detect() returns this. `model` is the classification; the
    # capacity_* fields are populated only when model is CAPACITY (R16.2).
    model: BQPricingModel
    confidence: ConfidenceLevel
    source_note: str                # how the model was determined + date (R16.3, P20; V4/V5)
    edition: str | None = None              # "STANDARD" | "ENTERPRISE" | "ENTERPRISE_PLUS"
    baseline_slots: int | None = None
    max_slots: int | None = None
    commitment_slots: int | None = None
    commitment_plan: str | None = None      # "FLEX" | "MONTHLY" | "ANNUAL" | "THREE_YEAR"


@dataclass
class SlotUtilization:              # R17
    avg_slots: float
    p50_slots: float
    p99_slots: float
    peak_slots: float
    active_hour_fraction: float
    total_slot_ms: int
    days_sampled: int               # distinct UTC dates with slot-bearing activity
    total_bytes_processed: int = 0
    # Bytes actually billed (10 MiB per-query minimum, rounded up to the nearest MiB) —
    # what on-demand billing charges. Zero is a legitimate value (all-cached or
    # reservation-served windows); has_billed_bytes below says whether the source
    # carried the column at all.
    total_bytes_billed: int = 0
    # True when the job source exposed total_bytes_billed (JOBS_BY_PROJECT always does;
    # old query-log exports may not). Distinguishes "billed 0" from "column unavailable"
    # so the cost model doesn't fall back to processed bytes on genuinely-zero windows.
    has_billed_bytes: bool = False
    total_queries: int = 0
    lookback_days: int = 30         # calendar days in the observation window


@dataclass
class CostLine:
    label: str
    monthly: float | None           # None when expressed as a range
    monthly_low: float | None
    monthly_high: float | None
    confidence: ConfidenceLevel
    source_note: str                # pricing-constant provenance + date (R18.7; V1–V4)


@dataclass
class WorkloadProfile:
    """Customer-specific workload metrics used for AWS cluster sizing and justification."""
    has_data: bool = False
    total_stored_gb: float = 0.0
    total_queries: int = 0
    days_sampled: int = 0
    lookback_days: int = 30
    queries_per_day: float = 0.0
    queries_per_second_avg: float = 0.0
    avg_concurrent_queries: float = 0.0
    peak_concurrent_queries: float = 0.0
    avg_bytes_per_query: float = 0.0
    monthly_scanned_tb: float = 0.0
    active_hour_fraction: float = 0.0
    total_slot_ms: int = 0
    avg_slots: float = 0.0
    p99_slots: float = 0.0
    peak_slots: float = 0.0


@dataclass
class AWSScenario:
    """One AWS deployment option with its cost lines, total, and justification."""
    label: str                      # e.g. "Redshift Serverless", "Provisioned 3× ra3.4xl (1yr RI)"
    category: str                   # "SERVERLESS" | "PROVISIONED_ONDEMAND" | "PROVISIONED_1YR" | "PROVISIONED_3YR"
    lines: list[CostLine]
    monthly_total: float
    confidence: ConfidenceLevel
    is_recommended: bool = False
    justification: str = ""         # why this option is/isn't recommended for this workload
    cluster_config: str = ""        # e.g. "3× ra3.4xlarge" (empty for serverless)
    workload_fit_notes: list[str] = field(default_factory=list)


@dataclass
class AWSRecommendation:
    """The tool's best-fit recommendation with reasoning anchored to customer workload."""
    recommended_scenario: str       # label of the recommended AWSScenario
    reasoning: str                  # paragraph explaining why, referencing actual workload numbers
    workload_profile: WorkloadProfile = field(default_factory=WorkloadProfile)
    alternatives_considered: list[str] = field(default_factory=list)


@dataclass
class CostComparison:               # R18
    bq_pricing_model: BQPricingModel
    bigquery_monthly: float
    bigquery_breakdown: list[CostLine]
    aws_lines: list[CostLine]       # storage (point) + compute (point or range) — best scenario
    aws_monthly_low: float
    aws_monthly_high: float
    monthly_delta_low: float        # headline: bigquery_monthly - aws_monthly_high
    monthly_delta_high: float       # bigquery_monthly - aws_monthly_low
    annual_savings_low: float
    annual_savings_high: float
    migration_onetime: float        # derived from aggregate Migration Effort (R18.5)
    breakeven_months_low: float
    breakeven_months_high: float
    compute_confidence: ConfidenceLevel
    aws_scenarios: list[AWSScenario] = field(default_factory=list)
    recommendation: AWSRecommendation | None = None
    # Region provenance: which geography each side was priced in (2026-07-02 region cascade).
    bq_pricing_region: str = "us"           # BigQuery dataset location the BQ rates reflect
    aws_pricing_region: str = "us-east-1"   # AWS region the AWS rates reflect
    # What the BigQuery estimate does NOT cover (streaming inserts, Storage R/W API, …) —
    # rendered verbatim in reports so the estimate is never mistaken for the whole GCP bill.
    scope_notes: list[str] = field(default_factory=list)


# ---- Report ----------------------------------------------------------------


@dataclass
class FailureRecord:
    entity_name: str
    stage: str                      # scan | classify | convert | detect | score
    error: str


@dataclass
class EntityReport:
    full_name: str                  # shared cross-file key (R19.5)
    entity_type: EntityType
    population: EntityPopulation
    rows: int
    size_gb: float
    depends_on: list[str]
    # Effort axis (Tables only; None for REBUILT)
    effort: EffortResult | None
    conversion: ConversionResult | None
    load_sync_dml: str | None
    # Query axis (any entity with SQL surface / direct query target)
    complexity: ComplexityResult | None
    rewrite_guidance: list[str]
    translated_sql: TranslationResult | None = None
    placement: PlacementRecommendation | None = None
    physical_bytes: int | None = None  # measured physical storage; None = not available/measured


@dataclass
class AssessmentSummary:
    total_entities: int
    total_tables: int
    total_size_gb: float                # projected post-migration (physical) size
    effort_counts: dict[str, int]       # {"AUTO": n, "ASSISTED": n, "MANUAL": n}
    complexity_counts: dict[str, int]   # {"PORTABLE": n, "ADAPT": n, "REWRITE": n}
    sql_surface_confidence: ConfidenceLevel
    total_logical_size_gb: float = 0.0  # BigQuery logical size (what the customer's console shows)


@dataclass
class Assessment:
    assessment_id: str                  # "assess-{date}-{hash}"
    generated_at: datetime
    project_id: str
    summary: AssessmentSummary
    cost: CostComparison
    entities: list[EntityReport]
    failures: list[FailureRecord]
