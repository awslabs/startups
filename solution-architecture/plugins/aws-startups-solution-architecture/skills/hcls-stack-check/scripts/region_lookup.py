"""Region classification + service EU-availability lookup.

is_eu_region() is pure and offline. service_offers_eu_region() queries the AWS
global-infrastructure SSM PUBLIC parameters
(/aws/service/global-infrastructure/services/<slug>/regions) to learn which
regions a service offers. AWS calls use your standard AWS credentials (the
default boto3 credential chain). To target a specific named profile, set the
AWS_PROFILE environment variable; if it is unset, the default chain is used.
"""
from __future__ import annotations

import os
from typing import Optional, TypedDict

# Optional named profile. When unset, boto3's default credential chain is used
# (env vars, shared config, SSO, instance role, etc.). No profile is hardcoded.
AWS_PROFILE = os.environ.get("AWS_PROFILE")
# The global-infrastructure parameters live in us-east-1.
_SSM_REGION = "us-east-1"

# Canonical EU region set for the data-residency check. NOTE on exclusions:
#   - eu-west-2 (London) is in the UK, which left the EU; it is NOT an EU region.
#   - eu-central-2 (Zurich) is in Switzerland, which is not an EU member state.
# Both carry the "eu-" prefix but are outside the EU, so they are deliberately
# excluded here. Membership is by the real jurisdiction, not the region prefix.
EU_REGIONS: frozenset[str] = frozenset(
    {
        "eu-central-1",  # Frankfurt
        "eu-west-1",     # Ireland
        "eu-west-3",     # Paris
        "eu-north-1",    # Stockholm
        "eu-south-1",    # Milan
        "eu-south-2",    # Spain
    }
)

# Region status outcomes for the EU column (tri-state, never a false "no").
EU_YES = "yes"
EU_NO = "no"
EU_GLOBAL = "global"
EU_UNKNOWN = "unknown"

# Global (non-regional) AWS service ARNs report an empty or "aws-global"-style
# region. Those resources have no single data-residency region, so the EU column
# must read "global", not a misleading "no".
_GLOBAL_REGION_MARKERS = frozenset({"", "aws-global", "global", "us-gov-global", "aws-cn-global"})

# Known display-name to SSM service-slug mappings for common services. The SSM
# global-infrastructure service slugs are short codes (e.g. "s3", "ec2").
_KNOWN_SLUGS = {
    "s3": "s3",
    "ec2": "ec2",
    "rds": "rds",
    "lambda": "lambda",
    "dynamodb": "dynamodb",
    "sqs": "sqs",
    "sns": "sns",
    "transcribe": "transcribe",
    "comprehend medical": "comprehendmedical",
    "healthlake": "healthlake",
    "braket": "braket",
}


class EuAvailability(TypedDict):
    offers_eu: Optional[bool]  # True/False, or None when unknown
    eu_regions_offered: list
    resolved_slug: Optional[str]


def is_eu_region(region: str) -> bool:
    """Return True if the given region is in the EU region set."""
    return region in EU_REGIONS


def eu_region_status(region: Optional[str]) -> str:
    """Classify a resource's region for the EU column (tri-state).

    Returns one of:
      - EU_YES     the region is an EU region.
      - EU_GLOBAL  the resource is global / non-regional (empty or an
                   "aws-global"-style marker). It has no single residency region.
      - EU_UNKNOWN region is missing/unparseable in a way that is neither clearly
                   EU, clearly non-EU, nor clearly global.
      - EU_NO      a real, non-EU regional location.

    Empty/global regions deliberately map to EU_GLOBAL / EU_UNKNOWN rather than a
    misleading EU_NO.
    """
    r = (region or "").strip().lower()
    if r in _GLOBAL_REGION_MARKERS:
        # Empty string is ambiguous: could be a global service or just missing
        # metadata. Treat a truly empty value as unknown, named global markers
        # as global.
        return EU_UNKNOWN if r == "" else EU_GLOBAL
    if r in EU_REGIONS:
        return EU_YES
    return EU_NO


def resolve_service_slug(service: str) -> Optional[str]:
    """Best-effort map a display name ("Amazon S3") to an SSM slug ("s3").

    Lowercases, strips a leading "amazon "/"aws ", checks a known map, then
    falls back to the collapsed remainder (last token for multi-word names).
    Returns None when nothing usable can be derived.
    """
    n = " ".join((service or "").split()).strip().lower()
    if not n:
        return None
    for prefix in ("amazon ", "aws "):
        if n.startswith(prefix):
            n = n[len(prefix):].strip()
            break
    if n in _KNOWN_SLUGS:
        return _KNOWN_SLUGS[n]
    # Fallback: single word to itself, multi-word to the collapsed string, and
    # also try the last token (covers cases like "elastic compute cloud").
    collapsed = n.replace(" ", "")
    return collapsed or None


def service_offers_eu_region(service: str) -> EuAvailability:
    """Return whether a service offers at least one EU region, via SSM.

    Uses boto3 SSM (default credential chain, or AWS_PROFILE env var if set)
    against the public
    global-infrastructure parameters. Never crashes the run: if the slug cannot
    be resolved, the SSM path returns nothing, or the call errors, returns
    offers_eu=None (unknown) so the report can show "region availability:
    unknown".

    Return shape:
        {"offers_eu": True|False|None, "eu_regions_offered": [...],
         "resolved_slug": str|None}
    """
    slug = resolve_service_slug(service)
    if not slug:
        return EuAvailability(offers_eu=None, eu_regions_offered=[], resolved_slug=None)

    try:
        import boto3  # imported lazily so offline unit tests need no boto3

        session = boto3.Session(profile_name=AWS_PROFILE) if AWS_PROFILE else boto3.Session()
        ssm = session.client("ssm", region_name=_SSM_REGION)
        path = f"/aws/service/global-infrastructure/services/{slug}/regions"
        regions: list = []
        paginator = ssm.get_paginator("get_parameters_by_path")
        for page in paginator.paginate(Path=path):
            for param in page.get("Parameters", []):
                value = param.get("Value")
                if value:
                    regions.append(value)
    except Exception:
        # Auth, permission, network, or unknown-service errors: unknown result.
        return EuAvailability(offers_eu=None, eu_regions_offered=[], resolved_slug=slug)

    if not regions:
        # Slug did not resolve to a real service path.
        return EuAvailability(offers_eu=None, eu_regions_offered=[], resolved_slug=slug)

    eu_offered = sorted(r for r in regions if r in EU_REGIONS)
    return EuAvailability(
        offers_eu=bool(eu_offered),
        eu_regions_offered=eu_offered,
        resolved_slug=slug,
    )
