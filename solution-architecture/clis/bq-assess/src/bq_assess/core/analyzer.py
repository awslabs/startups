"""Query log analyzer for BigQuery migration assessment.

Analyzes BigQuery query logs (from INFORMATION_SCHEMA.JOBS or exported JSON)
to extract table usage patterns, JOIN relationships, WHERE columns, and hub
tables for DISTKEY/SORTKEY recommendations.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class JoinPattern:
    """A detected JOIN pattern between two tables."""

    left_table: str
    right_table: str
    join_column: str
    frequency: int


@dataclass
class WorkloadMetrics:
    """Workload characteristics extracted from query logs."""

    total_queries: int
    avg_daily_queries: float
    peak_hourly_queries: int
    total_bytes_processed: int
    avg_bytes_per_query: float
    distinct_query_hours: int  # hours with at least one query (out of 24*days)
    query_days_sampled: int


@dataclass
class QueryAnalysis:
    """Results of query log analysis."""

    table_query_counts: dict[str, int]
    join_patterns: dict[str, list[JoinPattern]]
    where_columns: dict[str, list[str]]
    hub_tables: list[str]
    anonymized: bool
    workload_metrics: WorkloadMetrics | None = None


class AnalyzerError(Exception):
    """Raised when query analysis fails."""


# ---------------------------------------------------------------------------
# Regex patterns for SQL parsing
# ---------------------------------------------------------------------------

# String literals: single-quoted values (handles escaped quotes)
_STRING_LITERAL_RE = re.compile(r"'[^']*'")

# Numeric literals after operators / keywords — avoids replacing numbers in
# identifiers.  Matches integers and decimals that follow an operator, comma,
# opening paren, or the keywords BETWEEN / AND / IN / LIMIT / OFFSET / THEN.
_NUMERIC_LITERAL_RE = re.compile(
    r"(?<=[\s=><!(,+\-*/])\d+\.?\d*(?=[\s,);]|$)"
)

# FROM / JOIN table references  (handles optional project.dataset.table)
_TABLE_REF_RE = re.compile(
    r"(?:FROM|JOIN)\s+`?([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+){0,2})`?",
    re.IGNORECASE,
)

# JOIN … ON pattern:
#   JOIN <table> ON <alias>.<col> = <alias>.<col>
_JOIN_PATTERN_RE = re.compile(
    r"JOIN\s+`?([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+){0,2})`?"
    r"\s+(?:AS\s+)?(\w+)?\s*ON\s+"
    r"(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)",
    re.IGNORECASE,
)

# WHERE column references: WHERE <col> <op> or AND/OR <col> <op>
_WHERE_COL_RE = re.compile(
    r"(?:WHERE|AND|OR)\s+(\w+)\.?(\w+)?\s*(?:=|!=|<>|>=|<=|>|<|IN|LIKE|BETWEEN|IS)",
    re.IGNORECASE,
)


class QueryAnalyzer:
    """Analyzes BigQuery query logs for migration recommendations."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_from_api(
        self,
        client,  # google.cloud.bigquery.Client
        project_id: str,
        days: int = 30,
    ) -> QueryAnalysis:
        """Read and analyze query logs from INFORMATION_SCHEMA.JOBS.

        Requires the ``bigquery.jobs.listAll`` permission at the project level.

        Parameters
        ----------
        client:
            An authenticated ``google.cloud.bigquery.Client``.
        project_id:
            GCP project whose query logs should be analysed.
        days:
            Number of days of history to read (default 30).

        Returns
        -------
        QueryAnalysis
            Aggregated analysis of the query logs.

        Raises
        ------
        AnalyzerError
            If the query fails (e.g. missing ``bigquery.jobs.listAll``).
        """
        sql = (
            f"SELECT query, total_bytes_processed, creation_time "
            f"FROM `{project_id}`.`region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT "
            f"WHERE job_type = 'QUERY' "
            f"AND state = 'DONE' "
            f"AND creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY) "
            f"AND statement_type != 'SCRIPT'"
        )

        try:
            rows = client.query(sql).result()
        except Exception as exc:
            msg = str(exc)
            if "Access Denied" in msg or "403" in msg or "permission" in msg.lower():
                raise AnalyzerError(
                    f"Missing required permission 'bigquery.jobs.listAll' on project '{project_id}'. "
                    "This permission is needed to read query logs from INFORMATION_SCHEMA.JOBS. "
                    "To fix this, either:\n"
                    "  1. Grant the 'bigquery.jobs.listAll' permission to your service account, or\n"
                    "  2. Export query logs manually and provide them via the --query-logs option."
                ) from exc
            raise AnalyzerError(
                f"Failed to read query logs from INFORMATION_SCHEMA.JOBS: {msg}"
            ) from exc

        queries: list[str] = []
        bytes_processed_list: list[int] = []
        creation_times: list[datetime] = []
        for row in rows:
            query_text = row.query if hasattr(row, "query") else row[0]
            if query_text:
                queries.append(query_text)
            bp = row.total_bytes_processed if hasattr(row, "total_bytes_processed") else row[1]
            bytes_processed_list.append(bp or 0)
            ct = row.creation_time if hasattr(row, "creation_time") else row[2]
            if ct:
                creation_times.append(ct)

        workload = self._compute_workload_metrics(
            bytes_processed_list, creation_times, days
        )
        result = self._analyze_queries(queries)
        result.workload_metrics = workload
        return result

    def analyze_from_file(self, file_path: str) -> QueryAnalysis:
        """Read and analyze query logs from an exported JSON file.

        Expected format: a JSON array of objects, each with at least a
        ``"query"`` field containing the SQL text.

        Parameters
        ----------
        file_path:
            Path to the exported JSON query log file.

        Returns
        -------
        QueryAnalysis
            Aggregated analysis of the query logs.

        Raises
        ------
        AnalyzerError
            If the file cannot be read or parsed.
        """
        path = Path(file_path)
        if not path.exists():
            raise AnalyzerError(f"Query log file not found: {file_path}")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise AnalyzerError(
                f"Failed to parse query log file '{file_path}': {exc}"
            ) from exc

        if not isinstance(data, list):
            raise AnalyzerError(
                f"Expected a JSON array in '{file_path}', got {type(data).__name__}"
            )

        queries: list[str] = []
        bytes_processed_list: list[int] = []
        creation_times: list[datetime] = []
        for entry in data:
            if isinstance(entry, dict) and entry.get("query"):
                queries.append(entry["query"])
                bp = entry.get("total_bytes_processed", 0)
                bytes_processed_list.append(int(bp) if bp else 0)
                ct = entry.get("creation_time")
                if ct:
                    try:
                        creation_times.append(
                            datetime.fromisoformat(str(ct))
                        )
                    except (ValueError, TypeError):
                        pass

        workload = self._compute_workload_metrics(
            bytes_processed_list, creation_times, days=30
        ) if bytes_processed_list else None

        result = self._analyze_queries(queries)
        result.workload_metrics = workload
        return result

    def anonymize_query(self, query_text: str) -> str:
        """Replace literal values with placeholders.

        - Single-quoted string literals → ``'?'``
        - Numeric literals (integers and floats) appearing after operators
          or SQL keywords → ``?``

        Table and column names containing digits are preserved.
        """
        # First replace string literals
        result = _STRING_LITERAL_RE.sub("'?'", query_text)
        # Then replace numeric literals
        result = _NUMERIC_LITERAL_RE.sub("?", result)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_workload_metrics(
        bytes_processed: list[int],
        creation_times: list[datetime],
        days: int,
    ) -> WorkloadMetrics:
        """Derive workload characteristics from raw job metadata."""
        total_queries = len(bytes_processed)
        total_bytes = sum(bytes_processed)
        avg_bytes = total_bytes / max(total_queries, 1)
        avg_daily = total_queries / max(days, 1)

        # Count queries per hour-bucket and distinct active hours
        hourly_counts: dict[str, int] = defaultdict(int)
        for ct in creation_times:
            bucket = ct.strftime("%Y-%m-%d-%H")
            hourly_counts[bucket] += 1

        peak_hourly = max(hourly_counts.values()) if hourly_counts else 0
        distinct_hours = len(hourly_counts)

        return WorkloadMetrics(
            total_queries=total_queries,
            avg_daily_queries=round(avg_daily, 1),
            peak_hourly_queries=peak_hourly,
            total_bytes_processed=total_bytes,
            avg_bytes_per_query=round(avg_bytes, 0),
            distinct_query_hours=distinct_hours,
            query_days_sampled=days,
        )

    def _analyze_queries(self, queries: list[str]) -> QueryAnalysis:
        """Shared analysis logic for both API and file-based query sources."""
        table_query_counts: dict[str, int] = defaultdict(int)
        join_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        where_cols: dict[str, set[str]] = defaultdict(set)

        for raw_query in queries:
            query = self.anonymize_query(raw_query)
            self._extract_table_refs(query, table_query_counts)
            self._extract_join_patterns(query, join_counts)
            self._extract_where_columns(query, where_cols)

        # Build JoinPattern objects grouped by left table
        join_patterns: dict[str, list[JoinPattern]] = defaultdict(list)
        for (left, right, col), freq in join_counts.items():
            join_patterns[left].append(
                JoinPattern(
                    left_table=left,
                    right_table=right,
                    join_column=col,
                    frequency=freq,
                )
            )

        # Convert where_cols sets to sorted lists
        where_columns: dict[str, list[str]] = {
            t: sorted(cols) for t, cols in where_cols.items()
        }

        # Hub tables: tables with > 5 distinct join partners
        join_partners: dict[str, set[str]] = defaultdict(set)
        for (left, right, _col) in join_counts:
            join_partners[left].add(right)
            join_partners[right].add(left)

        hub_tables = sorted(
            t for t, partners in join_partners.items() if len(partners) > 5
        )

        return QueryAnalysis(
            table_query_counts=dict(table_query_counts),
            join_patterns=dict(join_patterns),
            where_columns=where_columns,
            hub_tables=hub_tables,
            anonymized=True,
        )

    @staticmethod
    def _extract_table_refs(
        query: str, counts: dict[str, int]
    ) -> None:
        """Extract table references from FROM and JOIN clauses."""
        for match in _TABLE_REF_RE.finditer(query):
            table_name = match.group(1)
            # Normalise: take the last two parts (dataset.table) if fully qualified
            parts = table_name.split(".")
            if len(parts) >= 2:
                table_name = f"{parts[-2]}.{parts[-1]}"
            counts[table_name] += 1

    @staticmethod
    def _extract_join_patterns(
        query: str, counts: dict[tuple[str, str, str], int]
    ) -> None:
        """Extract JOIN … ON patterns.

        We extract the right-side table from the JOIN clause and the join
        column from the ON condition.  The left table is inferred from the
        first FROM clause in the query.
        """
        # Determine the "left" (driving) table from the FROM clause
        from_match = re.search(
            r"\bFROM\s+`?([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+){0,2})`?",
            query,
            re.IGNORECASE,
        )
        left_table = ""
        if from_match:
            parts = from_match.group(1).split(".")
            left_table = f"{parts[-2]}.{parts[-1]}" if len(parts) >= 2 else parts[-1]

        for match in _JOIN_PATTERN_RE.finditer(query):
            right_table = match.group(1)
            parts = right_table.split(".")
            if len(parts) >= 2:
                right_table = f"{parts[-2]}.{parts[-1]}"

            # The ON clause has alias.col = alias.col — use the column name
            col_left = match.group(4)
            col_right = match.group(6)
            # Use the column from the right side of the join as the join column
            join_col = col_right if col_left != col_right else col_left
            counts[(left_table, right_table, join_col)] += 1

    @staticmethod
    def _extract_where_columns(
        query: str, where_cols: dict[str, set[str]]
    ) -> None:
        """Extract columns referenced in WHERE clauses."""
        # Find the WHERE clause portion
        where_match = re.search(r"\bWHERE\b", query, re.IGNORECASE)
        if not where_match:
            return

        where_clause = query[where_match.start():]
        for match in _WHERE_COL_RE.finditer(where_clause):
            # group(1) is the table alias or column, group(2) is the column if dotted
            if match.group(2):
                table_or_alias = match.group(1)
                col = match.group(2)
                where_cols[table_or_alias].add(col)
            else:
                col = match.group(1)
                # Without a table qualifier, store under a generic key
                where_cols["_unqualified"].add(col)
