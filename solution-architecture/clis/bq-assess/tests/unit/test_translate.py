"""Unit tests for RewriteGuide.translate() — best-effort BQ→Redshift translation."""
import pytest

from bq_assess.engine.redshift.rewrite import RewriteGuide


@pytest.fixture
def guide():
    return RewriteGuide()


class TestTranslateBasic:
    def test_date_diff(self, guide):
        result = guide.translate("SELECT DATE_DIFF(a, b, DAY) FROM t")
        assert "DATEDIFF" in result.redshift_sql
        assert result.confidence == "HIGH"

    def test_safe_cast(self, guide):
        result = guide.translate("SELECT SAFE_CAST(x AS INT64) FROM t")
        assert "TRY_CAST" in result.redshift_sql
        assert "BIGINT" in result.redshift_sql
        assert result.confidence == "HIGH"

    def test_if_to_case(self, guide):
        result = guide.translate("SELECT IF(a > 1, a, b) FROM t")
        assert "CASE WHEN" in result.redshift_sql
        assert result.confidence == "HIGH"

    def test_backticks_to_double_quotes(self, guide):
        result = guide.translate("SELECT * FROM `project.dataset.table`")
        assert "`" not in result.redshift_sql
        assert result.confidence == "HIGH"

    def test_int64_to_bigint(self, guide):
        result = guide.translate("SELECT CAST(x AS INT64) FROM t")
        assert "BIGINT" in result.redshift_sql

    def test_format_date(self, guide):
        result = guide.translate("SELECT FORMAT_DATE('%Y-%m', dt) FROM t")
        assert "TO_CHAR" in result.redshift_sql
        assert result.confidence == "HIGH"


class TestTranslateEdgeCases:
    def test_empty_sql(self, guide):
        result = guide.translate("")
        assert result.confidence == "LOW"
        assert result.warnings

    def test_whitespace_only(self, guide):
        result = guide.translate("   \n  ")
        assert result.confidence == "LOW"

    def test_none_sql(self, guide):
        result = guide.translate(None)
        assert result.confidence == "LOW"

    def test_js_udf_detected(self, guide):
        sql = "CREATE FUNCTION fn(x STRING) RETURNS STRING LANGUAGE js AS 'return x;'"
        result = guide.translate(sql)
        assert result.confidence == "LOW"
        assert any("Lambda UDF" in w for w in result.warnings)

    def test_unparseable_sql(self, guide):
        result = guide.translate("THIS IS NOT VALID SQL @@@ !!!")
        assert result.confidence == "LOW"
        assert "TRANSLATION FAILED" in result.redshift_sql


class TestTranslateComplex:
    def test_qualify_passes_through(self, guide):
        sql = "SELECT x FROM t QUALIFY ROW_NUMBER() OVER (ORDER BY x) = 1"
        result = guide.translate(sql)
        assert "QUALIFY" in result.redshift_sql
        assert result.confidence == "HIGH"

    def test_multi_statement(self, guide):
        sql = "SELECT 1; SELECT 2"
        result = guide.translate(sql)
        assert ";" in result.redshift_sql
        assert result.confidence == "HIGH"
