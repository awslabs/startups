"""Render the readiness report as markdown.

Emits a table (resource_id, service, hipaa_eligible, region, eu) plus the
mandatory boundary statement and the list of active discovery paths.
"""
from __future__ import annotations

from typing import Iterable

# Canonical source of the not-a-compliance boundary. MUST appear in every
# report. SKILL.md/README describe this constant; this definition is the source
# of truth (the verbatim AWS HIPAA disclaimer lives in hipaa_source.DISCLAIMER_TEXT).
BOUNDARY_STATEMENT = (
    "> **Boundary:** This report is a factual membership + region check against "
    "AWS-published sources. It is **NOT a compliance assessment** and **NOT legal "
    "advice.** Service eligibility does not imply a compliant deployment."
)

TABLE_HEADER = "| resource_id | service | hipaa_eligible | region | eu |"
TABLE_DIVIDER = "|---|---|---|---|---|"

# Severity -> display badge for the coverage warning block.
_SEVERITY_BADGE = {"HIGH": "🔴 HIGH", "INFO": "🟡 INFO", "OK": "🟢 OK"}


def render_coverage_warning(verdict: dict) -> str:
    """Render the RE coverage verdict as a prominent block for the TOP of the report.

    `verdict` is a preflight.CoverageVerdict: {"severity": str, "message": str}.
    Rendered near the top so a Terraform-heavy customer's coverage gap is
    visible up front rather than buried below the table.
    """
    severity = verdict.get("severity", "INFO")
    badge = _SEVERITY_BADGE.get(severity, severity)
    return (
        f"## Discovery coverage: {badge}\n\n"
        f"> **[{severity}]** {verdict.get('message', '')}"
    )


def render_disclaimer(snapshot: dict | None = None) -> str:
    """Render the verbatim AWS HIPAA disclaimer as a prominent top block.

    Uses the snapshot's "disclaimer" text when present, otherwise falls back to
    hipaa_source.DISCLAIMER_TEXT. This is shown alongside (not instead of) the
    not-a-compliance BOUNDARY_STATEMENT.
    """
    import hipaa_source

    text = (snapshot or {}).get("disclaimer") or hipaa_source.DISCLAIMER_TEXT
    body = "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))
    return "## AWS HIPAA disclaimer\n\n" + body


def render_hipaa_source_line(snapshot: dict) -> str:
    """Render a prominent top-of-report line describing the HIPAA list source.

    `snapshot` is a hipaa_source.Snapshot: {services, source, fetched_at, ...}.
    The list is normally live (the skill fails closed if it cannot be fetched or
    validated). A `source` of "dev-override" means a local file was used via the
    HCLS_SNAPSHOT_FILE escape hatch; label it honestly rather than claiming
    "live, fetched".
    """
    fetched_at = snapshot.get("fetched_at", "unknown")
    count = len(snapshot.get("services", []))
    source = snapshot.get("source", "live")
    if source == "dev-override":
        return f"**HIPAA list: dev-override (local file), loaded {fetched_at} ({count} services)**"
    return f"**HIPAA list: live, fetched {fetched_at} ({count} services)**"


def _hipaa_cell(verdict: str, caveat: str | None) -> str:
    """Format the hipaa_eligible cell text from a verdict + optional caveat."""
    if verdict == "yes":
        return "yes"
    if verdict == "yes-with-caveat":
        return f"yes* ({caveat})" if caveat else "yes*"
    if verdict == "unmapped":
        # Service could not be resolved to a known AWS name, so membership was
        # not checked. Distinct from "not on list" (named and genuinely absent).
        return "unmapped (service not resolved)"
    return "not on list"


def _esc(value: str) -> str:
    """Escape pipe characters so table cells do not break markdown rendering."""
    return str(value).replace("|", "\\|")


def render_row(row: dict) -> str:
    """Render a single markdown table row.

    Expected keys: resource_id, service, hipaa_eligible (yes/yes-with-caveat/
    not-on-list), caveat (str|None), region, eu (yes/no). A YES_WITH_CAVEAT row
    shows the caveat inline, e.g. "yes* (<caveat>)".
    """
    hipaa = _hipaa_cell(row.get("hipaa_eligible", "not-on-list"), row.get("caveat"))
    region = row.get("region") or "(unknown)"
    return "| {rid} | {svc} | {hipaa} | {region} | {eu} |".format(
        rid=_esc(row.get("resource_id", "")),
        svc=_esc(row.get("service", "")),
        hipaa=_esc(hipaa),
        region=_esc(region),
        eu=_esc(row.get("eu", "no")),
    )


def render_report(rows: Iterable[dict], discovery_paths: Iterable[str], coverage_verdict: dict, hipaa_snapshot: dict, topology_source_line: str | None = None, account_id: str | None = None) -> str:
    """Assemble the full markdown report.

    Order, top to bottom:
      1. Title
      2. AWS HIPAA disclaimer (render_disclaimer), verbatim
      3. Not-a-compliance boundary (BOUNDARY_STATEMENT)
      4. HIPAA source line (render_hipaa_source_line)
      5. Coverage warning (render_coverage_warning) at the top of the findings
      6. Results table (resource_id | service | hipaa_eligible | region | eu)
      7. Footer: the topology source (local file vs live), the account the
         inventory came from, and which discovery paths were active
    """
    rows = list(rows)
    paths = list(discovery_paths)

    parts: list[str] = []
    parts.append("# HCLS stack readiness report")
    parts.append(render_disclaimer(hipaa_snapshot))
    parts.append(BOUNDARY_STATEMENT)
    parts.append(render_hipaa_source_line(hipaa_snapshot))
    parts.append("## Findings")
    parts.append(render_coverage_warning(coverage_verdict))

    table = [TABLE_HEADER, TABLE_DIVIDER]
    table.extend(render_row(r) for r in rows)
    if not rows:
        table.append("| (no resources with a resolvable service) | | | | |")
    parts.append("\n".join(table))

    active = ", ".join(paths) if paths else "(none reported)"
    source = topology_source_line or "(unspecified)"
    account = f"\n\nInventory account: {account_id}." if account_id else ""
    parts.append(
        "## Discovery paths active\n\n"
        f"Topology source: {source}.{account}\n\n"
        f"Topology discovery paths active for this export: {active}."
    )

    return "\n\n".join(parts) + "\n"
