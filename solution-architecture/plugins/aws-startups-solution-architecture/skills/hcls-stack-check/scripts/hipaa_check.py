"""HIPAA-eligibility membership check.

Checks whether a resource's service is on AWS's published HIPAA Eligible
Services Reference list. The list is provided by hipaa_source.load_snapshot()
(live-only fetch; fails closed with no cache); entries are {name, caveat}.

Matching is by NORMALIZED NAME: case-insensitive, with leading "Amazon "/"AWS "
prefixes stripped. Caveat text is IGNORED for the membership decision but is
CARRIED into the result so the report can show "eligible*" with the condition.

This is a factual membership check only. Eligibility != compliance.
"""
from __future__ import annotations

import re

import hipaa_source

# Report verdicts for the hipaa_eligible column.
YES = "yes"
YES_WITH_CAVEAT = "yes-with-caveat"
NOT_ON_LIST = "not-on-list"
# Service could not be resolved to a known AWS name (e.g. an unmapped Resource
# Explorer service code). We cannot assert list membership for a service we
# could not even name, so this is DISTINCT from NOT_ON_LIST (which means "named
# and genuinely absent from the list").
UNMAPPED = "unmapped"

# On the live page a service's short code appears in parentheses at the end of
# the full display name, e.g. "Amazon Simple Storage Service (S3)" or "Amazon
# Elastic Compute Cloud (Amazon EC2)". The topology side resolves the same
# service to the short display name ("Amazon S3"), so we ALSO index the
# parenthesized short code as an alias to keep membership matching correct.
_PAREN_CODE_RE = re.compile(r"\(([^)]+)\)\s*$")


def normalize_name(name: str) -> str:
    """Normalize a service name for case-insensitive, prefix-insensitive match.

    Single source of truth: delegates to hipaa_source._normalize_name so the
    topology side and the HIPAA-list side normalize identically (strip a leading
    "Amazon "/"AWS ", lowercase). E.g. "Amazon S3" -> "s3".
    """
    return hipaa_source._normalize_name(name)


def _paren_code_alias(name: str) -> str | None:
    """Extract a normalized short-code alias from a trailing "(...)", or None.

    "Amazon Simple Storage Service (S3)" -> "s3"
    "Amazon Elastic Compute Cloud (Amazon EC2)" -> "ec2"
    Returns None when there is no trailing parenthetical or it is not a plausible
    short code (a short, single token).
    """
    m = _PAREN_CODE_RE.search(name or "")
    if not m:
        return None
    inner = normalize_name(m.group(1))  # strips a leading "amazon "/"aws " too
    # A short code is a single, short token (e.g. "s3", "ec2", "rds", "sqs").
    if inner and " " not in inner and len(inner) <= 8:
        return inner
    return None


def build_index(snapshot: dict | None = None) -> dict[str, str | None]:
    """Build {normalized_name: caveat} from a snapshot's services list.

    `snapshot` is a hipaa_source.Snapshot (or any dict with `services`). If None,
    calls hipaa_source.load_snapshot() (live-only; fails closed with no cache).

    Each service is indexed under its normalized full name AND, when its display
    name ends with a parenthesized short code, under that short-code alias. This
    lets the topology side's short names ("Amazon S3") match the live page's
    full names ("Amazon Simple Storage Service (S3)").
    """
    snap = snapshot if snapshot is not None else hipaa_source.load_snapshot()
    index: dict[str, str | None] = {}
    for entry in snap.get("services", []):
        name = entry.get("name", "")
        caveat = entry.get("caveat")
        index[normalize_name(name)] = caveat
        alias = _paren_code_alias(name)
        if alias and alias not in index:
            index[alias] = caveat
    return index


def check_service(service: str, index: dict[str, str | None] | None = None) -> dict:
    """Return a verdict dict for a single service name.

    Result shape: {"verdict": YES|YES_WITH_CAVEAT|NOT_ON_LIST, "caveat": str|None}.
      - YES             -> matched, no caveat
      - YES_WITH_CAVEAT -> matched, carries the caveat text
      - NOT_ON_LIST     -> no match by normalized name
    """
    idx = index if index is not None else build_index()
    key = normalize_name(service)
    if key not in idx:
        return {"verdict": NOT_ON_LIST, "caveat": None}
    caveat = idx[key]
    if caveat:
        return {"verdict": YES_WITH_CAVEAT, "caveat": caveat}
    return {"verdict": YES, "caveat": None}
