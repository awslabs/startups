"""Pytest for topology_ingest + region_lookup."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import region_lookup  # noqa: E402
import topology_ingest  # noqa: E402


def test_sample_fixture_exists():
    assert topology_ingest.SAMPLE_FIXTURE.exists()


def test_region_classification_eu_and_non_eu():
    assert region_lookup.is_eu_region("eu-west-1") is True
    assert region_lookup.is_eu_region("us-east-1") is False


def test_normalize_returns_three_resources():
    topo = topology_ingest.load_topology(topology_ingest.SAMPLE_FIXTURE)
    result = topology_ingest.normalize(topo)
    assert len(result.resources) == 3


def test_unmapped_resource_is_kept_not_dropped():
    # An AWS::ECS::Cluster-style resource with an unknown service code must be
    # KEPT and flagged unresolved, not silently dropped.
    topo = {
        "resources": [
            {"resource_id": "arn:aws:xyz:eu-west-1:1:thing/1", "service": "madeup-code"},
        ]
    }
    result = topology_ingest.normalize(topo)
    assert len(result.resources) == 1
    res = result.resources[0]
    assert res.resolved is False
    assert res.service == topology_ingest.UNKNOWN_SERVICE
    assert res.raw_service == "madeup-code"


def test_extended_re_codes_resolve_previously_unknown_services():
    # These RE service codes previously came back unknown/not-on-list; they must
    # now resolve to known display names.
    cases = {
        "logs": "Amazon CloudWatch Logs",
        "elasticloadbalancing": "Elastic Load Balancing",
        "secretsmanager": "AWS Secrets Manager",
        "apigateway": "Amazon API Gateway",
        "sagemaker": "Amazon SageMaker",
        "kinesis": "Amazon Kinesis",
        "events": "Amazon EventBridge",
        "states": "AWS Step Functions",
        "cognito-idp": "Amazon Cognito",
        "route53": "Amazon Route 53",
        "ssm": "AWS Systems Manager",
        "es": "Amazon OpenSearch Service",
        "elasticfilesystem": "Amazon Elastic File System",
    }
    for code, expected in cases.items():
        topo = {"resources": [{"resource_id": f"arn::{code}", "service": code}]}
        result = topology_ingest.normalize(topo)
        assert result.resources[0].resolved is True, code
        assert result.resources[0].service == expected, code


def test_ecs_cluster_cfn_type_resolves():
    # AWS::ECS::Cluster was the reviewer's example of a dropped type; it now maps.
    topo = {"resources": [{"resource_id": "arn::ecs", "resource_type": "AWS::ECS::Cluster"}]}
    result = topology_ingest.normalize(topo)
    assert result.resources[0].resolved is True
    assert result.resources[0].service == "Amazon ECS"


def test_account_id_is_captured():
    topo = {"account_id": "111122223333", "resources": []}
    assert topology_ingest.normalize(topo).account_id == "111122223333"
