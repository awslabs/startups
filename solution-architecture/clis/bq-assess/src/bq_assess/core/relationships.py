"""Relationship inference for BigQuery table migration assessment.

Detects table relationships from naming conventions, view SQL definitions,
clustering keys, and optional query logs. Per R15.5, this informs Iceberg
sort-order hints (R7) and Query Complexity blast-radius (R11) — it does NOT
emit DISTKEY/SORTKEY recommendations (the Query Engine is Redshift Serverless
over Iceberg; there are no distribution keys).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from bq_assess.core.analyzer import QueryAnalysis
from bq_assess.models import ConfidenceLevel, EntityMetadata


@dataclass
class InferredRelationship:
    """A relationship inferred between two tables."""

    source_table: str
    target_table: str
    join_column: str
    confidence: ConfidenceLevel
    source: str  # "naming_convention", "view_definition", "query_logs"


@dataclass
class RelationshipResult:
    """Aggregated relationship inference results."""

    relationships: list[InferredRelationship]
    likely_join_keys: list[str]
    sort_order_hints: dict[str, list[str]]  # table -> Iceberg sort-order hint columns (R7/R15.5)
    confidence: ConfidenceLevel

# Match patterns like: JOIN dataset.table ON ... or JOIN table ON ...
JOIN_PATTERN = re.compile(
    r"JOIN\s+(\w+(?:\.\w+)?)\s+",
    re.IGNORECASE,
)

# Match ON clause: ... ON a.col = b.col
ON_CLAUSE_PATTERN = re.compile(
    r"ON\s+(\w+(?:\.\w+)?)\.(\w+)\s*=\s*(\w+(?:\.\w+)?)\.(\w+)",
    re.IGNORECASE,
)


class RelationshipInferrer:
    """Infer table relationships from metadata and optional query logs."""

    def infer(
        self,
        tables: list[EntityMetadata],
        query_analysis: QueryAnalysis | None = None,
        view_definitions: dict[str, str] | None = None,
    ) -> RelationshipResult:
        """Infer table relationships from metadata and optional query logs.

        Args:
            tables: List of entity metadata (TABLE population).
            query_analysis: Optional query log analysis results.
            view_definitions: Optional mapping of table_name to view SQL.

        Returns:
            RelationshipResult with inferred relationships, join keys,
            Iceberg sort-order hints, and overall confidence level.
        """
        relationships: list[InferredRelationship] = []
        likely_join_keys: list[str] = []
        sort_order_hints: dict[str, list[str]] = {}

        # 1. Column naming heuristic: _id suffix columns in >3 tables
        naming_rels, naming_keys = self._infer_from_naming(tables)
        relationships.extend(naming_rels)
        likely_join_keys.extend(naming_keys)

        # 2. View SQL parsing: extract JOIN clauses
        if view_definitions:
            view_rels = self._infer_from_views(view_definitions)
            relationships.extend(view_rels)

        # 3. Clustering keys → Iceberg sort-order hints (R7; NOT Redshift SORTKEYs — R15.5)
        for table in tables:
            if table.clustering_fields:
                sort_order_hints[table.full_name] = list(table.clustering_fields)

        # 4. Query log integration
        if query_analysis is not None:
            log_rels = self._infer_from_query_logs(query_analysis)
            relationships.extend(log_rels)

        # 5. Determine overall confidence
        confidence = self._determine_confidence(
            query_analysis, view_definitions, naming_keys
        )

        # Deduplicate join keys
        likely_join_keys = sorted(set(likely_join_keys))

        return RelationshipResult(
            relationships=relationships,
            likely_join_keys=likely_join_keys,
            sort_order_hints=sort_order_hints,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_from_naming(
        tables: list[EntityMetadata],
    ) -> tuple[list[InferredRelationship], list[str]]:
        """Detect relationships from _id suffix column naming conventions.

        Columns ending in ``_id`` that appear in more than 3 tables are
        considered likely join keys.  For each pair of tables sharing such
        a column, an InferredRelationship is created.
        """
        # Map column_name -> set of table full_names that contain it
        id_column_tables: dict[str, set[str]] = defaultdict(set)

        for table in tables:
            for col in table.columns:
                if col.name.endswith("_id"):
                    id_column_tables[col.name].add(table.full_name)

        relationships: list[InferredRelationship] = []
        likely_join_keys: list[str] = []

        MAX_TOTAL_RELS = 100_000
        for col_name, table_names in id_column_tables.items():
            if len(table_names) > 3:
                likely_join_keys.append(col_name)
                sorted_names = sorted(table_names)[:10]
                for src, tgt in combinations(sorted_names, 2):
                    relationships.append(
                        InferredRelationship(
                            source_table=src,
                            target_table=tgt,
                            join_column=col_name,
                            confidence=ConfidenceLevel.MEDIUM,
                            source="naming_convention",
                        )
                    )
                    if len(relationships) >= MAX_TOTAL_RELS:
                        return relationships, likely_join_keys

        return relationships, likely_join_keys

    @staticmethod
    def _infer_from_views(
        view_definitions: dict[str, str],
    ) -> list[InferredRelationship]:
        """Parse JOIN clauses from view SQL definitions.

        Extracts table relationships from SQL JOIN patterns found in view
        definitions.
        """
        relationships: list[InferredRelationship] = []

        for view_name, sql in view_definitions.items():
            # Try to extract ON clause details first
            for match in ON_CLAUSE_PATTERN.finditer(sql):
                left_ref = match.group(1)
                left_col = match.group(2)
                right_ref = match.group(3)
                # right_col = match.group(4) — same join column typically

                # Use the join column name from the ON clause
                join_col = left_col

                relationships.append(
                    InferredRelationship(
                        source_table=left_ref,
                        target_table=right_ref,
                        join_column=join_col,
                        confidence=ConfidenceLevel.MEDIUM,
                        source="view_definition",
                    )
                )

            # If no ON clause matches, fall back to just detecting JOINed tables
            if not any(ON_CLAUSE_PATTERN.finditer(sql)):
                joined_tables = JOIN_PATTERN.findall(sql)
                for joined_table in joined_tables:
                    relationships.append(
                        InferredRelationship(
                            source_table=view_name,
                            target_table=joined_table,
                            join_column="unknown",
                            confidence=ConfidenceLevel.MEDIUM,
                            source="view_definition",
                        )
                    )

        return relationships

    @staticmethod
    def _infer_from_query_logs(
        query_analysis: QueryAnalysis,
    ) -> list[InferredRelationship]:
        """Extract relationships from query log join patterns."""
        relationships: list[InferredRelationship] = []

        for _table, patterns in query_analysis.join_patterns.items():
            for jp in patterns:
                relationships.append(
                    InferredRelationship(
                        source_table=jp.left_table,
                        target_table=jp.right_table,
                        join_column=jp.join_column,
                        confidence=ConfidenceLevel.HIGH,
                        source="query_logs",
                    )
                )

        return relationships

    @staticmethod
    def _determine_confidence(
        query_analysis: QueryAnalysis | None,
        view_definitions: dict[str, str] | None,
        naming_keys: list[str],
    ) -> ConfidenceLevel:
        """Determine overall confidence based on available data sources.

        HIGH  — query logs provided
        MEDIUM — view definitions found or naming heuristics produced results
        LOW   — schema-only analysis
        """
        if query_analysis is not None:
            return ConfidenceLevel.HIGH
        if (view_definitions and len(view_definitions) > 0) or len(naming_keys) > 0:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW
