"""Tests for region_lookup: pure slug normalizer + unknown handling. Offline.

The live SSM call is network-marked and skipped in offline runs.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import region_lookup as rl  # noqa: E402


def test_is_eu_region():
    assert rl.is_eu_region("eu-west-1") is True
    assert rl.is_eu_region("us-east-1") is False


def test_london_and_zurich_are_not_eu():
    # eu-west-2 (London, UK) and eu-central-2 (Zurich, CH) are outside the EU
    # despite the "eu-" prefix.
    assert rl.is_eu_region("eu-west-2") is False
    assert rl.is_eu_region("eu-central-2") is False


def test_remaining_eu_regions_are_eu():
    for r in ("eu-central-1", "eu-west-1", "eu-west-3", "eu-north-1", "eu-south-1", "eu-south-2"):
        assert rl.is_eu_region(r) is True, r


def test_eu_region_status_tristate():
    assert rl.eu_region_status("eu-west-1") == rl.EU_YES
    assert rl.eu_region_status("us-east-1") == rl.EU_NO
    assert rl.eu_region_status("eu-west-2") == rl.EU_NO  # London: real, non-EU
    # Empty region is ambiguous -> unknown, not a false "no".
    assert rl.eu_region_status("") == rl.EU_UNKNOWN
    assert rl.eu_region_status(None) == rl.EU_UNKNOWN
    # Named global markers -> global, not "no".
    assert rl.eu_region_status("aws-global") == rl.EU_GLOBAL
    assert rl.eu_region_status("global") == rl.EU_GLOBAL


def test_resolve_service_slug_known_and_prefixes():
    assert rl.resolve_service_slug("Amazon S3") == "s3"
    assert rl.resolve_service_slug("AWS Lambda") == "lambda"
    assert rl.resolve_service_slug("Amazon Comprehend Medical") == "comprehendmedical"
    assert rl.resolve_service_slug("Braket") == "braket"


def test_resolve_service_slug_empty_is_none():
    assert rl.resolve_service_slug("") is None
    assert rl.resolve_service_slug("   ") is None


def test_service_offers_eu_region_unknown_when_slug_unresolvable():
    res = rl.service_offers_eu_region("")
    assert res["offers_eu"] is None
    assert res["eu_regions_offered"] == []
    assert res["resolved_slug"] is None


def test_service_offers_eu_region_unknown_on_boto_error(monkeypatch):
    # Simulate boto3 raising (auth/permission/network): must return unknown.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "boto3":
            raise RuntimeError("simulated credential error")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    res = rl.service_offers_eu_region("Amazon S3")
    assert res["offers_eu"] is None
    assert res["resolved_slug"] == "s3"


@pytest.mark.network
@pytest.mark.skip(reason="network + AWS creds, run explicitly with valid AWS credentials")
def test_service_offers_eu_region_live():
    res = rl.service_offers_eu_region("Amazon S3")
    assert res["offers_eu"] is True
    assert res["resolved_slug"] == "s3"
