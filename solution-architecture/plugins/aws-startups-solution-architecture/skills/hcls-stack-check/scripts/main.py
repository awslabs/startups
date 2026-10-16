"""Entry point: wire source -> ingest -> checks -> report.

Usage:
    uv run --project <scripts dir> python <scripts dir>/main.py \
        [--topology <path|live>] [--assume-role-arn <arn> [--external-id <id>]]

Default is a LIVE pull: enumerate the current account's resources via AWS
Resource Explorer using the caller's own credentials (default chain or
AWS_PROFILE). Pass --assume-role-arn to run under a role you own and are allowed
to assume. Pass a local .json export path (via --topology or a bare positional
arg) for testing or offline use.
"""
from __future__ import annotations

import argparse
import sys

import hipaa_check
import hipaa_source
import preflight
import region_lookup
import report
import topology_ingest
import topology_source as topology_source_module


def _re_status_safe(region: str, session=None) -> dict:
    """Get Resource Explorer status, tolerant of AWS call failures.

    check_resource_explorer_enabled already handles ResourceNotFound (enabled
    False) and permission errors (enabled None with an "error" key). This wrapper
    is a final safety net: any unexpected exception is treated as undetermined
    (enabled None) so the pipeline still runs and we avoid a false HIGH. When a
    `session` is passed, the check runs in THAT account (the one the inventory
    came from), not the caller's default profile.
    """
    try:
        return preflight.check_resource_explorer_enabled(region, session=session)
    except Exception as exc:
        return {
            "enabled": None,
            "index_type": None,
            "is_aggregator": False,
            "aggregator_region": None,
            "checked_region": region,
            "account_id": None,
            "error": str(exc),
        }


# EU-region status -> EU column value. Global/unknown surface honestly rather
# than a misleading "no".
_EU_STATUS_TO_CELL = {
    region_lookup.EU_YES: "yes",
    region_lookup.EU_NO: "no",
    region_lookup.EU_GLOBAL: "global",
    region_lookup.EU_UNKNOWN: "unknown",
}


def _eu_cell(res: "topology_ingest.NormalizedResource") -> str:
    """Compute the EU column value for a resource (tri-state + availability).

    Primary signal is the resource's own region (yes/no/global/unknown). When
    the region itself is unknown (e.g. a global service, or missing metadata) we
    consult service_offers_eu_region() so the cell can say whether the service
    even offers an EU region, instead of a bare "unknown".
    """
    status = region_lookup.eu_region_status(res.region)
    cell = _EU_STATUS_TO_CELL.get(status, "unknown")
    if status in (region_lookup.EU_GLOBAL, region_lookup.EU_UNKNOWN) and res.resolved:
        avail = region_lookup.service_offers_eu_region(res.service)
        offers = avail.get("offers_eu")
        if offers is True:
            return f"{cell} (service offers EU)"
        if offers is False:
            return f"{cell} (no EU region offered)"
    return cell


def build_rows(result: "topology_ingest.TopologyIngestResult", snapshot: dict) -> list[dict]:
    """Combine per-resource HIPAA + EU checks into report rows."""
    index = hipaa_check.build_index(snapshot)
    rows: list[dict] = []
    for res in result.resources:
        if not res.resolved:
            # Service could not be resolved to a known AWS name: report it as
            # unmapped (distinct from not-on-list), never silently dropped.
            verdict = {"verdict": hipaa_check.UNMAPPED, "caveat": None}
            service_display = f"unknown ({res.raw_service})" if res.raw_service else "unknown"
        else:
            verdict = hipaa_check.check_service(res.service, index)
            service_display = res.service
        rows.append(
            {
                "resource_id": res.resource_id,
                "service": service_display,
                "hipaa_eligible": verdict["verdict"],
                "caveat": verdict["caveat"],
                "region": res.region,
                "eu": _eu_cell(res),
            }
        )
    return rows


def run(topology_source: str | None = None, assume_role_arn: str | None = None, external_id: str | None = None) -> str:
    """Run the full pipeline and return the markdown report.

    topology_source.load_topology() (live pull by default, or a local .json
    export path for testing/offline) -> topology_ingest.normalize() ->
    hipaa_source.load_snapshot() -> preflight.assess_coverage() -> per-resource
    HIPAA + EU checks -> report.render_report(...). Both source resolution and
    the HIPAA snapshot are fail-closed.
    """
    raw_topology = topology_source_module.load_topology(
        topology_source, assume_role_arn=assume_role_arn, external_id=external_id
    )
    source_line = _describe_source(topology_source, assume_role_arn)

    snapshot = hipaa_source.load_snapshot()  # live + fail-closed (or dev override)

    ingest_result = topology_ingest.normalize(raw_topology)

    # RE preflight. Probe region is best-effort (first resource region, else a
    # neutral default). RE status can be True, False, or None (undetermined,
    # e.g. permissions). When undetermined and the RE path is not already active,
    # surface an INFO note rather than a false HIGH. The preflight runs against
    # the account the inventory came from; we re-check with the default session
    # here (the live-pull session is internal to topology_source), so note the
    # export's account id in the footer for the reader.
    probe_region = next((r.region for r in ingest_result.resources if r.region), "us-east-1")
    re_status = _re_status_safe(probe_region)
    re_active = "resource-explorer" in set(ingest_result.discovery_paths or [])
    if re_status.get("enabled") is None and not re_active:
        detail = re_status.get("error")
        suffix = f" ({detail})" if detail else ""
        coverage_verdict = {
            "severity": preflight.INFO,
            "message": (
                "Resource Explorer status could not be determined "
                f"(permissions){suffix}. Coverage of non-CloudFormation resources "
                "is unverified."
            ),
        }
    else:
        coverage_verdict = preflight.assess_coverage(ingest_result.discovery_paths, re_status)

    # If the preflight account and the export account disagree, the OK/HIGH
    # verdict was computed against the wrong account; downgrade to INFO.
    export_account = ingest_result.account_id
    checked_account = re_status.get("account_id")
    if export_account and checked_account and export_account != checked_account:
        coverage_verdict = {
            "severity": preflight.INFO,
            "message": (
                f"Resource Explorer status was checked in account {checked_account}, "
                f"but the inventory came from account {export_account}. Coverage "
                "for the inventory's account is unverified; run the preflight with "
                "credentials for that account."
            ),
        }

    rows = build_rows(ingest_result, snapshot)
    return report.render_report(
        rows,
        ingest_result.discovery_paths,
        coverage_verdict,
        snapshot,
        source_line,
        account_id=export_account,
    )


def _describe_source(topology_source: str | None, assume_role_arn: str | None = None) -> str:
    """One-line human description of which topology source run() used.

    Mirrors the resolver's own log line so the report footer states whether the
    topology came from a local file or the live Resource Explorer pull, and
    whether a user-named role was assumed.
    """
    if topology_source and topology_source.strip().lower() != topology_source_module.LIVE:
        return f"local file {topology_source}"
    if assume_role_arn:
        return f"live (Resource Explorer, assumed role {assume_role_arn})"
    return "live (Resource Explorer, caller credentials)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HCLS stack readiness check (factual, not compliance).")
    parser.add_argument(
        "--topology",
        dest="topology",
        default=None,
        help=(
            "Topology source: a path to a local resource inventory .json export "
            "(for testing/offline), or 'live' to enumerate the account via "
            "Resource Explorer. Defaults to live."
        ),
    )
    parser.add_argument(
        "--assume-role-arn",
        dest="assume_role_arn",
        default=None,
        help=(
            "Optional: a role ARN you own and are allowed to assume, used for "
            "the live Resource Explorer enumeration instead of your own "
            "credentials. NOT the DevOps Agent account role."
        ),
    )
    parser.add_argument(
        "--external-id",
        dest="external_id",
        default=None,
        help="Optional STS ExternalId for --assume-role-arn.",
    )
    parser.add_argument(
        "topology_positional",
        nargs="?",
        default=None,
        help="Backward-compat: a bare path is treated as a local .json export.",
    )
    args = parser.parse_args(argv)
    # --topology wins; otherwise a bare positional path is used; otherwise live.
    source = args.topology if args.topology is not None else args.topology_positional
    try:
        print(run(source, assume_role_arn=args.assume_role_arn, external_id=args.external_id))
    except topology_source_module.TopologySourceError as exc:
        # Fail-closed is a valid, correct outcome (e.g. no Resource Explorer
        # index, or no credentials). Print the actionable message cleanly (no
        # traceback) and exit nonzero.
        print(f"topology source error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
