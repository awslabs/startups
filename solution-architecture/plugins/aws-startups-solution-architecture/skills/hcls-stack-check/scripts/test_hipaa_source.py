"""Tests for hipaa_source: offline parser + validation gate + fail-closed.

The live network call is kept out of offline runs (network-marked skip).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import hipaa_source  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as fh:
        return fh.read()


def test_parser_is_structure_independent():
    # Fixture uses arbitrary/nested markup and a differently-named wrapper.
    entries = hipaa_source.parse_services(_read("hipaa_page_sample.html"))
    names = {hipaa_source._normalize_name(e["name"]) for e in entries}
    assert {"s3", "ec2", "rds"}.issubset(names)
    # nav/footer items (Home, Privacy, ...) must not be picked up.
    assert "home" not in names and "privacy" not in names


def test_parser_carries_caveat():
    entries = hipaa_source.parse_services(_read("hipaa_page_sample.html"))
    by_name = {hipaa_source._normalize_name(e["name"]): e for e in entries}
    assert by_name["transcribe"]["caveat"] == "Includes Healthscribe"


def test_validation_gate_passes_on_full_fixture():
    entries = hipaa_source.parse_services(_read("hipaa_page_sample.html"))
    hipaa_source._validate(entries)  # should not raise


def test_validation_gate_raises_on_too_few_services():
    entries = hipaa_source.parse_services(_read("hipaa_page_too_small.html"))
    with pytest.raises(hipaa_source.LiveFetchError) as exc:
        hipaa_source._validate(entries)
    assert "failed validation" in str(exc.value)


def test_sentinel_gate_matches_live_format_full_names():
    # Regression: the live page lists services under full display names with the
    # short code in parentheses, e.g. "Amazon Simple Storage Service (S3)". The
    # sentinel gate must detect S3/EC2/RDS in that form, not only bare codes.
    entries = [
        {"name": "Amazon Simple Storage Service (S3)", "caveat": None},
        {"name": "Amazon Elastic Compute Cloud (Amazon EC2)", "caveat": None},
        {"name": "Amazon Relational Database Service (Amazon RDS)", "caveat": None},
    ]
    entries += [{"name": f"Amazon Service {i:02d}", "caveat": None} for i in range(47)]
    assert len(entries) == 50
    presence = hipaa_source._sentinel_presence(entries)
    assert presence == {"S3": True, "EC2": True, "RDS": True}
    hipaa_source._validate(entries)  # should not raise


def test_sentinel_gate_still_raises_when_sentinels_absent():
    # Enough entries, but no S3/EC2/RDS anywhere: gate must still fail closed.
    entries = [{"name": f"Amazon Service {i:02d}", "caveat": None} for i in range(60)]
    presence = hipaa_source._sentinel_presence(entries)
    assert presence == {"S3": False, "EC2": False, "RDS": False}
    with pytest.raises(hipaa_source.LiveFetchError):
        hipaa_source._validate(entries)


def test_split_name_caveat_parses_bracketed_caveat():
    entry = hipaa_source._split_name_caveat("AWS Transcribe [Includes Healthscribe]")
    assert entry["name"] == "AWS Transcribe"
    assert entry["caveat"] == "Includes Healthscribe"


def test_no_cache_fallback_symbols_remain():
    # Fail-closed: cache helpers must not exist.
    assert not hasattr(hipaa_source, "_load_cache")
    assert not hasattr(hipaa_source, "SNAPSHOT_PATH")


@pytest.mark.network
@pytest.mark.skip(reason="network call, run explicitly, kept out of offline runs")
def test_fetch_live_snapshot_real_network():
    snap = hipaa_source.fetch_live_snapshot()
    assert snap["source"] == "live"
    assert snap["disclaimer"] == hipaa_source.DISCLAIMER_TEXT
    assert len(snap["services"]) >= hipaa_source.MIN_EXPECTED_SERVICES
