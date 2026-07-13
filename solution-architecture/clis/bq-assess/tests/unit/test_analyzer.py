"""Unit tests for the QueryAnalyzer.

Validates: Requirements 9.4, 9.5
"""

from __future__ import annotations

import json

import pytest

from bq_assess.core.analyzer import AnalyzerError, QueryAnalyzer


@pytest.fixture
def analyzer() -> QueryAnalyzer:
    return QueryAnalyzer()


# ---------------------------------------------------------------------------
# Helper to write a query log JSON file
# ---------------------------------------------------------------------------

def _write_query_log(tmp_path, queries: list[str]):
    """Write a list of SQL strings as a JSON query log file and return the path."""
    path = tmp_path / "queries.json"
    entries = [{"query": q} for q in queries]
    with open(path, "w") as f:
        json.dump(entries, f)
    return str(path)


# ---------------------------------------------------------------------------
# 1. Query log parsing — table_query_counts
# ---------------------------------------------------------------------------

class TestQueryLogParsing:
    """Test query log parsing with known query patterns."""

    def test_simple_select_extracts_table(self, analyzer: QueryAnalyzer, tmp_path):
        path = _write_query_log(tmp_path, ["SELECT * FROM ds.orders"])
        result = analyzer.analyze_from_file(path)

        assert "ds.orders" in result.table_query_counts
        assert result.table_query_counts["ds.orders"] == 1

    def test_join_extracts_both_tables(self, analyzer: QueryAnalyzer, tmp_path):
        sql = (
            "SELECT * FROM ds.orders o "
            "JOIN ds.customers c ON o.customer_id = c.customer_id"
        )
        path = _write_query_log(tmp_path, [sql])
        result = analyzer.analyze_from_file(path)

        assert "ds.orders" in result.table_query_counts
        assert "ds.customers" in result.table_query_counts

    def test_join_extracts_join_patterns(self, analyzer: QueryAnalyzer, tmp_path):
        sql = (
            "SELECT * FROM ds.orders o "
            "JOIN ds.customers c ON o.customer_id = c.customer_id"
        )
        path = _write_query_log(tmp_path, [sql])
        result = analyzer.analyze_from_file(path)

        assert len(result.join_patterns) > 0
        # Flatten all join patterns to check for the expected join
        all_patterns = [
            jp for patterns in result.join_patterns.values() for jp in patterns
        ]
        assert any(jp.join_column == "customer_id" for jp in all_patterns)

    def test_where_extracts_columns(self, analyzer: QueryAnalyzer, tmp_path):
        sql = "SELECT * FROM ds.orders WHERE o.status = 'active'"
        path = _write_query_log(tmp_path, [sql])
        result = analyzer.analyze_from_file(path)

        assert len(result.where_columns) > 0
        # The WHERE clause references o.status
        all_cols = [
            col for cols in result.where_columns.values() for col in cols
        ]
        assert "status" in all_cols

    def test_multiple_queries_accumulate_counts(self, analyzer: QueryAnalyzer, tmp_path):
        queries = [
            "SELECT * FROM ds.orders",
            "SELECT * FROM ds.orders WHERE o.id = 1",
            "SELECT * FROM ds.customers",
        ]
        path = _write_query_log(tmp_path, queries)
        result = analyzer.analyze_from_file(path)

        assert result.table_query_counts["ds.orders"] == 2
        assert result.table_query_counts["ds.customers"] == 1

    def test_result_is_anonymized(self, analyzer: QueryAnalyzer, tmp_path):
        path = _write_query_log(tmp_path, ["SELECT * FROM ds.orders"])
        result = analyzer.analyze_from_file(path)

        assert result.anonymized is True


# ---------------------------------------------------------------------------
# 2. Anonymization
# ---------------------------------------------------------------------------

class TestAnonymization:
    """Test anonymization with specific SQL strings."""

    def test_string_literal_replaced(self, analyzer: QueryAnalyzer):
        sql = "SELECT * FROM t WHERE name = 'John' AND age = 25"
        result = analyzer.anonymize_query(sql)

        assert "'John'" not in result
        assert "'?'" in result

    def test_numeric_literal_replaced(self, analyzer: QueryAnalyzer):
        sql = "SELECT * FROM t WHERE name = 'John' AND age = 25"
        result = analyzer.anonymize_query(sql)

        # 25 after = should be replaced with ?
        assert "= 25" not in result
        assert "= ?" in result

    def test_preserves_table_and_column_names(self, analyzer: QueryAnalyzer):
        sql = "SELECT col1 FROM table1"
        result = analyzer.anonymize_query(sql)

        assert "col1" in result
        assert "table1" in result
        # No changes expected — no literals to anonymize
        assert result == sql

    def test_multiple_string_literals(self, analyzer: QueryAnalyzer):
        sql = "SELECT * FROM t WHERE city = 'NYC' OR city = 'LA'"
        result = analyzer.anonymize_query(sql)

        assert "'NYC'" not in result
        assert "'LA'" not in result
        assert result.count("'?'") == 2

    def test_float_literal_replaced(self, analyzer: QueryAnalyzer):
        sql = "SELECT * FROM t WHERE price > 19.99"
        result = analyzer.anonymize_query(sql)

        assert "19.99" not in result


# ---------------------------------------------------------------------------
# 3. Hub table detection
# ---------------------------------------------------------------------------

class TestHubTableDetection:
    """Test hub table detection (tables with >5 distinct join partners)."""

    def test_hub_table_detected(self, analyzer: QueryAnalyzer, tmp_path):
        # Create queries where ds.hub joins with 6 different tables
        queries = []
        for i in range(6):
            queries.append(
                f"SELECT * FROM ds.hub h "
                f"JOIN ds.table{i} t ON h.id = t.id"
            )
        path = _write_query_log(tmp_path, queries)
        result = analyzer.analyze_from_file(path)

        assert "ds.hub" in result.hub_tables

    def test_non_hub_table_excluded(self, analyzer: QueryAnalyzer, tmp_path):
        # Only 3 join partners — should NOT be a hub table
        queries = []
        for i in range(3):
            queries.append(
                f"SELECT * FROM ds.small h "
                f"JOIN ds.partner{i} t ON h.id = t.id"
            )
        path = _write_query_log(tmp_path, queries)
        result = analyzer.analyze_from_file(path)

        assert "ds.small" not in result.hub_tables


# ---------------------------------------------------------------------------
# 4. Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Test error conditions raise AnalyzerError."""

    def test_file_not_found_raises(self, analyzer: QueryAnalyzer):
        with pytest.raises(AnalyzerError, match="not found"):
            analyzer.analyze_from_file("/nonexistent/path/queries.json")

    def test_invalid_json_raises(self, analyzer: QueryAnalyzer, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("this is not json {{{", encoding="utf-8")

        with pytest.raises(AnalyzerError, match="Failed to parse"):
            analyzer.analyze_from_file(str(path))

    def test_empty_query_list_returns_empty(self, analyzer: QueryAnalyzer, tmp_path):
        path = _write_query_log(tmp_path, [])
        result = analyzer.analyze_from_file(path)

        assert result.table_query_counts == {}
        assert result.join_patterns == {}
        assert result.where_columns == {}
        assert result.hub_tables == []
        assert result.anonymized is True


# ---------------------------------------------------------------------------
# 5. Workload metrics from file
# ---------------------------------------------------------------------------

class TestWorkloadMetricsFromFile:
    """Test workload metric extraction from JSON query logs."""

    def test_workload_metrics_extracted(self, analyzer: QueryAnalyzer, tmp_path):
        """When bytes/timestamps are present, workload metrics are populated."""
        entries = [
            {
                "query": "SELECT * FROM ds.orders",
                "total_bytes_processed": 1000000,
                "creation_time": "2025-01-15T10:00:00+00:00",
            },
            {
                "query": "SELECT * FROM ds.users",
                "total_bytes_processed": 2000000,
                "creation_time": "2025-01-15T11:00:00+00:00",
            },
        ]
        path = tmp_path / "queries.json"
        path.write_text(json.dumps(entries), encoding="utf-8")

        result = analyzer.analyze_from_file(str(path))

        assert result.workload_metrics is not None
        assert result.workload_metrics.total_queries == 2
        assert result.workload_metrics.total_bytes_processed == 3000000
        assert result.workload_metrics.distinct_query_hours == 2

    def test_workload_metrics_without_timestamps(self, analyzer: QueryAnalyzer, tmp_path):
        """Metrics work even when no timestamps are provided."""
        entries = [
            {"query": "SELECT 1", "total_bytes_processed": 500},
        ]
        path = tmp_path / "queries.json"
        path.write_text(json.dumps(entries), encoding="utf-8")

        result = analyzer.analyze_from_file(str(path))

        assert result.workload_metrics is not None
        assert result.workload_metrics.total_queries == 1
        assert result.workload_metrics.peak_hourly_queries == 0

    def test_no_workload_metrics_for_bare_queries(self, analyzer: QueryAnalyzer, tmp_path):
        """Standard query log format (query only) still returns workload metrics."""
        path = _write_query_log(tmp_path, ["SELECT 1"])
        result = analyzer.analyze_from_file(path)
        # bytes_processed_list will have [0], so workload is still computed
        assert result.workload_metrics is not None
        assert result.workload_metrics.total_bytes_processed == 0
