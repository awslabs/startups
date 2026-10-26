"""Pytest for preflight. assess_coverage is pure and tested offline; the live
resource-explorer-2 get_index call is exercised by a separate, network-gated test."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import preflight  # noqa: E402


def _status(enabled: bool, is_aggregator: bool = False) -> preflight.ReStatus:
    return {
        "enabled": enabled,
        "index_type": "AGGREGATOR" if is_aggregator else ("LOCAL" if enabled else None),
        "is_aggregator": is_aggregator,
        "aggregator_region": "eu-west-1" if is_aggregator else None,
        "checked_region": "eu-west-1",
        "account_id": None,
    }


def test_high_when_re_disabled_and_only_cloudformation():
    verdict = preflight.assess_coverage(["cloudformation"], _status(False))
    assert verdict["severity"] == preflight.HIGH
    assert "Resource Explorer" in verdict["message"]


def test_ok_requires_aggregator_index():
    # RE path active AND an aggregator index -> OK (all regions covered).
    verdict = preflight.assess_coverage(
        ["cloudformation", "resource-explorer"], _status(True, is_aggregator=True)
    )
    assert verdict["severity"] == preflight.OK


def test_info_when_re_path_active_but_local_only_index():
    # RE path active but only a LOCAL index -> INFO, NOT OK (one region only).
    verdict = preflight.assess_coverage(
        ["cloudformation", "resource-explorer"], _status(True, is_aggregator=False)
    )
    assert verdict["severity"] == preflight.INFO
    assert "LOCAL" in verdict["message"]


def test_info_when_re_enabled_but_path_inactive():
    verdict = preflight.assess_coverage(["cloudformation"], _status(True))
    assert verdict["severity"] == preflight.INFO


@pytest.mark.network
@pytest.mark.skip(reason="network + AWS creds, run explicitly with valid AWS credentials")
def test_re_api_call_live():
    res = preflight.check_resource_explorer_enabled("eu-west-1")
    assert res["checked_region"] == "eu-west-1"
    assert res["enabled"] in (True, False, None)
