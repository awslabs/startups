"""Ingest an AWS resource inventory (Resource Explorer live pull or a local
export).

Discovery source is AWS Resource Explorer, which captures BOTH
CloudFormation-managed resources AND resources created outside IaC (Terraform,
Pulumi, console). Each resource carries a type, region, and service code.

Docs: https://docs.aws.amazon.com/resource-explorer/latest/userguide/welcome.html
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Sample fixture shipped with the skill. TESTS ONLY: it must never be loaded on
# the runtime path (the live pull is the preferred source; for offline use pass
# an explicit --topology <path>). Tests reference this constant directly. Lives
# next to the code under scripts/fixtures/.
SAMPLE_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_topology.json"

# Display name used when a resource's service cannot be confidently resolved to
# a known AWS service name. Such resources are KEPT (shown as unknown), never
# silently dropped, so the inventory count stays honest.
UNKNOWN_SERVICE = "unknown"

# CloudFormation type namespace to a HIPAA-list display name. The HIPAA list is
# matched by normalized display name, so we resolve a human name here. Extend as
# needed; unknown namespaces are reported as `unknown` rather than dropped.
_CFN_NAMESPACE_TO_SERVICE = {
    "AWS::S3": "Amazon S3",
    "AWS::EC2": "Amazon EC2",
    "AWS::RDS": "Amazon RDS",
    "AWS::Lambda": "AWS Lambda",
    "AWS::SQS": "Amazon SQS",
    "AWS::SNS": "Amazon SNS",
    "AWS::DynamoDB": "Amazon DynamoDB",
    "AWS::Transcribe": "AWS Transcribe",
    "AWS::ComprehendMedical": "Amazon Comprehend Medical",
    "AWS::HealthLake": "Amazon HealthLake",
    "AWS::ECS": "Amazon ECS",
    "AWS::Logs": "Amazon CloudWatch Logs",
    "AWS::ElasticLoadBalancingV2": "Elastic Load Balancing",
    "AWS::ElasticLoadBalancing": "Elastic Load Balancing",
    "AWS::SecretsManager": "AWS Secrets Manager",
    "AWS::ApiGateway": "Amazon API Gateway",
    "AWS::ApiGatewayV2": "Amazon API Gateway",
    "AWS::SageMaker": "Amazon SageMaker",
    "AWS::Kinesis": "Amazon Kinesis",
    "AWS::Events": "Amazon EventBridge",
    "AWS::StepFunctions": "AWS Step Functions",
    "AWS::Cognito": "Amazon Cognito",
    "AWS::Route53": "Amazon Route 53",
    "AWS::SSM": "AWS Systems Manager",
    "AWS::Elasticsearch": "Amazon OpenSearch Service",
    "AWS::OpenSearchService": "Amazon OpenSearch Service",
    "AWS::EFS": "Amazon Elastic File System",
}

# service-slug (e.g. "amazon-s3") to display name, for exports that carry a
# lowercase service key instead of, or in addition to, a CFN type.
_SLUG_TO_SERVICE = {
    "amazon-s3": "Amazon S3",
    "amazon-ec2": "Amazon EC2",
    "amazon-rds": "Amazon RDS",
    "aws-lambda": "AWS Lambda",
    "amazon-sqs": "Amazon SQS",
    "amazon-sns": "Amazon SNS",
    "amazon-dynamodb": "Amazon DynamoDB",
    "aws-transcribe": "AWS Transcribe",
    "amazon-comprehend-medical": "Amazon Comprehend Medical",
    "amazon-healthlake": "Amazon HealthLake",
}

# AWS Resource Explorer short service codes (e.g. "s3", "ec2") to a HIPAA-list
# display name. RE's result carries `Service` as a short code, not an "amazon-*"
# slug, so the live pull needs this map. Extended beyond the first ten because
# several HIPAA-eligible services (logs, elasticloadbalancing, secretsmanager,
# apigateway, sagemaker, kinesis, events, states, cognito-idp, route53, ssm, es,
# elasticfilesystem) previously came back `unknown`/not-on-list from their RE
# codes. Codes still not in this map are reported as `unknown` (an "unmapped"
# verdict), never silently as not-on-list.
_RE_SERVICE_CODE_TO_SERVICE = {
    "s3": "Amazon S3",
    "ec2": "Amazon EC2",
    "rds": "Amazon RDS",
    "lambda": "AWS Lambda",
    "sqs": "Amazon SQS",
    "sns": "Amazon SNS",
    "dynamodb": "Amazon DynamoDB",
    "transcribe": "AWS Transcribe",
    "comprehendmedical": "Amazon Comprehend Medical",
    "comprehend-medical": "Amazon Comprehend Medical",
    "healthlake": "Amazon HealthLake",
    # Extended set: RE codes for services that are HIPAA-eligible but were
    # previously unresolved.
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
    "ecs": "Amazon ECS",
}

_KNOWN_DISCOVERY_PATHS = ("cloudformation", "resource-explorer")


@dataclass
class NormalizedResource:
    """A single resource, normalized down to what the checks need.

    `resolved` is True when the service was confidently mapped to a known AWS
    display name, False when it could not be mapped. When False, `service` is
    UNKNOWN_SERVICE and the HIPAA check must return an "unmapped" verdict rather
    than "not-on-list" (we cannot assert membership for a service we could not
    even name). `raw_service` carries the original code/slug/type for display.
    """

    resource_id: str
    service: str  # HIPAA-list display name, e.g. "Amazon S3", or UNKNOWN_SERVICE
    region: str
    resolved: bool = True
    raw_service: str = ""


@dataclass
class TopologyIngestResult:
    resources: list[NormalizedResource] = field(default_factory=list)
    # Which discovery paths the topology export reports as active.
    discovery_paths: list[str] = field(default_factory=list)
    # Account the inventory came from, when the export/live pull carried one.
    account_id: Optional[str] = None


def load_topology(path: str | Path) -> dict[str, Any]:
    """Load a topology JSON export from disk into a dict."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _resolve_service(resource: dict[str, Any]) -> tuple[Optional[str], str]:
    """Resolve a resource to a HIPAA-list display name.

    Returns a (display_name, raw) tuple:
      - display_name is a known AWS display name when the service could be
        confidently mapped, else None (caller shows it as UNKNOWN_SERVICE).
      - raw is the best raw identifier for display (service code/slug or CFN
        type), so an unmapped resource still shows WHAT it was.

    Preference order:
      1. Explicit "amazon-*"/"aws-*" service slug (local export style).
      2. AWS Resource Explorer short service code, e.g. "s3" (live pull style).
      3. CloudFormation "resource_type" namespace, e.g. "AWS::S3::Bucket".
    No best-effort title-casing fallback: a code we do not know is left
    unresolved (display None) so the HIPAA check reports it as `unmapped`,
    never a false `not-on-list`.
    """
    slug = (resource.get("service") or "").strip().lower()
    rtype = (resource.get("resource_type") or resource.get("type") or "").strip()
    raw = slug or rtype

    if slug in _SLUG_TO_SERVICE:
        return _SLUG_TO_SERVICE[slug], raw
    if slug in _RE_SERVICE_CODE_TO_SERVICE:
        return _RE_SERVICE_CODE_TO_SERVICE[slug], raw

    if rtype:
        namespace = "::".join(rtype.split("::")[:2])  # e.g. "AWS::S3"
        if namespace in _CFN_NAMESPACE_TO_SERVICE:
            return _CFN_NAMESPACE_TO_SERVICE[namespace], raw

    # Unknown but present: keep the resource, flag it as unresolved.
    return None, raw


def _resolve_discovery_paths(topology: dict[str, Any]) -> list[str]:
    """Extract active discovery paths from the export, else empty list."""
    raw = topology.get("discovery_paths") or topology.get("discoveryPaths") or []
    if not isinstance(raw, list):
        return []
    # Keep known paths in a stable order; ignore anything unexpected.
    present = {str(p).strip().lower() for p in raw}
    return [p for p in _KNOWN_DISCOVERY_PATHS if p in present]


def normalize(topology: dict[str, Any]) -> TopologyIngestResult:
    """Parse a topology export into a normalized resource list.

    Tolerant of missing fields. A resource with no resolvable service is KEPT
    and marked unresolved (service=UNKNOWN_SERVICE, resolved=False) rather than
    dropped, so e.g. an AWS::ECS::Cluster shows up as `unknown` instead of
    vanishing. Only resources with no identifier at all are skipped. Region is
    collected where present (empty string when absent). Also returns the active
    discovery paths and the account id declared by the export.
    """
    resources: list[NormalizedResource] = []
    for res in topology.get("resources", []) or []:
        if not isinstance(res, dict):
            continue
        resource_id = str(res.get("resource_id") or res.get("id") or res.get("arn") or "").strip()
        if not resource_id:
            continue  # genuinely unidentifiable; nothing to report
        display, raw = _resolve_service(res)
        resolved = display is not None
        service = display if resolved else UNKNOWN_SERVICE
        region = str(res.get("region") or "").strip()
        resources.append(
            NormalizedResource(
                resource_id=resource_id,
                service=service,
                region=region,
                resolved=resolved,
                raw_service=raw,
            )
        )

    account_id = topology.get("account_id") or topology.get("accountId")
    return TopologyIngestResult(
        resources=resources,
        discovery_paths=_resolve_discovery_paths(topology),
        account_id=str(account_id).strip() if account_id else None,
    )


def ingest(path: str | Path) -> TopologyIngestResult:
    """Convenience wrapper: load + normalize a topology export from `path`.

    `path` is REQUIRED and has no default. This is deliberate: nothing in the
    runtime path may silently fall back to the bundled sample fixture. The
    sample (SAMPLE_FIXTURE) is for tests only; callers that want it must pass it
    explicitly.
    """
    return normalize(load_topology(path))
