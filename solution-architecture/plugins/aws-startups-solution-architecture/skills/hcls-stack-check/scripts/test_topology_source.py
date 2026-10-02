"""Tests for the topology SOURCE layer (topology_source).

Runnable with stdlib only (pytest not installed): each test_* function raises
on failure. A __main__ block runs them all and prints PASS/FAIL. The real live
network call stays skipped: we exercise the paths by (a) monkeypatching
fetch_live_topology to raise, and (b) monkeypatching the session factory so the
real fetch_live_topology drives Resource Explorer ListResources against an
in-memory fake (both the no-index fail-closed case and the happy path) with no
network.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import topology_ingest  # noqa: E402
import topology_source  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_topology.json")


def test_local_file_returns_dict_and_normalizes_to_three():
    topo = topology_source.load_topology(FIXTURE)
    assert isinstance(topo, dict), "expected a dict from the local file source"
    result = topology_ingest.normalize(topo)
    assert len(result.resources) == 3, f"expected 3 resources, got {len(result.resources)}"


def test_live_source_fail_closed_propagates():
    original = topology_source.fetch_live_topology

    def _boom(region=None, **kwargs):
        raise topology_source.TopologySourceError("space not configured")

    topology_source.fetch_live_topology = _boom
    try:
        raised = False
        try:
            topology_source.load_topology("live")
        except topology_source.TopologySourceError:
            raised = True
        assert raised, "expected TopologySourceError to propagate from live pull"
    finally:
        topology_source.fetch_live_topology = original


def test_default_none_is_live_and_fail_closed():
    original = topology_source.fetch_live_topology

    def _boom(region=None, **kwargs):
        raise topology_source.TopologySourceError("space not configured")

    topology_source.fetch_live_topology = _boom
    try:
        raised = False
        try:
            topology_source.load_topology(None)
        except topology_source.TopologySourceError:
            raised = True
        assert raised, "expected TopologySourceError when source is None (default live)"
    finally:
        topology_source.fetch_live_topology = original


def test_bogus_source_string_fails_closed():
    raised = False
    try:
        topology_source.load_topology("not-a-file-and-not-live")
    except topology_source.TopologySourceError:
        raised = True
    assert raised, "expected TopologySourceError for a non-file, non-live source"


def test_fetch_live_topology_fails_closed_when_re_has_no_index():
    # Exercise the REAL fetch_live_topology (no network): monkeypatch the
    # session factory so resource-explorer-2 ListResources raises a ClientError
    # (the "no index configured" condition). It must fail closed with a
    # TopologySourceError whose message points at Resource Explorer.
    try:
        from botocore.exceptions import ClientError
    except Exception:
        print("SKIP test_fetch_live_topology_fails_closed_when_re_has_no_index (no botocore)")
        return

    class _FakePaginator:
        def paginate(self, **kwargs):
            raise ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": "no index"}},
                "ListResources",
            )

    class _FakeReClient:
        def get_paginator(self, name):
            return _FakePaginator()

    class _FakeSession:
        region_name = "eu-central-1"

        def client(self, name, region_name=None):
            return _FakeReClient()

    original = topology_source._make_session
    topology_source._make_session = lambda: _FakeSession()
    try:
        raised = None
        try:
            topology_source.fetch_live_topology()
        except topology_source.TopologySourceError as exc:
            raised = exc
        assert raised is not None, "expected TopologySourceError, got none"
        msg = str(raised)
        assert "Resource Explorer" in msg, msg
        assert "--topology <path>" in msg, msg
    finally:
        topology_source._make_session = original


def test_fetch_live_topology_lists_resources_and_captures_account():
    # Happy path (no network): ListResources returns two resources with an
    # OwningAccountId. fetch_live_topology must build the normalize()-ready dict,
    # capture the account id, and record discovery paths.
    pages = [
        {
            "Resources": [
                {
                    "Arn": "arn:aws:s3:::b1",
                    "Service": "s3",
                    "Region": "eu-west-1",
                    "OwningAccountId": "111122223333",
                    "CfnResourceType": "AWS::S3::Bucket",
                },
                {
                    "Arn": "arn:aws:ecs:eu-west-1:111122223333:cluster/c1",
                    "Service": "ecs",
                    "Region": "eu-west-1",
                    "OwningAccountId": "111122223333",
                },
            ]
        }
    ]

    class _FakePaginator:
        def paginate(self, **kwargs):
            return iter(pages)

    class _FakeReClient:
        def get_paginator(self, name):
            assert name == "list_resources", f"expected ListResources, got {name}"
            return _FakePaginator()

    class _FakeSession:
        region_name = "eu-west-1"

        def client(self, name, region_name=None):
            # No sts get_caller_identity needed: OwningAccountId is present.
            return _FakeReClient()

    original = topology_source._make_session
    topology_source._make_session = lambda: _FakeSession()
    try:
        topo = topology_source.fetch_live_topology()
    finally:
        topology_source._make_session = original

    assert topo["account_id"] == "111122223333", topo
    assert len(topo["resources"]) == 2, topo
    assert "resource-explorer" in topo["discovery_paths"], topo
    # One resource carried a CfnResourceType -> cloudformation path asserted.
    assert "cloudformation" in topo["discovery_paths"], topo


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
