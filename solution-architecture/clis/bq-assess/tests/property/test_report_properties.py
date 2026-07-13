"""Phase 6 property tests for report writers (P24-P26).

Validates: JSON/HTML round-trip, offline safety, credential filtering.
"""

from __future__ import annotations

import json
import os
import re
import tempfile

from hypothesis import given, settings

from bq_assess.models import Assessment
from bq_assess.report.html_writer import HTMLWriter
from bq_assess.report.json_writer import JSONWriter

from tests.conftest import assessment


# ---------------------------------------------------------------------------
# Credential patterns for P26
# ---------------------------------------------------------------------------

# Patterns that indicate credential leakage
_CREDENTIAL_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"),
    re.compile(r'"private_key"\s*:'),
    re.compile(r'"client_email"\s*:\s*"[^"]+@[^"]+\.iam\.gserviceaccount\.com"'),
    re.compile(r'"token"\s*:\s*"ya29\.[A-Za-z0-9_-]+'),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
]


# ---------------------------------------------------------------------------
# Phase 6 Property Tests (P24-P26): normative Assessment model
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Property 24: JSON round-trip and populations (R19 — normative model)
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(a=assessment())
def test_p24_json_roundtrip_and_populations(a: Assessment) -> None:
    """P24: JSON round-trip fidelity and population filtering.

    For any Assessment: 3 files written, valid JSON, correct assessment_id,
    effort has only TABLE, query has all, union of full_names = all entities.
    """
    out_dir = tempfile.mkdtemp()
    paths = JSONWriter().write(a, out_dir)

    # Exactly 3 files
    assert len(paths) == 3

    landing_path = [p for p in paths if "landing" in p][0]
    effort_path = [p for p in paths if "effort" in p][0]
    query_path = [p for p in paths if "query" in p][0]

    # Valid JSON
    with open(landing_path) as f:
        landing = json.load(f)
    with open(effort_path) as f:
        effort = json.load(f)
    with open(query_path) as f:
        query = json.load(f)

    # assessment_id matches
    assert landing["assessment_id"] == a.assessment_id
    assert effort["assessment_id"] == a.assessment_id
    assert query["assessment_id"] == a.assessment_id

    # Landing has required top-level keys
    for key in ["generated_at", "project_id", "summary", "cost", "failures"]:
        assert key in landing

    # Effort file: only TABLE population
    for e in effort["entities"]:
        assert e["population"] == "TABLE"

    # Query file: includes all entities
    assert len(query["entities"]) == len(a.entities)

    # Cross-reference: union of full_names
    effort_names = {e["full_name"] for e in effort["entities"]}
    query_names = {e["full_name"] for e in query["entities"]}
    all_names = effort_names | query_names
    expected_names = {e.full_name for e in a.entities}
    assert all_names == expected_names


# ---------------------------------------------------------------------------
# Property 25: HTML offline and confidence banners (R20)
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(a=assessment())
def test_p25_html_offline_and_banners(a: Assessment) -> None:
    """P25: HTML is offline-safe and confidence banners appear correctly.

    For any Assessment: single HTML file with all tabs, no http/https URLs,
    LOW-confidence banners appear when needed, no CSV produced.
    """
    out_dir = tempfile.mkdtemp()
    paths = HTMLWriter().write(a, out_dir)

    assert len(paths) == 1
    assert paths[0].endswith(".html")

    with open(paths[0]) as f:
        html = f.read()

    # Offline (R20.7): no external ASSET references — scripts, stylesheets, images,
    # fonts, imports. A blanket "http:// not in html" is wrong: customer DATA (rewrite
    # guidance, SQL text, dataset names) may legitimately contain URL strings, and
    # autoescaped text content is not a network dependency. Assert on the constructs
    # that would actually make the browser fetch something.
    for needle in (
        'src="http', "src='http",              # <script>/<img>/<iframe> loads
        'href="http', "href='http",            # <link rel=stylesheet> / external links
        "url(http", "url('http", 'url("http',  # CSS url() fetches
        "@import",                              # CSS imports
        "<script src", "<link rel=",            # any non-inlined script/style at all
    ):
        assert needle not in html, f"external asset reference in HTML: {needle!r}"

    # All tabs present
    assert 'id="tab-landing"' in html
    assert 'id="tab-effort"' in html
    assert 'id="tab-query"' in html

    # LOW compute_confidence → banner
    if a.cost.compute_confidence.value == "LOW":
        assert "Low Confidence Cost Estimate" in html

    # LOW sql_surface_confidence → banner
    if a.summary.sql_surface_confidence.value == "LOW":
        assert "Low Confidence SQL Analysis" in html

    # No CSV in output
    files = os.listdir(out_dir)
    assert not any(f.endswith(".csv") for f in files)


# ---------------------------------------------------------------------------
# Property 26: No credentials in output (R22.3 / R22.6 — normative model)
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(a=assessment())
def test_p26_no_credentials_in_output(a: Assessment) -> None:
    """P26: No credentials leak into any output file (JSON or HTML).

    Scans for service-account keys, client emails, and token patterns.
    """
    out_dir = tempfile.mkdtemp()
    json_paths = JSONWriter().write(a, out_dir)
    html_paths = HTMLWriter().write(a, out_dir)

    for path in json_paths + html_paths:
        with open(path) as f:
            content = f.read()
        for pattern in _CREDENTIAL_PATTERNS:
            assert not pattern.search(content), (
                f"Credential pattern {pattern.pattern!r} found in {path}"
            )
