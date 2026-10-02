"""Tests for hipaa_check: normalized-name matching + caveat carry. Offline."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import hipaa_check  # noqa: E402

# Small in-memory snapshot mirroring the real hipaa_source.Snapshot shape.
_SNAP = {
    "services": [
        {"name": "Amazon S3", "caveat": None},
        {"name": "AWS Transcribe", "caveat": "Includes Healthscribe"},
    ],
    "source": "live",
    "fetched_at": "2026-09-23T00:00:00+00:00",
}


def _index():
    return hipaa_check.build_index(_SNAP)


def test_plain_service_returns_yes():
    res = hipaa_check.check_service("amazon-s3".replace("-", " "), _index())
    assert res["verdict"] == hipaa_check.YES
    assert res["caveat"] is None


def test_caveated_service_returns_yes_with_caveat_carrying_caveat():
    res = hipaa_check.check_service("AWS Transcribe", _index())
    assert res["verdict"] == hipaa_check.YES_WITH_CAVEAT
    assert res["caveat"] == "Includes Healthscribe"


def test_normalization_is_prefix_and_case_insensitive():
    # "amazon s3", "S3", "s3" all normalize to the same key.
    assert hipaa_check.check_service("S3", _index())["verdict"] == hipaa_check.YES


def test_unlisted_service_returns_not_on_list():
    assert hipaa_check.check_service("Amazon SQS", _index())["verdict"] == hipaa_check.NOT_ON_LIST


def test_normalize_name_is_single_source_of_truth():
    # hipaa_check.normalize_name must delegate to hipaa_source._normalize_name
    # (no duplicate implementation).
    import hipaa_source

    for name in ("Amazon S3", "AWS Transcribe", "  amazon   ec2 ", ""):
        assert hipaa_check.normalize_name(name) == hipaa_source._normalize_name(name)


def test_unmapped_verdict_constant_exists_and_is_distinct():
    assert hipaa_check.UNMAPPED == "unmapped"
    assert hipaa_check.UNMAPPED != hipaa_check.NOT_ON_LIST
