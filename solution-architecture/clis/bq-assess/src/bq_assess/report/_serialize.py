"""Shared serialization: Assessment dataclass → dicts for JSON/HTML consumption."""
from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import Enum

from bq_assess.models import Assessment, EntityPopulation
from bq_assess.engine.redshift import cost_constants as k


def _to_dict(obj):
    """Recursively serialize a dataclass/enum/datetime tree to JSON-safe primitives.

    Rules:
    - Enum → .value
    - datetime → .isoformat()
    - dataclass → dict (None-valued fields omitted)
    - list → list (recurse each element)
    - dict → dict (recurse values, omit None values)
    - primitives pass through
    """
    if obj is None:
        return None
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            k: v
            for k, v in (
                (f.name, _to_dict(getattr(obj, f.name)))
                for f in dataclasses.fields(obj)
            )
            if v is not None
        }
    if isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: v for k, v in ((k, _to_dict(v)) for k, v in obj.items()) if v is not None}
    return obj


def serialize_landing(assessment: Assessment) -> dict:
    """Build the landing JSON dict: metadata + summary + cost + failures."""
    result = {
        "assessment_id": assessment.assessment_id,
        "generated_at": assessment.generated_at.isoformat(),
        "project_id": assessment.project_id,
        "summary": _to_dict(assessment.summary),
        "cost": _to_dict(assessment.cost),
        "failures": _to_dict(assessment.failures),
    }
    return result


def serialize_entities(assessment: Assessment) -> tuple[list[dict], list[dict]]:
    """Serialize all entities once; return (effort_entities, query_entities).

    Avoids calling _to_dict() twice on TABLE entities (which appear in both views).
    The result is memoized on the assessment instance: JSONWriter and HTMLWriter both
    call this in the default ``--format json,html`` run, and the recursive walk over
    every entity (column schemas, view SQL) is the most expensive serialization step
    at large-warehouse scale.
    """
    cached = getattr(assessment, "_serialized_entities", None)
    if cached is not None:
        return cached
    effort: list[dict] = []
    query: list[dict] = []
    for e in assessment.entities:
        d = _to_dict(e)
        # Add physical and logical size for display
        d["logical_size_gb"] = e.size_gb
        pb = e.physical_bytes
        d["physical_size_gb"] = round(pb / (1024 ** 3), 4) if pb is not None else round(e.size_gb * k.ASSUMED_PHYSICAL_RATIO, 4)
        query.append(d)
        if e.population is EntityPopulation.TABLE:
            effort.append(d)
    assessment._serialized_entities = (effort, query)
    return assessment._serialized_entities


# Fields the HTML report's client-side table renderer uses. Full entity dicts carry
# column schemas and view SQL that the report tables never show — dropping them keeps
# the embedded JSON (and thus the report file) small at warehouse scale. The template's
# JS renderer and these allowlists are pinned together by
# tests/unit/test_report_serialize.py::test_report_rows_cover_template_accesses.
_EFFORT_ROW_KEYS = (
    "full_name", "entity_type", "population", "rows",
    "logical_size_gb", "physical_size_gb",
    "effort", "conversion", "load_sync_dml",
)
_QUERY_ROW_KEYS = (
    "full_name", "entity_type", "population",
    "complexity", "depends_on", "rewrite_guidance", "translated_sql", "placement",
)

# Nested fields the renderer never reads. `complexity.constructs` matters most: it
# carries per-construct anonymized SQL snippets, which at query-log scale dominate
# the payload (and would ship SQL text the report never displays).
_NESTED_DROP_KEYS = {
    "complexity": ("constructs",),
    "placement": ("refresh_unverified",),
    "conversion": ("success",),
}


def _project_row(d: dict, keys: tuple[str, ...]) -> dict:
    """Copy the allowlisted keys, pruning nested dead fields without mutating ``d``.

    ``d`` is shared with the JSON sidecar writer, so nested dicts are shallow-copied
    rather than edited in place.
    """
    row = {}
    for key in keys:
        value = d.get(key)
        if value is None:
            continue
        drop = _NESTED_DROP_KEYS.get(key)
        if drop and isinstance(value, dict):
            value = {k: v for k, v in value.items() if k not in drop}
        row[key] = value
    return row


def build_report_rows(effort_entities: list[dict], query_entities: list[dict]) -> dict:
    """Project serialized entity dicts down to the HTML report's table payload.

    Rows without a score are dropped here, mirroring the former template-side
    ``{% if e.effort %}`` / ``{% if e.complexity %}`` guards.
    """
    return {
        "effort": [
            _project_row(d, _EFFORT_ROW_KEYS)
            for d in effort_entities if d.get("effort")
        ],
        "query": [
            _project_row(d, _QUERY_ROW_KEYS)
            for d in query_entities if d.get("complexity")
        ],
    }


