"""HIPAA Eligible Services list source.

Source of truth is ALWAYS a live runtime fetch of the AWS HIPAA Eligible
Services Reference page. There is no offline cache and no fallback data file.
If the live list cannot be retrieved, or cannot be parsed into a plausible
list, the skill FAILS LOUDLY (raises LiveFetchError) rather than returning
partial, empty, or cached data.

The page is server-rendered HTML with no JSON API. The parser is deliberately
layout resilient: it does not depend on any specific ul, class, id, or DOM
nesting. It applies independent heuristics, then a validation gate decides
whether the result is trustworthy.

No third-party scraping libraries, stdlib urllib plus html.parser only.
"""
from __future__ import annotations

import datetime as _dt
import re
from html.parser import HTMLParser
from typing import Optional, TypedDict
from urllib.request import Request, urlopen
from urllib.parse import urlparse

HIPAA_REFERENCE_URL = "https://aws.amazon.com/compliance/hipaa-eligible-services-reference/"

# A browser-like UA is required, the default urllib UA can be blocked.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Validation gate thresholds. A layout change that breaks parsing should FAIL
# these checks rather than silently under reporting.
MIN_EXPECTED_SERVICES = 50
SENTINEL_SERVICES = ("S3", "EC2", "RDS")

# Sentinel detection regexes. On the live page these services appear under full
# display names with the short code as a whole token or inside parentheses,
# e.g. "Amazon Simple Storage Service (S3)", "Amazon Elastic Compute Cloud
# (Amazon EC2)", "Amazon Relational Database Service (Amazon RDS)". A plain
# normalized-name equality check ("s3" == "simple storage service (s3)") never
# matches, so we detect a sentinel when its short code appears as a whole token
# (word boundaries) anywhere in ANY raw parsed name, which also covers the
# parenthesized form.
_SENTINEL_TOKEN_RE = {
    s: re.compile(rf"\b{re.escape(s)}\b", re.IGNORECASE) for s in SENTINEL_SERVICES
}

# Nav/footer link texts that start with "AWS "/"Amazon " but are NOT services.
# These leak from the page chrome (header nav, footer, related-links) and would
# inflate the count and pollute names. Matched by normalized name (see
# _normalize_name) so the "aws "/"amazon " prefix is already stripped. Kept
# layout-resilient: this is a content denylist, not a CSS/DOM dependency.
_NON_SERVICE_NAMES = frozenset(
    {
        "marketplace",
        "services in scope by compliance program",
        "cloud security",
        "trust center",
        "solutions library",
        "partners",
        "re:post",
        "support overview",
        "accessibility",
        "compliance programs",
        "customer compliance center",
        "compliance resources",
        "documentation",
        "getting started",
        "contact us",
        "free tier",
        "pricing",
    }
)

# Service-name pattern: an entry must start with one of these known prefixes.
_SERVICE_NAME_RE = re.compile(
    r"^(Amazon|AWS|Alexa|Kiro|VM Import|Elastic Load Balancing)\b",
    re.IGNORECASE,
)

# Splits a raw entry into a name plus an optional trailing "[caveat]".
_ENTRY_RE = re.compile(r"^\s*(?P<name>.+?)\s*(?:\[(?P<caveat>.+?)\])?\s*$")

# Verbatim AWS disclaimer. Do not edit the wording.
DISCLAIMER_TEXT = (
    "NOTE: If you are a Covered Entity or Business Associate as defined by the "
    "Health Insurance Portability and Accountability Act of 1996 (as amended, "
    '"HIPAA"), you agree not to use these HIPAA Eligible Services for any '
    "purpose or in any manner involving Protected Health Information (as defined "
    "by HIPAA) without first entering into an AWS business associate agreement.\n"
    "\n"
    "Unless specifically excluded, generally available features of each of the "
    "HIPAA eligible services listed are also considered HIPAA eligible.\n"
    "\n"
    "The services listed above are eligible for workloads involving electronic "
    "Protected Health Information (ePHI). It's important to note that some AWS "
    "services are not listed here. Customers still may use services not listed "
    "here, including within HIPAA Accounts, provided that the services do not "
    "process or store ePHI. For more information, please speak to your AWS "
    "account representative. Customers are responsible for ensuring their own "
    "HIPAA compliance when using any AWS service."
)


class ServiceEntry(TypedDict):
    name: str
    caveat: Optional[str]


class Snapshot(TypedDict):
    services: list  # list[ServiceEntry]
    fetched_at: str  # ISO timestamp
    source: str  # "live" for a network fetch, "dev-override" for a local file
    disclaimer: str


class LiveFetchError(RuntimeError):
    """Raised on fetch failure, parse failure, or validation gate failure."""


class _TextCollector(HTMLParser):
    """Collect <li> inner texts (heuristic A) and anchor / text nodes (B)."""

    def __init__(self) -> None:
        super().__init__()
        self._li_depth = 0
        self._li_buf: list[str] = []
        self.li_texts: list[str] = []
        self.text_nodes: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            if self._li_depth == 0:
                self._li_buf = []
            self._li_depth += 1

    def handle_endtag(self, tag):
        if tag == "li" and self._li_depth > 0:
            self._li_depth -= 1
            if self._li_depth == 0:
                text = " ".join("".join(self._li_buf).split()).strip()
                if text:
                    self.li_texts.append(text)

    def handle_data(self, data):
        if self._li_depth > 0:
            self._li_buf.append(data)
        chunk = " ".join(data.split()).strip()
        if chunk:
            self.text_nodes.append(chunk)


def _split_name_caveat(raw: str) -> ServiceEntry:
    """Split raw entry text into {name, caveat}, caveat from a trailing [..]."""
    raw = " ".join((raw or "").split())
    m = _ENTRY_RE.match(raw)
    if not m:
        return ServiceEntry(name=raw, caveat=None)
    caveat = m.group("caveat")
    return ServiceEntry(name=m.group("name").strip(), caveat=caveat.strip() if caveat else None)


def _looks_like_service(text: str) -> bool:
    """True when text looks like an AWS service entry (not page chrome).

    Must start with a known service-name prefix AND not be a known nav/footer
    link (matched by normalized name against _NON_SERVICE_NAMES). This keeps the
    parser layout-resilient (content-based, no CSS/DOM dependency) while
    excluding leaked header/footer <li> links like "AWS Marketplace" or "AWS
    Trust Center".
    """
    if not _SERVICE_NAME_RE.match(text or ""):
        return False
    return _normalize_name(text) not in _NON_SERVICE_NAMES


def _normalize_name(name: str) -> str:
    """Lowercase and strip a leading 'Amazon '/'AWS ' for de-dupe and sentinels."""
    n = " ".join((name or "").split()).strip()
    for prefix in ("amazon ", "aws "):
        if n.lower().startswith(prefix):
            n = n[len(prefix):]
            break
    return n.lower().strip()


def _dedupe(entries: list) -> list:
    """De-dupe by normalized name, keeping the first (prefer one with a caveat)."""
    out: dict[str, ServiceEntry] = {}
    for e in entries:
        key = _normalize_name(e["name"])
        if not key:
            continue
        if key not in out or (e.get("caveat") and not out[key].get("caveat")):
            out[key] = e
    return list(out.values())


def parse_services(html: str) -> list:
    """Parse service entries from page HTML using independent heuristics.

    Heuristic A: every <li> inner text matching the service-name pattern.
    Heuristic B (fallback when A is too small): all text nodes / anchor texts
    matching the same pattern.

    This function does NOT enforce the validation gate, callers do (so tests can
    exercise the raw parse and the gate separately).
    """
    collector = _TextCollector()
    collector.feed(html)

    a = [_split_name_caveat(t) for t in collector.li_texts if _looks_like_service(t)]
    a = _dedupe(a)

    if len(a) >= MIN_EXPECTED_SERVICES:
        return a

    # Heuristic B fallback: scan all text nodes for the same pattern.
    b_source = list(collector.li_texts) + list(collector.text_nodes)
    b = [_split_name_caveat(t) for t in b_source if _looks_like_service(t)]
    b = _dedupe(b)

    # Return whichever heuristic found more entries.
    return b if len(b) > len(a) else a


def _sentinel_presence(entries: list) -> dict:
    """Map each sentinel to whether its short code appears in any parsed name.

    A sentinel (S3, EC2, RDS) is present when its short code appears as a whole
    token (word boundaries, case-insensitive) in ANY raw service name. This
    matches the live page format where the code sits inside the full display
    name or in parentheses, e.g. "Amazon Simple Storage Service (S3)" or
    "Amazon Elastic Compute Cloud (Amazon EC2)". This does NOT weaken the gate:
    a name must still contain the exact code token, so genuinely absent
    sentinels stay False.
    """
    raw_names = [str(e.get("name") or "") for e in entries]
    return {
        s: any(_SENTINEL_TOKEN_RE[s].search(name) for name in raw_names)
        for s in SENTINEL_SERVICES
    }


def _validate(entries: list) -> None:
    """Validation gate. Raise LiveFetchError if the parsed list is not plausible.

    Requires (a) at least MIN_EXPECTED_SERVICES entries, AND (b) all sentinel
    services (S3, EC2, RDS) present by normalized name. A layout change that
    breaks parsing FAILS here instead of silently under reporting.
    """
    n = len(entries)
    sentinels = _sentinel_presence(entries)
    if n < MIN_EXPECTED_SERVICES or not all(sentinels.values()):
        raise LiveFetchError(
            f"HIPAA list parse failed validation: got {n} services, "
            f"sentinels_present={sentinels}"
        )


def fetch_live_snapshot(timeout: int = 15) -> Snapshot:
    """Fetch, parse, and validate the live HIPAA Eligible Services Reference.

    Returns {"services": [{name, caveat}], "fetched_at": iso, "source": "live",
    "disclaimer": DISCLAIMER_TEXT}. Raises LiveFetchError on non-200 responses,
    network errors, parse failure, or validation gate failure. Never returns
    partial, empty, or cached data.
    """
    # Defence in depth: HIPAA_REFERENCE_URL is a module-level constant (never
    # user-controlled), but assert the scheme/host anyway so a future edit can
    # never turn this into an SSRF or a file:// read. semgrep's dynamic-urllib
    # rule is a false positive here because of this guard + the fixed constant.
    parsed = urlparse(HIPAA_REFERENCE_URL)
    if parsed.scheme != "https" or parsed.netloc != "aws.amazon.com":
        raise LiveFetchError(
            f"Refusing to fetch non-https/non-aws.amazon.com HIPAA reference URL: {HIPAA_REFERENCE_URL}"
        )
    req = Request(HIPAA_REFERENCE_URL, headers={"User-Agent": _BROWSER_UA})
    try:
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected,gitlab.bandit.B310-1 -- URL is a fixed module constant, validated https + exact aws.amazon.com host above; not user-controlled.
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310  # nosec B310
            status = getattr(resp, "status", resp.getcode())
            if status != 200:
                raise LiveFetchError(f"Unexpected HTTP status {status} from {HIPAA_REFERENCE_URL}")
            html = resp.read().decode("utf-8", errors="replace")
    except LiveFetchError:
        raise
    except Exception as exc:  # network, timeout, DNS, etc.
        raise LiveFetchError(f"Live fetch failed: {exc}") from exc

    services = parse_services(html)
    _validate(services)  # fail closed if the parse is not plausible
    return Snapshot(
        services=services,
        fetched_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        source="live",
        disclaimer=DISCLAIMER_TEXT,
    )


def _load_dev_override(path: str) -> Snapshot:
    """Load a snapshot from a local JSON file for dev/testing only.

    Opt-in via the HCLS_SNAPSHOT_FILE env var. This does NOT reintroduce a
    committed fallback: no file is shipped in the repo, the override is entirely
    user-supplied. The same validation gate applies, so a bogus dev file still
    fails closed.

    Accepts either a plain list of entries under "services" or a full Snapshot
    shape. Entries may be {name, caveat} or bare name strings.
    """
    import json as _json

    with open(path, "r", encoding="utf-8") as fh:
        raw = _json.load(fh)
    raw_services = raw.get("services", raw) if isinstance(raw, dict) else raw
    services: list = []
    for item in raw_services or []:
        if isinstance(item, dict):
            services.append(ServiceEntry(name=item.get("name", ""), caveat=item.get("caveat")))
        else:
            services.append(_split_name_caveat(str(item)))
    _validate(services)  # dev override is validated too, fail closed
    return Snapshot(
        services=services,
        fetched_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        # Dev/testing escape hatch: this list came from a local file, NOT a live
        # fetch. Label it honestly so the report does not claim "live, fetched".
        source="dev-override",
        disclaimer=DISCLAIMER_TEXT,
    )


def load_snapshot(timeout: int = 15) -> Snapshot:
    """Resolver the rest of the skill calls. Live only, fail-closed.

    Returns fetch_live_snapshot() and lets any exception propagate so the skill
    fails loudly rather than serving stale or empty data.

    Testing-only override: if the HCLS_SNAPSHOT_FILE env var points to a JSON
    file, that file is read instead of the network. This is a dev/testing escape
    hatch only; it ships no committed data and is opt-in via the env var.
    """
    import os

    override = os.environ.get("HCLS_SNAPSHOT_FILE")
    if override:
        return _load_dev_override(override)
    return fetch_live_snapshot(timeout=timeout)
