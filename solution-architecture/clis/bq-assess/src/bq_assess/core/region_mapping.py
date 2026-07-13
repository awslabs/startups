"""BQ location → AWS region mapping (shared by collector and full tool)."""

from __future__ import annotations

BQ_LOCATION_TO_AWS_REGION: dict[str, str] = {
    "us": "us-east-1",
    "eu": "eu-west-1",
    "us-central1": "us-east-1",
    "us-east1": "us-east-1",
    "us-east4": "us-east-1",
    "us-west1": "us-west-2",
    "us-west2": "us-west-2",
    "northamerica-northeast1": "ca-central-1",
    "southamerica-east1": "sa-east-1",
    "europe-west1": "eu-west-1",
    "europe-west2": "eu-west-2",
    "europe-west3": "eu-central-1",
    "europe-west4": "eu-central-1",
    "australia-southeast1": "ap-southeast-2",
    "australia-southeast2": "ap-southeast-2",
    "asia-southeast1": "ap-southeast-1",
    "asia-northeast1": "ap-northeast-1",
    "asia-south1": "ap-south-1",
}


def bq_location_to_aws_region(location: str | None) -> str:
    """Map a BigQuery dataset location to the nearest AWS region (us-east-1 if unknown)."""
    loc = (location or "").strip().lower()
    return BQ_LOCATION_TO_AWS_REGION.get(loc, "us-east-1")
