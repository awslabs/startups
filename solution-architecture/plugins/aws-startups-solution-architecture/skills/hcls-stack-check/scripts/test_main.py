"""Pytest for the main wiring: build_rows + EU cell + report rendering. Offline.

Exercises the new behaviors: unmapped resources become an `unmapped` verdict and
an `unknown (<raw>)` service cell (never dropped); EU column is tri-state; the
report labels a dev-override HIPAA source honestly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import main  # noqa: E402
import region_lookup  # noqa: E402
import report  # noqa: E402
import topology_ingest  # noqa: E402

# In-memory HIPAA snapshot (live shape) so no network is touched.
_SNAP = {
    "services": [{"name": "Amazon S3", "caveat": None}],
    "source": "live",
    "fetched_at": "2026-09-23T00:00:00+00:00",
    "disclaimer": "disc",
}


def test_build_rows_marks_unmapped_resource():
    result = topology_ingest.TopologyIngestResult(
        resources=[
            topology_ingest.NormalizedResource(
                resource_id="arn::x", service="unknown", region="eu-west-1",
                resolved=False, raw_service="madeup-code",
            )
        ],
        discovery_paths=["resource-explorer"],
    )
    rows = main.build_rows(result, _SNAP)
    assert rows[0]["hipaa_eligible"] == "unmapped"
    assert rows[0]["service"] == "unknown (madeup-code)"
    # Row must still render (not dropped).
    assert "unmapped" in report.render_row(rows[0])


def test_build_rows_resolved_service_eu_cell():
    result = topology_ingest.TopologyIngestResult(
        resources=[
            topology_ingest.NormalizedResource(
                resource_id="arn::s3", service="Amazon S3", region="eu-west-1",
                resolved=True, raw_service="s3",
            ),
            topology_ingest.NormalizedResource(
                resource_id="arn::rds", service="Amazon RDS", region="us-east-1",
                resolved=True, raw_service="rds",
            ),
        ],
        discovery_paths=["resource-explorer"],
    )
    rows = main.build_rows(result, _SNAP)
    assert rows[0]["eu"] == "yes"
    assert rows[1]["eu"] == "no"
    # Amazon S3 is on the snapshot; Amazon RDS is not.
    assert rows[0]["hipaa_eligible"] == "yes"
    assert rows[1]["hipaa_eligible"] == "not-on-list"


def test_eu_cell_global_region_is_not_a_false_no(monkeypatch):
    # A global service (empty region marker) with the availability lookup stubbed
    # must read "global", never "no".
    monkeypatch.setattr(
        region_lookup, "service_offers_eu_region",
        lambda svc: {"offers_eu": True, "eu_regions_offered": ["eu-west-1"], "resolved_slug": "r53"},
    )
    res = topology_ingest.NormalizedResource(
        resource_id="arn::r53", service="Amazon Route 53", region="aws-global",
        resolved=True, raw_service="route53",
    )
    cell = main._eu_cell(res)
    assert cell.startswith("global")
    assert "service offers EU" in cell


def test_report_labels_dev_override_source():
    dev_snap = dict(_SNAP, source="dev-override")
    line = report.render_hipaa_source_line(dev_snap)
    assert "dev-override" in line
    assert "live, fetched" not in line


def test_report_live_source_line_unchanged():
    line = report.render_hipaa_source_line(_SNAP)
    assert line.startswith("**HIPAA list: live, fetched")


def test_report_footer_includes_account_id():
    out = report.render_report([], ["resource-explorer"], {"severity": "OK", "message": "m"}, _SNAP, "live", account_id="111122223333")
    assert "Inventory account: 111122223333" in out
