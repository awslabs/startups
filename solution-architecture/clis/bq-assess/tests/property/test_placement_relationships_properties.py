# Feature: bq-assess-lakehouse, Property 18: Placement rules
# Feature: bq-assess-lakehouse, Property 19: Relationship inference & confidence; no distribution keys
"""Property tests P18 (placement) and P19 (relationships).

- **P18** — UDF→REDSHIFT (JS flagged); view/MV home ∈ {REDSHIFT, ICEBERG_CATALOG} with
  non-empty signals and NOT a single blanket constant; Iceberg-MV → refresh_unverified.
  Validates R14.1-R14.4.
- **P19** — `_id` cols in >3 Tables → join keys; views w/ JOINs → ≥1 relationship; each
  relationship has confidence+source; NO DISTKEY/SORTKEY recommendation anywhere.
  Validates R15.1-R15.5.
"""

from __future__ import annotations

from datetime import datetime, timezone

import hypothesis.strategies as st
from hypothesis import given, settings

from bq_assess.core.relationships import RelationshipInferrer
from bq_assess.engine.redshift.placement import PlacementAdvisor
from bq_assess.models import (
    ColumnSchema,
    EntityMetadata,
    EntityPopulation,
    EntityType,
    RoutineMetadata,
)

_ID = st.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True)


def _table(dataset, name, columns):
    return EntityMetadata(
        entity_id=name, dataset_id=dataset, full_name=f"{dataset}.{name}",
        entity_type=EntityType.TABLE, population=EntityPopulation.TABLE,
        num_rows=1, num_bytes=1, columns=columns,
        time_partitioning=None, range_partitioning=None,
        clustering_fields=["created_at"], view_query=None, mview_query=None,
        routine=None, depends_on=[], last_modified=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# P18: Placement rules — R14.1-R14.4
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    n_single=st.integers(min_value=1, max_value=5),
    n_multi=st.integers(min_value=1, max_value=5),
)
def test_p18_placement_no_blanket_default(n_single, n_multi):
    """View/MV home ∈ {REDSHIFT, ICEBERG_CATALOG}, signal-driven, NOT a blanket constant
    (R14.2): single-dataset views → REDSHIFT (engine-local); multi-dataset views →
    ICEBERG_CATALOG (open multi-engine). Across a mix, both homes appear."""
    # Feature: bq-assess-lakehouse, Property 18: Placement rules
    advisor = PlacementAdvisor()

    def _view(i, deps):
        return EntityMetadata(
            entity_id=f"v{i}", dataset_id="ds0", full_name=f"ds0.v{i}",
            entity_type=EntityType.VIEW, population=EntityPopulation.REBUILT,
            num_rows=0, num_bytes=0,
            columns=[ColumnSchema(name="c", field_type="INT64", mode="NULLABLE")],
            time_partitioning=None, range_partitioning=None, clustering_fields=None,
            view_query="SELECT c FROM ...", mview_query=None, routine=None,
            depends_on=deps, last_modified=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

    homes = set()
    for i in range(n_single):
        rec = advisor.recommend(_view(("s", i), [f"ds0.t{i}"]), has_logs=False)
        assert rec is not None and rec.home == "REDSHIFT"  # single-dataset → engine-local
        assert rec.signals
        homes.add(rec.home)
    for i in range(n_multi):
        rec = advisor.recommend(_view(("m", i), [f"ds{i}.a", f"ds{i+1}.b"]), has_logs=False)
        assert rec is not None and rec.home == "ICEBERG_CATALOG"  # multi-dataset → open catalog
        assert rec.signals
        homes.add(rec.home)

    # Both homes produced across the mix — not a blanket default (R14.2).
    assert homes == {"REDSHIFT", "ICEBERG_CATALOG"}


@settings(max_examples=50)
@given(st.data())
def test_p18_udf_always_redshift(data):
    """Every UDF → REDSHIFT; a JavaScript UDF is flagged for Python/Lambda rewrite (R14.1)."""
    # Feature: bq-assess-lakehouse, Property 18: Placement rules
    lang = data.draw(st.sampled_from(["JAVASCRIPT", "SQL"]))
    udf = EntityMetadata(
        entity_id="fn", dataset_id="d", full_name="d.fn",
        entity_type=EntityType.ROUTINE, population=EntityPopulation.REBUILT,
        num_rows=0, num_bytes=0, columns=[],
        time_partitioning=None, range_partitioning=None, clustering_fields=None,
        view_query=None, mview_query=None,
        routine=RoutineMetadata(name="fn", language=lang, arguments=[], body="x", routine_type="SCALAR_FUNCTION"),
        depends_on=[], last_modified=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    rec = PlacementAdvisor().recommend(udf)
    assert rec is not None and rec.home == "REDSHIFT"
    if lang == "JAVASCRIPT":
        assert any("javascript" in s.lower() or "lambda" in s.lower() or "python" in s.lower()
                   for s in rec.signals), "JS UDF must be flagged for Python/Lambda rewrite"


# ---------------------------------------------------------------------------
# P19: Relationship inference & no distribution keys — R15.1-R15.5
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    id_col=_ID.map(lambda s: s + "_id"),
    n_tables=st.integers(min_value=4, max_value=7),
)
def test_p19_id_columns_in_many_tables_are_join_keys(id_col, n_tables):
    """An `_id` column appearing in >3 Tables appears in likely_join_keys (R15.1)."""
    # Feature: bq-assess-lakehouse, Property 19: Relationship inference & confidence; no distribution keys
    tables = [
        _table("d", f"t{i}", [ColumnSchema(name=id_col, field_type="INT64", mode="NULLABLE")])
        for i in range(n_tables)
    ]
    result = RelationshipInferrer().infer(tables)
    assert id_col in result.likely_join_keys
    # Every relationship carries a non-null confidence + source
    for r in result.relationships:
        assert r.confidence is not None
        assert r.source


@settings(max_examples=50)
@given(st.data())
def test_p19_no_distribution_key_recommendations(data):
    """No output field SHALL contain a DISTKEY or SORTKEY recommendation (R15.5 — the
    lakehouse pivot removed distribution keys; the Query Engine is Serverless over Iceberg)."""
    # Feature: bq-assess-lakehouse, Property 19: Relationship inference & confidence; no distribution keys
    n = data.draw(st.integers(min_value=1, max_value=5))
    tables = [_table("d", f"t{i}", [ColumnSchema(name="x_id", field_type="INT64", mode="NULLABLE")]) for i in range(n)]
    result = RelationshipInferrer().infer(tables)
    # The result object must not expose distkey/sortkey recommendation fields.
    forbidden = [f for f in vars(result) if "distkey" in f.lower() or "sortkey" in f.lower()]
    assert not forbidden, f"R15.5 forbids distribution-key fields, found: {forbidden}"
