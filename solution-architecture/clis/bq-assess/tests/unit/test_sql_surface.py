"""Unit tests for SQLSurfaceAnalyzer — construct detection, anonymization, assembly (R10).

The P16 (construct↔score) and P17 (anonymization) Hypothesis properties are owned by issue
#22 (3.4). These unit tests pin #19's detection/anonymize/assemble behavior per construct
class and the surface-attribution rules.
"""

from __future__ import annotations

from datetime import datetime, timezone

from bq_assess.core.sql_surface import (
    ARRAY_FN,
    FUNCTION_DRIFT,
    JS_UDF,
    STRUCT_NAV,
    UNNEST,
    SQLSurfaceAnalyzer,
)
from bq_assess.models import (
    ColumnSchema,
    EntityMetadata,
    EntityPopulation,
    EntityType,
    RoutineMetadata,
)


def _analyzer() -> SQLSurfaceAnalyzer:
    return SQLSurfaceAnalyzer()


# ---------------------------------------------------------------------------
# Detection — one class at a time
# ---------------------------------------------------------------------------


class TestDetect:
    def test_unnest(self):
        c = _analyzer().detect("SELECT x FROM t, UNNEST(items) AS x")
        assert [d.construct_class for d in c] == [UNNEST]

    def test_array_fn_function(self):
        c = _analyzer().detect("SELECT ARRAY_LENGTH(tags) FROM t")
        classes = {d.construct_class for d in c}
        # ARRAY_LENGTH is both an ARRAY_* fn and a drift name — both are legitimate signals
        assert ARRAY_FN in classes or FUNCTION_DRIFT in classes

    def test_array_constructor(self):
        c = _analyzer().detect("SELECT ARRAY[1, 2, 3] AS a")
        assert ARRAY_FN in {d.construct_class for d in c}

    def test_function_drift(self):
        c = _analyzer().detect("SELECT DATE_DIFF(d2, d1, DAY) FROM t")
        assert FUNCTION_DRIFT in {d.construct_class for d in c}

    def test_struct_nav(self):
        c = _analyzer().detect("SELECT payload.user.id FROM t")
        assert STRUCT_NAV in {d.construct_class for d in c}

    def test_js_udf(self):
        sql = "CREATE TEMP FUNCTION f(x FLOAT64) RETURNS FLOAT64 LANGUAGE js AS 'return x*2;'"
        assert JS_UDF in {d.construct_class for d in _analyzer().detect(sql)}

    def test_clean_sql_has_no_constructs(self):
        assert _analyzer().detect("SELECT id, name FROM users WHERE active = TRUE") == []

    def test_empty_sql(self):
        assert _analyzer().detect("") == []

    def test_multiple_constructs_deduped_by_class(self):
        sql = (
            "SELECT payload.user.id, ARRAY_LENGTH(tags) "
            "FROM t, UNNEST(items) AS x WHERE a.b.c = 1"
        )
        classes = [d.construct_class for d in _analyzer().detect(sql)]
        # each class at most once
        assert len(classes) == len(set(classes))
        assert UNNEST in classes
        assert STRUCT_NAV in classes

    def test_snippet_is_anonymized(self):
        sql = "SELECT * FROM t, UNNEST(items) WHERE name = 'secret_value'"
        c = _analyzer().detect(sql)
        for d in c:
            assert "secret_value" not in d.snippet


# ---------------------------------------------------------------------------
# Anonymization (R10.4 / R22.4)
# ---------------------------------------------------------------------------


class TestAnonymize:
    def test_string_literal_removed(self):
        out = _analyzer().anonymize("WHERE name = 'Alice'")
        assert "Alice" not in out
        assert "'?'" in out

    def test_numeric_literal_removed(self):
        out = _analyzer().anonymize("WHERE age = 42")
        assert "42" not in out

    def test_identifier_with_digits_preserved(self):
        out = _analyzer().anonymize("SELECT col1, table2.col3 FROM table2")
        assert "col1" in out
        assert "table2" in out
        assert "col3" in out

    def test_empty(self):
        assert _analyzer().anonymize("") == ""


# ---------------------------------------------------------------------------
# Surface assembly (R10.1, R10.2, R10.5)
# ---------------------------------------------------------------------------


def _entity(full_name, etype, *, view=None, mview=None, routine_body=None):
    dataset, eid = full_name.split(".")
    routine = None
    if routine_body is not None:
        routine = RoutineMetadata(
            name=eid, language="JAVASCRIPT", arguments=["x"],
            body=routine_body, routine_type="SCALAR_FUNCTION",
        )
    pop = (
        EntityPopulation.TABLE
        if etype in (EntityType.TABLE, EntityType.EXTERNAL)
        else EntityPopulation.REBUILT
    )
    return EntityMetadata(
        entity_id=eid, dataset_id=dataset, full_name=full_name,
        entity_type=etype, population=pop, num_rows=0, num_bytes=0,
        columns=[ColumnSchema(name="id", field_type="INT64", mode="NULLABLE")],
        time_partitioning=None, range_partitioning=None, clustering_fields=None,
        view_query=view, mview_query=mview, routine=routine, depends_on=[],
        last_modified=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


class TestAssemble:
    def test_view_mview_routine_captured(self):
        entities = [
            _entity("d.v", EntityType.VIEW, view="SELECT a FROM d.t"),
            _entity("d.mv", EntityType.MATERIALIZED_VIEW, mview="SELECT b FROM d.t"),
            _entity("d.fn", EntityType.ROUTINE, routine_body="return x;"),
            _entity("d.plain", EntityType.TABLE),  # no SQL surface
        ]
        surface = _analyzer().assemble(entities)
        assert set(surface) == {"d.v", "d.mv", "d.fn"}  # plain table omitted
        assert surface["d.v"] == ["SELECT a FROM d.t"]

    def test_surface_is_anonymized(self):
        entities = [_entity("d.v", EntityType.VIEW, view="SELECT a FROM d.t WHERE x = 'top_secret'")]
        surface = _analyzer().assemble(entities)
        assert "top_secret" not in surface["d.v"][0]

    def test_ad_hoc_only_with_logs(self):
        entities = [_entity("d.t", EntityType.TABLE)]
        # No logs → no ad-hoc bucket
        assert "__ad_hoc__" not in _analyzer().assemble(entities)
        # With logs → ad-hoc bucket present + anonymized
        surface = _analyzer().assemble(entities, query_log_text=["SELECT * FROM d.t WHERE id = 99"])
        assert "__ad_hoc__" in surface
        assert "99" not in surface["__ad_hoc__"][0]

    def test_detect_for_entities_attributes_constructs(self):
        entities = [
            _entity("d.unnest_view", EntityType.VIEW, view="SELECT x FROM d.t, UNNEST(items) AS x"),
            _entity("d.js_fn", EntityType.ROUTINE, routine_body="LANGUAGE js AS 'return 1;'"),
            _entity("d.clean", EntityType.VIEW, view="SELECT id FROM d.t"),
        ]
        attributed = _analyzer().detect_for_entities(entities)
        assert UNNEST in {c.construct_class for c in attributed["d.unnest_view"]}
        assert JS_UDF in {c.construct_class for c in attributed["d.js_fn"]}
        assert "d.clean" not in attributed  # no constructs → omitted
