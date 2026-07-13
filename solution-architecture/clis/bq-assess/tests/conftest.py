"""Shared test fixtures and Hypothesis strategies."""

from __future__ import annotations

from datetime import datetime, timezone

import hypothesis.strategies as st
import pytest

from bq_assess import models as m  # normative lakehouse model (issue #3)
from bq_assess.core.analyzer import JoinPattern, QueryAnalysis
from bq_assess.models import ColumnSchema


# Valid BigQuery types from TYPE_MAP in the design
BQ_TYPES = [
    "STRING", "INT64", "FLOAT64", "BOOL", "TIMESTAMP", "DATE",
    "STRUCT", "ARRAY", "GEOGRAPHY", "BYTES", "NUMERIC", "BIGNUMERIC",
    "TIME", "JSON", "INTERVAL",
]

BQ_MODES = ["NULLABLE", "REQUIRED", "REPEATED"]

PARTITION_TYPES = ["DAY", "HOUR", "MONTH", "YEAR"]


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_identifier = st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True)


@st.composite
def column_schema(draw: st.DrawFn, *, max_depth: int = 2) -> ColumnSchema:
    """Generate a valid ColumnSchema with proper nesting rules.

    STRUCT types get nested fields; non-STRUCT types get an empty list.
    """
    name = draw(_identifier)
    mode = draw(st.sampled_from(BQ_MODES))

    if max_depth <= 0:
        # At max depth, avoid STRUCT to prevent infinite recursion
        field_type = draw(st.sampled_from([t for t in BQ_TYPES if t != "STRUCT"]))
        return ColumnSchema(name=name, field_type=field_type, mode=mode, fields=[])

    field_type = draw(st.sampled_from(BQ_TYPES))

    if field_type == "STRUCT":
        nested = draw(
            st.lists(column_schema(max_depth=max_depth - 1), min_size=1, max_size=3)
        )
        return ColumnSchema(name=name, field_type=field_type, mode=mode, fields=nested)

    return ColumnSchema(name=name, field_type=field_type, mode=mode, fields=[])


@st.composite
def query_analysis(draw: st.DrawFn) -> QueryAnalysis:
    """Generate a valid QueryAnalysis with table counts, joins, and WHERE columns."""
    table_names = draw(st.lists(_identifier, min_size=1, max_size=6, unique=True))

    table_query_counts = {t: draw(st.integers(min_value=1, max_value=10000)) for t in table_names}

    join_patterns: dict[str, list[JoinPattern]] = {}
    for t in table_names:
        n_joins = draw(st.integers(min_value=0, max_value=3))
        patterns = []
        for _ in range(n_joins):
            right = draw(st.sampled_from(table_names))
            patterns.append(JoinPattern(
                left_table=t,
                right_table=right,
                join_column=draw(_identifier),
                frequency=draw(st.integers(min_value=1, max_value=500)),
            ))
        if patterns:
            join_patterns[t] = patterns

    where_columns: dict[str, list[str]] = {}
    for t in table_names:
        cols = draw(st.lists(_identifier, min_size=0, max_size=4))
        if cols:
            where_columns[t] = cols

    # Hub tables: tables with >5 distinct join partners
    hub_tables = [
        t for t in table_names
        if len({jp.right_table for jp in join_patterns.get(t, [])}) > 5
    ]

    return QueryAnalysis(
        table_query_counts=table_query_counts,
        join_patterns=join_patterns,
        where_columns=where_columns,
        hub_tables=hub_tables,
        anonymized=draw(st.booleans()),
    )


@st.composite
def sql_query_with_literals(draw: st.DrawFn) -> str:
    """Generate SQL strings containing string literals and numeric literals.

    Useful for testing query anonymization — the generated SQL will always
    contain at least one single-quoted string literal and one numeric literal.
    """
    table = draw(_identifier)
    col1 = draw(_identifier)
    col2 = draw(_identifier)

    # Generate a string literal (single-quoted, no internal quotes for simplicity)
    str_value = draw(st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters=" "),
    ))
    num_value = draw(st.one_of(
        st.integers(min_value=-999999, max_value=999999),
        st.floats(min_value=-9999.0, max_value=9999.0, allow_nan=False, allow_infinity=False),
    ))

    # Build a realistic SQL query with both literal types
    template = draw(st.sampled_from([
        f"SELECT * FROM {table} WHERE {col1} = '{str_value}' AND {col2} = {num_value}",
        f"SELECT {col1}, {col2} FROM {table} WHERE {col1} IN ('{str_value}') AND {col2} > {num_value}",
        f"SELECT COUNT(*) FROM {table} WHERE {col1} LIKE '{str_value}%' AND {col2} BETWEEN {num_value} AND {num_value + 100}",
    ]))

    return template


# ---------------------------------------------------------------------------
# Hypothesis strategies — normative lakehouse model (issue #4, design.md § Data Models)
#
# These build the new `bq_assess.models` (aliased `m`) dataclasses used by Phase 1+
# implementations and their P-tests. They sit alongside the legacy strategies above,
# which still serve the not-yet-rewritten code until each phase migrates (see SCRUM_NOTES).
# `column_schema()` is reused as-is — ColumnSchema is shared single-identity between models.
# ---------------------------------------------------------------------------

# Construct classes the SQL surface detector recognizes (design.md DetectedConstruct / R10.3)
SQL_CONSTRUCT_CLASSES = ["UNNEST", "FUNCTION_DRIFT", "ARRAY_FN", "STRUCT_NAV", "JS_UDF"]

# Snippets that exercise each BigQuery-specific construct class, keyed by class.
_CONSTRUCT_SNIPPETS = {
    "UNNEST": "SELECT x FROM t, UNNEST(items) AS x",
    "FUNCTION_DRIFT": "SELECT DATE_DIFF(d2, d1, DAY) FROM t",
    "ARRAY_FN": "SELECT ARRAY_LENGTH(tags) FROM t",
    "STRUCT_NAV": "SELECT payload.user.id FROM t",
    "JS_UDF": "CREATE TEMP FUNCTION f(x FLOAT64) RETURNS FLOAT64 LANGUAGE js AS 'return x*2;'",
}

ENTITY_TYPES = list(m.EntityType)
TABLE_TYPES = [m.EntityType.TABLE, m.EntityType.EXTERNAL]
REBUILT_TYPES = [m.EntityType.VIEW, m.EntityType.MATERIALIZED_VIEW, m.EntityType.ROUTINE]
ROUTINE_LANGUAGES = ["SQL", "JAVASCRIPT"]


@st.composite
def time_partition_config(draw: st.DrawFn) -> m.TimePartitionConfig:
    """Generate a TimePartitionConfig; field=None models ingestion-time (non-clean, R7.3)."""
    return m.TimePartitionConfig(
        type=draw(st.sampled_from(PARTITION_TYPES)),
        field=draw(st.one_of(st.none(), _identifier)),
    )


@st.composite
def range_partition_config(draw: st.DrawFn) -> m.RangePartitionConfig:
    """Generate a RangePartitionConfig with start < end and a positive interval (R3.8)."""
    start = draw(st.integers(min_value=0, max_value=10**6))
    end = draw(st.integers(min_value=start + 1, max_value=start + 10**6 + 1))
    return m.RangePartitionConfig(
        field=draw(_identifier),
        start=start,
        end=end,
        interval=draw(st.integers(min_value=1, max_value=10**5)),
    )


@st.composite
def routine_metadata(draw: st.DrawFn) -> m.RoutineMetadata:
    """Generate a RoutineMetadata (UDF / stored procedure) — R3.3."""
    language = draw(st.sampled_from(ROUTINE_LANGUAGES))
    body = (
        "return x + 1;" if language == "JAVASCRIPT"
        else "SELECT 1"
    )
    return m.RoutineMetadata(
        name=draw(_identifier),
        language=language,
        arguments=draw(st.lists(_identifier, max_size=4)),
        body=body,
        routine_type=draw(st.sampled_from(["SCALAR_FUNCTION", "PROCEDURE"])),
    )


def _population_for(entity_type: m.EntityType) -> m.EntityPopulation:
    """The total, disjoint EntityType -> EntityPopulation mapping (R4.2/R4.3)."""
    return (
        m.EntityPopulation.TABLE
        if entity_type in (m.EntityType.TABLE, m.EntityType.EXTERNAL)
        else m.EntityPopulation.REBUILT
    )


@st.composite
def entity_metadata(
    draw: st.DrawFn,
    *,
    entity_type: m.EntityType | None = None,
) -> m.EntityMetadata:
    """Generate a valid EntityMetadata covering all types and both partitionings.

    Population is derived from the type (R4.2/R4.3). View/MV entities carry their
    `*_query`; routines carry `routine`; tables may carry either/both partitionings.
    Optionally pin `entity_type` to force a specific population in a test.
    """
    etype = entity_type if entity_type is not None else draw(st.sampled_from(ENTITY_TYPES))
    population = _population_for(etype)

    dataset_id = draw(_identifier)
    entity_id = draw(_identifier)
    columns = draw(st.lists(column_schema(), min_size=1, max_size=8))

    # Partitionings / clustering only make sense for Tables; views/routines leave them None.
    if population is m.EntityPopulation.TABLE:
        time_part = draw(st.one_of(st.none(), time_partition_config()))
        range_part = draw(st.one_of(st.none(), range_partition_config()))
        clustering = draw(st.one_of(st.none(), st.lists(_identifier, min_size=1, max_size=4)))
        num_rows = draw(st.integers(min_value=0, max_value=10**12))
    else:
        time_part = None
        range_part = None
        clustering = None
        num_rows = 0  # views/mviews/routines (design.md: 0 for non-tables)

    view_query = draw(st.text(min_size=10, max_size=60)) if etype is m.EntityType.VIEW else None
    mview_query = (
        draw(st.text(min_size=10, max_size=60))
        if etype is m.EntityType.MATERIALIZED_VIEW else None
    )
    routine = draw(routine_metadata()) if etype is m.EntityType.ROUTINE else None

    ts = draw(st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2025, 12, 31),
        timezones=st.just(timezone.utc),
    ))

    return m.EntityMetadata(
        entity_id=entity_id,
        dataset_id=dataset_id,
        full_name=f"{dataset_id}.{entity_id}",
        entity_type=etype,
        population=population,
        num_rows=num_rows,
        num_bytes=draw(st.integers(min_value=0, max_value=10**15)),
        columns=columns,
        time_partitioning=time_part,
        range_partitioning=range_part,
        clustering_fields=clustering,
        view_query=view_query,
        mview_query=mview_query,
        routine=routine,
        depends_on=draw(st.lists(_identifier, max_size=5)),
        last_modified=ts,
    )


@st.composite
def slot_jobs(draw: st.DrawFn, *, min_size: int = 1, max_size: int = 50) -> list[dict]:
    """Generate a list of BigQuery job-metadata dicts for workload/slot analysis (R17).

    Each job carries the fields the Workload Analyzer reads: total_slot_ms,
    total_bytes_processed, creation_time, and — mirroring real BigQuery data —
    total_bytes_billed in one of THREE shapes (added 2026-07-03, widened 2026-07-04):
    normal (>= processed, 10 MiB per-query minimums), cache-hit/reservation-served
    (billed=0 with processed>0), or ABSENT entirely (old query-log exports). The
    absent/zero shapes exist so property tests can reach the processed-fallback and
    billed-zero branches in the cost model. Always non-empty by default so the
    utilization curve (avg/P50/P99/peak) is well-defined.
    """
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    # Per-FILE shape (not per-job): a real export either carries the column or predates
    # it; the workload analyzer treats mixed files as not-carrying (all-or-nothing).
    billed_shape = draw(st.sampled_from(["normal", "zero", "absent"]))
    jobs: list[dict] = []
    for _ in range(n):
        creation = draw(st.datetimes(
            min_value=datetime(2024, 1, 1),
            max_value=datetime(2025, 12, 31),
            timezones=st.just(timezone.utc),
        ))
        processed = draw(st.integers(min_value=0, max_value=10**13))
        job = {
            "total_slot_ms": draw(st.integers(min_value=0, max_value=10**9)),
            "total_bytes_processed": processed,
            "creation_time": creation,
        }
        if billed_shape == "normal":
            job["total_bytes_billed"] = draw(st.integers(
                min_value=processed, max_value=processed + 10 * 1024**2))
        elif billed_shape == "zero":
            job["total_bytes_billed"] = 0
        jobs.append(job)
    return jobs


# ---- Pricing-detection strategies (issue 5.1, R16 / V5) ----
#
# pricing_jobs() extends slot_jobs() with the three INFORMATION_SCHEMA.JOBS columns the
# Pricing Detector classifies on: reservation_id (NULL ⇒ on-demand, non-null ⇒ capacity),
# edition, and statement_type (SCRIPT parents report NULL reservation_id even under capacity).
# slot_jobs() is left untouched — the Workload Analyzer tests pin its 3-key shape.

# Edition values must match the keys in V4_EDITION_SLOT_HOUR_USD so a CAPACITY result the
# detector emits is priceable by the Cost Estimator (R18.2).
PRICING_EDITIONS = ["STANDARD", "ENTERPRISE", "ENTERPRISE_PLUS"]
# PricingDetection.commitment_plan vocabulary (models.py).
COMMITMENT_PLANS = ["FLEX", "MONTHLY", "ANNUAL", "THREE_YEAR"]
# A non-null reservation_id is a path: ADMIN_PROJECT:LOCATION.RESERVATION_NAME (V5).
_reservation_path = st.from_regex(
    r"[a-z0-9-]{1,20}:[a-z-]{2,10}\.[a-z0-9_-]{1,20}", fullmatch=True
)
# Non-SCRIPT leaf statement types (jobs that carry a real reservation_id signal).
_LEAF_STATEMENT_TYPES = ["SELECT", "INSERT", "MERGE", "UPDATE"]


@st.composite
def pricing_jobs(
    draw: st.DrawFn,
    *,
    min_size: int = 1,
    max_size: int = 30,
    force: str | None = None,
) -> list[dict]:
    """Generate INFORMATION_SCHEMA.JOBS rows carrying the detector's signal (R16, V5).

    Each row is a superset of a slot_jobs() row plus ``reservation_id``, ``edition``, and
    ``statement_type``. ``force`` pins an arm so a test can request a deterministic shape:

    - ``"ondemand"`` — all leaf jobs, every ``reservation_id`` NULL.
    - ``"capacity"`` — all leaf jobs, every ``reservation_id`` a non-null path + an edition.
    - ``"all_script"`` — every row a SCRIPT parent (NULL reservation_id by design).
    - ``"empty"``     — no jobs at all (the undeterminable / no-signal case).
    - ``None``        — free mix of SCRIPT parents and on-demand/capacity leaf jobs.
    """
    if force == "empty":
        return []
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    jobs: list[dict] = []
    for _ in range(n):
        creation = draw(st.datetimes(
            min_value=datetime(2024, 1, 1),
            max_value=datetime(2025, 12, 31),
            timezones=st.just(timezone.utc),
        ))
        is_script = force == "all_script" or (force is None and draw(st.booleans()))
        if is_script:
            # SCRIPT parent: NULL reservation_id even under capacity billing (the trap).
            stmt, resv, edition = "SCRIPT", None, None
        elif force == "ondemand":
            stmt, resv, edition = draw(st.sampled_from(_LEAF_STATEMENT_TYPES)), None, None
        elif force == "capacity":
            stmt = draw(st.sampled_from(_LEAF_STATEMENT_TYPES))
            resv = draw(_reservation_path)
            edition = draw(st.sampled_from(PRICING_EDITIONS))
        else:  # free leaf job: either billing model
            stmt = draw(st.sampled_from(_LEAF_STATEMENT_TYPES))
            if draw(st.booleans()):
                resv = draw(_reservation_path)
                edition = draw(st.sampled_from(PRICING_EDITIONS))
            else:
                resv, edition = None, None
        processed = draw(st.integers(min_value=0, max_value=10**13))
        jobs.append({
            "total_slot_ms": draw(st.integers(min_value=0, max_value=10**9)),
            "total_bytes_processed": processed,
            # Cache hits legitimately bill 0 while processing >0 bytes.
            "total_bytes_billed": draw(st.one_of(
                st.just(0),
                st.integers(min_value=processed, max_value=processed + 10 * 1024**2),
            )),
            "creation_time": creation,
            "reservation_id": resv,
            "edition": edition,
            "statement_type": stmt,
        })
    return jobs


@st.composite
def reservation_config(draw: st.DrawFn, *, edition: str | None = None) -> dict:
    """Generate a --reservation-config dict (R1.4): edition + slot/commitment figures.

    Mirrors the manual figures a user supplies from the Slot Estimator or their bill —
    a confidence rung above auto-detection (R16.2). Pin ``edition`` to force one.
    """
    base = draw(st.integers(min_value=0, max_value=10000))
    return {
        "edition": edition or draw(st.sampled_from(PRICING_EDITIONS)),
        "baseline_slots": base,
        "max_slots": draw(st.integers(min_value=base, max_value=base + 10000)),
        "commitment_slots": draw(st.integers(min_value=0, max_value=base + 10000)),
        "commitment_plan": draw(st.sampled_from(COMMITMENT_PLANS)),
    }


@st.composite
def sql_with_constructs(draw: st.DrawFn) -> tuple[str, list[str]]:
    """Generate SQL containing >=1 BigQuery-specific construct, with the expected classes.

    Returns (sql_text, expected_construct_classes) so a detector test can assert that
    every embedded construct is found. Construct snippets are joined into one statement.
    """
    classes = draw(st.lists(
        st.sampled_from(SQL_CONSTRUCT_CLASSES),
        min_size=1,
        max_size=len(SQL_CONSTRUCT_CLASSES),
        unique=True,
    ))
    parts = [_CONSTRUCT_SNIPPETS[c] for c in classes]
    sql = "\n".join(parts)
    return sql, classes


@st.composite
def cost_line(draw: st.DrawFn) -> m.CostLine:
    """Generate a CostLine — either a point value or a labelled range, with a source_note."""
    is_range = draw(st.booleans())
    if is_range:
        low = draw(st.floats(min_value=0.0, max_value=50000.0, allow_nan=False, allow_infinity=False))
        high = draw(st.floats(min_value=low, max_value=low + 50000.0, allow_nan=False, allow_infinity=False))
        monthly = None
    else:
        monthly = draw(st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False))
        low = None
        high = None
    return m.CostLine(
        label=draw(_identifier),
        monthly=monthly,
        monthly_low=low,
        monthly_high=high,
        confidence=draw(st.sampled_from(list(m.ConfidenceLevel))),
        source_note=draw(st.text(min_size=5, max_size=60)),
    )


@st.composite
def assessment(draw: st.DrawFn) -> m.Assessment:
    """Generate a valid normative Assessment with a consistent entity/summary graph.

    Effort axis is present only for Tables (None for REBUILT); Query axis may be present
    for any entity. Summary counts are derived from the generated entities so they agree.
    """
    n = draw(st.integers(min_value=0, max_value=8))
    entities: list[m.EntityReport] = []
    effort_counts = {"AUTO": 0, "ASSISTED": 0, "MANUAL": 0}
    complexity_counts = {"PORTABLE": 0, "ADAPT": 0, "REWRITE": 0}
    total_tables = 0
    total_size = 0.0

    for _ in range(n):
        etype = draw(st.sampled_from(ENTITY_TYPES))
        population = _population_for(etype)
        dataset = draw(_identifier)
        ename = draw(_identifier)
        size_gb = draw(st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
        total_size += size_gb

        # Effort axis — Tables only.
        if population is m.EntityPopulation.TABLE:
            total_tables += 1
            ecat = draw(st.sampled_from(list(m.EffortCategory)))
            effort_counts[ecat.value] += 1
            effort = m.EffortResult(
                category=ecat,
                score=draw(st.integers(min_value=0, max_value=10)),
                flags=draw(st.lists(_identifier, max_size=4)),
                reasoning=draw(st.text(max_size=60)),
                confidence=draw(st.sampled_from(list(m.ConfidenceLevel))),
            )
            conversion = m.ConversionResult(
                ddl=f"CREATE TABLE {dataset}.{ename} (id long);",
                partition_mapping=None,
                lossy_casts=[],
                warnings=[],
                success=True,
            )
            load_sync_dml = draw(st.one_of(st.none(), st.text(min_size=5, max_size=40)))
        else:
            effort = None
            conversion = None
            load_sync_dml = None

        # Query axis — may be present for any entity.
        ccat = draw(st.sampled_from(list(m.ComplexityCategory)))
        complexity_counts[ccat.value] += 1
        complexity = m.ComplexityResult(
            category=ccat,
            score=draw(st.integers(min_value=0, max_value=10)),
            constructs=[],
            flags=draw(st.lists(_identifier, max_size=4)),
            reasoning=draw(st.text(max_size=60)),
            confidence=draw(st.sampled_from(list(m.ConfidenceLevel))),
            confidence_source=draw(st.sampled_from(list(m.ConfidenceSource))),
        )
        placement = None
        if population is m.EntityPopulation.REBUILT:
            placement = m.PlacementRecommendation(
                home=draw(st.sampled_from(["REDSHIFT", "ICEBERG_CATALOG"])),
                signals=draw(st.lists(_identifier, min_size=1, max_size=3)),
                confidence=draw(st.sampled_from(list(m.ConfidenceLevel))),
                refresh_unverified=draw(st.booleans()),
            )

        entities.append(m.EntityReport(
            full_name=f"{dataset}.{ename}",
            entity_type=etype,
            population=population,
            rows=draw(st.integers(min_value=0, max_value=10**12)) if population is m.EntityPopulation.TABLE else 0,
            size_gb=size_gb,
            depends_on=draw(st.lists(_identifier, max_size=4)),
            effort=effort,
            conversion=conversion,
            load_sync_dml=load_sync_dml,
            complexity=complexity,
            rewrite_guidance=draw(st.lists(st.text(min_size=1, max_size=40), max_size=3)),
            placement=placement,
        ))

    summary = m.AssessmentSummary(
        total_entities=len(entities),
        total_tables=total_tables,
        total_size_gb=round(total_size, 4),
        effort_counts=effort_counts,
        complexity_counts=complexity_counts,
        sql_surface_confidence=draw(st.sampled_from(list(m.ConfidenceLevel))),
    )

    bq_monthly = draw(st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False))
    aws_low = draw(st.floats(min_value=0.0, max_value=bq_monthly + 1.0, allow_nan=False, allow_infinity=False))
    aws_high = draw(st.floats(min_value=aws_low, max_value=aws_low + 50000.0, allow_nan=False, allow_infinity=False))
    cost = m.CostComparison(
        bq_pricing_model=draw(st.sampled_from(list(m.BQPricingModel))),
        bigquery_monthly=bq_monthly,
        bigquery_breakdown=draw(st.lists(cost_line(), max_size=3)),
        aws_lines=draw(st.lists(cost_line(), min_size=1, max_size=3)),
        aws_monthly_low=aws_low,
        aws_monthly_high=aws_high,
        monthly_delta_low=bq_monthly - aws_high,
        monthly_delta_high=bq_monthly - aws_low,
        annual_savings_low=(bq_monthly - aws_high) * 12,
        annual_savings_high=(bq_monthly - aws_low) * 12,
        migration_onetime=draw(st.floats(min_value=0.0, max_value=50000.0, allow_nan=False, allow_infinity=False)),
        breakeven_months_low=draw(st.one_of(
            st.floats(min_value=0.0, max_value=120.0, allow_nan=False, allow_infinity=False),
            st.just(9999.0),
        )),
        breakeven_months_high=draw(st.one_of(
            st.floats(min_value=0.0, max_value=240.0, allow_nan=False, allow_infinity=False),
            st.just(9999.0),
        )),
        compute_confidence=draw(st.sampled_from(list(m.ConfidenceLevel))),
    )

    failures = [
        m.FailureRecord(
            entity_name=draw(_identifier),
            stage=draw(st.sampled_from(["scan", "classify", "convert", "detect", "score"])),
            error=draw(st.text(min_size=5, max_size=60)),
        )
        for _ in range(draw(st.integers(min_value=0, max_value=3)))
    ]

    ts = draw(st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2025, 12, 31),
        timezones=st.just(timezone.utc),
    ))

    return m.Assessment(
        assessment_id=f"assess-{draw(st.from_regex(r'[0-9]{8}', fullmatch=True))}-{draw(st.from_regex(r'[a-f0-9]{6}', fullmatch=True))}",
        generated_at=ts,
        project_id=draw(_identifier),
        summary=summary,
        cost=cost,
        entities=entities,
        failures=failures,
    )

# ---- Normative-model strategy fixtures (issue #4) ----

@pytest.fixture
def gen_column_schema():
    """Fixture providing the column_schema Hypothesis strategy."""
    return column_schema()


@pytest.fixture
def gen_query_analysis():
    """Fixture providing the query_analysis Hypothesis strategy."""
    return query_analysis()


@pytest.fixture
def gen_sql_query_with_literals():
    """Fixture providing the sql_query_with_literals Hypothesis strategy."""
    return sql_query_with_literals()

@pytest.fixture
def gen_entity_metadata():
    """Fixture providing the entity_metadata Hypothesis strategy."""
    return entity_metadata()


@pytest.fixture
def gen_slot_jobs():
    """Fixture providing the slot_jobs Hypothesis strategy."""
    return slot_jobs()


@pytest.fixture
def gen_pricing_jobs():
    """Fixture providing the pricing_jobs Hypothesis strategy (issue 5.1)."""
    return pricing_jobs()


@pytest.fixture
def gen_reservation_config():
    """Fixture providing the reservation_config Hypothesis strategy (issue 5.1)."""
    return reservation_config()


@pytest.fixture
def gen_sql_with_constructs():
    """Fixture providing the sql_with_constructs Hypothesis strategy."""
    return sql_with_constructs()


@pytest.fixture
def gen_assessment():
    """Fixture providing the assessment Hypothesis strategy."""
    return assessment()
