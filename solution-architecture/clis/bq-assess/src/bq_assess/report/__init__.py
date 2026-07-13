"""Report generation: three mirrored JSON files + three HTML interfaces (Landing/Effort/Query).

No CSV output in the target design (ADR-0001 / R20.8). See
``.kiro/specs/phase1-assessment-tool/SCRUM_NOTES.md`` for the #2 restructure decision.

All legacy code migrated to the normative writers as of Phase 8 (8.1).
"""

from bq_assess.report.html_writer import HTMLWriter  # noqa: F401
from bq_assess.report.json_writer import JSONWriter  # noqa: F401

__all__ = ["HTMLWriter", "JSONWriter"]
