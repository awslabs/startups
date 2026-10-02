"""Topology SOURCE layer: resolve WHERE the topology graph comes from.

This module sits in front of topology_ingest.normalize(). It answers "where do
I get the raw topology dict from" and returns that dict unchanged for
normalize() to consume. Two sources are supported:

  Mode A, LOCAL FILE (dev/testing/offline): a path to an existing .json file is
  read and json.load()'d. No env-var hack is needed, just pass the path.

  Mode B, LIVE PULL (default): enumerate the current account's resources via AWS
  Resource Explorer at runtime using the caller's own AWS credentials (the
  default credential chain, or AWS_PROFILE if set), OR a role the USER explicitly
  names via assume_role_arn. The resulting dict is handed to normalize().

Why the caller's own credentials (not the DevOps Agent account role): the AWS
DevOps Agent account role trusts only `aidevops.amazonaws.com` and carries
confused-deputy conditions, so a plain sts:AssumeRole with user credentials
fails and making it work would mean loosening that trust policy. Resource
Explorer run with the caller's own credentials (or a role the user names and is
allowed to assume) enumerates the same inventory without touching the agent
role.

Fail-closed philosophy: if the live pull cannot be completed (no Resource
Explorer index, auth failure, call error), we raise TopologySourceError with an
actionable message rather than returning empty, partial, or fabricated data.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

# Optional named profile. When unset, boto3's default credential chain is used
# (env vars, shared config, SSO, instance role, etc.). No profile is hardcoded,
# same pattern as region_lookup.py / preflight.py.
AWS_PROFILE = os.environ.get("AWS_PROFILE")

# Sentinel meaning "live pull" when passed as the source string.
LIVE = "live"

# Resource Explorer docs (ListResources paginates the full inventory; Search
# silently caps at 1,000 results, so we never use Search here).
RESOURCE_EXPLORER_DOCS = (
    "https://docs.aws.amazon.com/resource-explorer/latest/userguide/"
    "getting-started-setting-up.html"
)


class TopologySourceError(RuntimeError):
    """Raised when the topology cannot be sourced (fail-closed).

    Carries an actionable message so the skill fails loudly rather than
    silently under-reporting or fabricating a topology.
    """


def _looks_like_local_file(source: Optional[str]) -> bool:
    """True when `source` points at an existing .json file on disk."""
    if not source:
        return False
    if source.strip().lower() == LIVE:
        return False
    p = Path(source)
    return p.suffix.lower() == ".json" and p.is_file()


def _make_session():
    """Build a boto3 Session honoring AWS_PROFILE, else the default chain."""
    import boto3  # imported lazily so offline unit tests need no boto3

    return boto3.Session(profile_name=AWS_PROFILE) if AWS_PROFILE else boto3.Session()


def _assume_role_session(session, role_arn: str, external_id: Optional[str], region: Optional[str]):
    """Assume a USER-NAMED role via STS and return a boto3 Session for it.

    This is an OPT-IN path: the caller passes assume_role_arn explicitly for a
    role they own and are allowed to assume (e.g. a read-only inventory role in
    another account). It is NOT the DevOps Agent account role, which only trusts
    aidevops.amazonaws.com and cannot be assumed with user credentials. Fail
    closed on any STS error. Read-only downstream use only.
    """
    from botocore.exceptions import BotoCoreError, ClientError

    import boto3

    sts = session.client("sts")
    kwargs: dict[str, Any] = {
        "RoleArn": role_arn,
        "RoleSessionName": "hcls-stack-readiness-check",
    }
    if external_id:
        kwargs["ExternalId"] = external_id
    try:
        creds = sts.assume_role(**kwargs)["Credentials"]
    except (BotoCoreError, ClientError) as exc:
        raise TopologySourceError(
            f"Could not assume the role you named ({role_arn}) for a read-only "
            "inventory pull. Check that your current principal is allowed to "
            "sts:AssumeRole into it (and the ExternalId if the role requires "
            f"one), or omit --assume-role-arn to use your own credentials. "
            f"(details: {exc})"
        ) from exc

    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=region,
    )


def _caller_account_id(session) -> Optional[str]:
    """Best-effort account id of the credentials the enumeration runs under.

    Used to label the report so a reader knows WHICH account the inventory came
    from (the export's account), independent of whichever profile the caller's
    shell defaults to. Never fatal: returns None if STS is unavailable.
    """
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        return (session.client("sts").get_caller_identity() or {}).get("Account")
    except (BotoCoreError, ClientError, Exception):
        return None


def _resource_explorer_resources(target_session, region: Optional[str]) -> tuple[list[dict], Optional[str]]:
    """Enumerate resources in the target account via AWS Resource Explorer.

    Uses the ListResources operation, NOT Search: Search returns at most 1,000
    results and would silently truncate a larger account while the report still
    reads "OK". ListResources paginates the entire inventory. When an aggregator
    index exists, Resource Explorer enumerates all regions; otherwise it is
    limited to the local index's region (preflight surfaces that gap).

    Returns a tuple of (resources, export_account_id):
      resources: list of normalize()-ready dicts
        {"resource_id", "service", "resource_type", "region", "cfn_managed"}
      export_account_id: the OwningAccountId seen on the resources (the account
        the inventory actually came from), or None if none was present.

    Fail-closed on any RE error (including no index configured).
    """
    from botocore.exceptions import BotoCoreError, ClientError

    re_client = target_session.client("resource-explorer-2", region_name=region)
    resources: list[dict] = []
    export_account_id: Optional[str] = None
    try:
        # ListResources with no QueryString returns every indexed resource; it
        # paginates, so unlike Search it does not cap at 1,000.
        paginator = re_client.get_paginator("list_resources")
        for page in paginator.paginate():
            for item in page.get("Resources", []) or []:
                arn = (item.get("Arn") or "").strip()
                if not arn:
                    continue
                owning_account = (item.get("OwningAccountId") or "").strip()
                if owning_account and export_account_id is None:
                    export_account_id = owning_account
                service_code = (item.get("Service") or "").strip()
                cfn_type = (item.get("CfnResourceType") or "").strip()
                resources.append(
                    {
                        "resource_id": arn,
                        # ingest resolves "service"/"resource_type" to a display
                        # name; we hand it both the RE service code and the CFN
                        # type so its existing resolver logic applies unchanged.
                        "service": service_code,
                        "resource_type": cfn_type,
                        "region": (item.get("Region") or "").strip(),
                        "owning_account_id": owning_account or None,
                        # A resource with a CfnResourceType is CloudFormation
                        # managed; otherwise it is an out-of-IaC / RE-only find.
                        "cfn_managed": bool(cfn_type),
                    }
                )
    except (BotoCoreError, ClientError) as exc:
        raise TopologySourceError(
            "Could not enumerate resources via AWS Resource Explorer: "
            f"{exc}. Ensure Resource Explorer is enabled with an aggregator "
            "index in the target account (so all regions are covered), or run "
            f"against a local export with --topology <path>. See {RESOURCE_EXPLORER_DOCS}."
        ) from exc

    return resources, export_account_id


def fetch_live_topology(region: Optional[str] = None, assume_role_arn: Optional[str] = None, external_id: Optional[str] = None) -> dict[str, Any]:
    """Enumerate the current account's resource-level topology live, fail-closed.

    The topology is DERIVED from AWS Resource Explorer, which covers both
    CloudFormation-managed and out-of-IaC resources, with each resource's real
    Service and Region. By default the enumeration runs under the CALLER's own
    credentials (the default chain, or AWS_PROFILE). The caller MAY instead name
    a role they own and are allowed to assume via `assume_role_arn` (e.g. a
    read-only inventory role in another account). We deliberately do NOT assume
    the DevOps Agent account role: it trusts only aidevops.amazonaws.com and
    carries confused-deputy conditions, so user credentials cannot assume it and
    making them able to would mean loosening that trust policy.

    Pipeline (all read-only; never mutates state):
      1. Build a boto3 session from the default chain (or AWS_PROFILE).
      2. Optionally sts:AssumeRole into a user-named role.
      3. Resource Explorer ListResources (NOT Search; Search caps at 1,000) ->
         map each resource's real Arn, Service, Region, and OwningAccountId into
         the dict shape normalize() consumes.

    Args:
        region: AWS region for the clients. Defaults to the session region.
        assume_role_arn: Optional user-named role ARN to assume first.
        external_id: Optional STS ExternalId for that role.

    Returns:
        The raw topology dict for topology_ingest.normalize(), including an
        "account_id" key naming the account the inventory came from.

    Raises:
        TopologySourceError (fail-closed) when: boto3 is unavailable, the named
        role cannot be assumed, Resource Explorer is unavailable or returns no
        resources, or any call errors. Never returns empty/partial/fabricated.
    """
    # 1. Session via the default credential chain (or AWS_PROFILE).
    try:
        session = _make_session()
        target_region = region or session.region_name
    except Exception as exc:  # boto3 missing, bad profile, etc.
        raise TopologySourceError(
            "Live topology pull requires a usable AWS session (boto3 with the "
            "default credential chain, or AWS_PROFILE). Could not build one: "
            f"{exc}. Run against a local export with --topology <path> for "
            "testing or offline use."
        ) from exc

    # 2. Optionally assume a user-named role. Default: the caller's own creds.
    if assume_role_arn:
        enum_session = _assume_role_session(session, assume_role_arn, external_id, target_region)
    else:
        enum_session = session

    # 3. Enumerate via Resource Explorer ListResources.
    resources, export_account_id = _resource_explorer_resources(enum_session, target_region)
    if not resources:
        raise TopologySourceError(
            "AWS Resource Explorer returned no resources. Ensure Resource "
            "Explorer has an aggregator index with resources indexed in the "
            "target account, or run against a local export with "
            f"--topology <path>. See {RESOURCE_EXPLORER_DOCS}."
        )

    # Fall back to the enumerating identity's account id if no resource carried
    # an OwningAccountId (so the report can still name the account).
    if export_account_id is None:
        export_account_id = _caller_account_id(enum_session)

    # Resource Explorer always contributes the resource-explorer discovery path
    # (it is how we enumerated). CloudFormation coverage is asserted only when
    # at least one resource actually carried a CfnResourceType.
    any_cfn = any(r.get("cfn_managed") for r in resources)
    discovery_paths = ["resource-explorer"]
    if any_cfn:
        discovery_paths.insert(0, "cloudformation")

    return {
        "resources": resources,
        "discovery_paths": discovery_paths,
        "account_id": export_account_id,
    }


def load_topology(source: Optional[str] = None, assume_role_arn: Optional[str] = None, external_id: Optional[str] = None) -> dict[str, Any]:
    """Resolve the topology source and return the raw topology dict.

    Modes:
      - LOCAL FILE: `source` is a path to an existing .json file. It is read and
        json.load()'d. This is the dev/testing/offline path.
      - LIVE PULL (default): `source` is None or the string "live". The topology
        is enumerated via Resource Explorer by fetch_live_topology(), under the
        caller's own credentials or an optional user-named role.

    The resolver is explicit about which mode ran: it prints a one-line
    "topology source: ..." note. The returned dict is unchanged, ready for
    topology_ingest.normalize().

    Raises:
        TopologySourceError: on a live-pull failure, or when a non-live source
        string is given that is not an existing .json file (fail-closed).
    """
    if _looks_like_local_file(source):
        path = Path(source)  # type: ignore[arg-type]
        try:
            with open(path, "r", encoding="utf-8") as fh:
                topology = json.load(fh)
        except (OSError, ValueError) as exc:
            raise TopologySourceError(
                f"Could not read local topology file {path}: {exc}"
            ) from exc
        print(f"topology source: local file {path}")
        return topology

    # A non-live, non-file string is a mistake, fail closed rather than
    # silently falling through to a live pull.
    if source and source.strip().lower() != LIVE:
        raise TopologySourceError(
            f"Topology source {source!r} is neither an existing .json file nor "
            f"the literal 'live'. Pass a path to a local export, or 'live' (the "
            f"default) to enumerate the account via Resource Explorer."
        )

    print("topology source: live (Resource Explorer)")
    return fetch_live_topology(assume_role_arn=assume_role_arn, external_id=external_id)
