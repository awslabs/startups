"""Resource Explorer (RE) preflight.

Purpose: make Terraform-heavy customers' discovery COVERAGE GAP visible up front
rather than buried in the report. If Resource Explorer has no AGGREGATOR index,
only ONE region is searched, so resources in other regions (and anything created
outside CloudFormation) will not be discovered.

assess_coverage is a pure verdict function. check_resource_explorer_enabled
makes a real, read-only resource-explorer-2 get_index call via the default AWS
credential chain (or AWS_PROFILE), and degrades to "undetermined" (None) on
permission/credential errors rather than reporting a false result.
"""
from __future__ import annotations

import os
from typing import Iterable, Optional, TypedDict

# Severity labels for the coverage verdict.
HIGH = "HIGH"
INFO = "INFO"
OK = "OK"


# Optional named profile. When unset, boto3's default credential chain is used.
# No profile is hardcoded so the skill works with any user's standard creds.
AWS_PROFILE = os.environ.get("AWS_PROFILE")


class ReStatus(TypedDict):
    enabled: Optional[bool]  # True/False, or None when it could not be determined
    index_type: Optional[str]  # "AGGREGATOR" / "LOCAL" / None
    is_aggregator: bool  # True only when an AGGREGATOR index exists
    aggregator_region: Optional[str]
    checked_region: str
    account_id: Optional[str]  # account the index was checked in


class CoverageVerdict(TypedDict):
    severity: str  # HIGH / INFO / OK
    message: str


def check_resource_explorer_enabled(region: str, session=None) -> ReStatus:
    """Check whether AWS Resource Explorer has an index in a region.

    Uses boto3 resource-explorer-2 (default credential chain, or AWS_PROFILE
    env var if set, unless an explicit `session` is passed) and calls
    get_index() to determine whether an index exists and WHAT TYPE it is. Only
    an AGGREGATOR index searches all regions; a LOCAL index covers one region
    only, so coverage must NOT be reported OK on a local-only index.

    Pass `session` to check the SAME account/role the inventory came from (e.g.
    the session used for the live pull), rather than whatever the caller's shell
    profile defaults to.

    Return shape (ReStatus): enabled True/False/None, index_type, is_aggregator,
    aggregator_region, checked_region, account_id, and an optional "error" key.

    Handling:
      - AGGREGATOR index   -> enabled=True, is_aggregator=True
      - LOCAL index        -> enabled=True, is_aggregator=False
      - no index           -> enabled=False
      - auth/permission err -> enabled=None, plus an "error" key
    """
    result: dict = {
        "enabled": None,
        "index_type": None,
        "is_aggregator": False,
        "aggregator_region": None,
        "checked_region": region,
        "account_id": None,
    }
    try:
        from botocore.exceptions import ClientError

        if session is None:
            import boto3  # imported lazily so offline unit tests need no boto3

            session = boto3.Session(profile_name=AWS_PROFILE) if AWS_PROFILE else boto3.Session()

        # Record which account we are actually checking (best effort). The id is
        # purely informational for the report; if STS is unreachable we leave it
        # as None rather than failing the preflight.
        try:
            result["account_id"] = (session.client("sts").get_caller_identity() or {}).get("Account")
        except Exception:
            result["account_id"] = None

        client = session.client("resource-explorer-2", region_name=region)
        try:
            resp = client.get_index()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("ResourceNotFoundException", "NotFoundException"):
                result["enabled"] = False
                return result  # type: ignore[return-value]
            if code in ("AccessDeniedException", "UnauthorizedException", "AccessDenied"):
                result["error"] = f"permission: {code}"
                return result  # type: ignore[return-value]
            result["error"] = code or str(exc)
            return result  # type: ignore[return-value]

        # An index exists in this region.
        result["enabled"] = True
        index_type = (resp.get("Type") or "").upper()
        result["index_type"] = index_type or None
        if index_type == "AGGREGATOR":
            result["is_aggregator"] = True
            result["aggregator_region"] = region
        return result  # type: ignore[return-value]
    except Exception as exc:  # missing creds, expired token, network, etc.
        result["error"] = str(exc)
        return result  # type: ignore[return-value]


def assess_coverage(discovery_paths: Iterable[str], re_status: ReStatus) -> CoverageVerdict:
    """Assess discovery coverage from active paths + RE status. Pure/implemented.

    - OK:   resource-explorer path is active AND RE has an AGGREGATOR index
            (all regions searched, non-CloudFormation resources covered).
    - INFO: RE path active or enabled, but only a LOCAL index exists, so only
            one region was searched; or enabled but path not surfaced.
    - HIGH: resource-explorer NOT among active discovery paths AND RE disabled;
            non-CloudFormation resources will not be discovered at all.
    """
    paths = set(discovery_paths or [])
    re_active = "resource-explorer" in paths
    enabled = bool(re_status.get("enabled")) if re_status else False
    is_aggregator = bool(re_status.get("is_aggregator")) if re_status else False

    if re_active and is_aggregator:
        return CoverageVerdict(
            severity=OK,
            message=(
                "Resource Explorer discovery path is active with an AGGREGATOR "
                "index, coverage spans all regions and includes "
                "non-CloudFormation resources."
            ),
        )
    if re_active and enabled and not is_aggregator:
        return CoverageVerdict(
            severity=INFO,
            message=(
                "Resource Explorer is active but only a LOCAL index was found, "
                "so only one region was searched. Create an AGGREGATOR index "
                "for all-region coverage."
            ),
        )
    if not enabled:
        return CoverageVerdict(
            severity=HIGH,
            message=(
                "Non-CloudFormation resources (e.g. Terraform, Pulumi, "
                "console-created) will NOT be discovered. Enable AWS Resource "
                "Explorer with an aggregator index for full coverage."
            ),
        )
    return CoverageVerdict(
        severity=INFO,
        message=(
            "Resource Explorer is enabled but its discovery path is not active in "
            "this topology; no RE-only resources were surfaced."
        ),
    )
