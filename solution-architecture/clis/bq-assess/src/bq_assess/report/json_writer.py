"""Three mirrored JSON files (Landing / Effort / Query) — R19.

Writes three JSON files cross-referenced by full_name:
- Landing: metadata + summary + cost + failures
- Effort: Tables/External entities only (things that physically move)
- Query: All entities (Tables + REBUILT views/MVs/UDFs)
"""
from __future__ import annotations

import json
import os

from bq_assess.models import Assessment
from bq_assess.report._serialize import serialize_entities, serialize_landing


class JSONWriter:
    """Write three mirrored JSON files from an Assessment."""

    def write(self, assessment: Assessment, out_dir: str) -> list[str]:
        """Write landing/effort/query JSON files; return list of absolute paths."""
        aid = assessment.assessment_id
        paths = []

        landing = serialize_landing(assessment)
        paths.append(self._dump(landing, out_dir, f"assessment-landing-{aid}.json"))

        effort_entities, query_entities = serialize_entities(assessment)

        effort = {
            "assessment_id": aid,
            "entities": effort_entities,
        }
        paths.append(self._dump(effort, out_dir, f"assessment-effort-{aid}.json"))

        query = {
            "assessment_id": aid,
            "entities": query_entities,
        }
        paths.append(self._dump(query, out_dir, f"assessment-query-{aid}.json"))

        return paths

    def _dump(self, data: dict, out_dir: str, filename: str) -> str:
        path = os.path.join(out_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return os.path.abspath(path)
