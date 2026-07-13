"""Verified constants for Iceberg conversion (V6, V9).

All values are overridable. Every constant carries source URL + confirmation date.

References:
- V6: https://docs.aws.amazon.com/redshift/latest/dg/querying-iceberg-supported-data-types.html
- V9: https://docs.aws.amazon.com/cli/latest/reference/s3tables/create-table.html
"""

# V6 — TIME is lossy (Redshift cannot read Iceberg time type)
# Confirmed: 2026-06-06
V6_TIME_IS_LOSSY: bool = True
V6_TIME_ICEBERG_TYPE: str = "string"
V6_TIME_LOSS_DESCRIPTION: str = (
    "BigQuery TIME: Iceberg has native time but Redshift cannot read it "
    "over Iceberg. Stored as ISO 8601 string."
)

# V6 — JSON is lossy (no native Iceberg JSON type)
V6_JSON_IS_LOSSY: bool = True
V6_JSON_ICEBERG_TYPE: str = "string"
V6_JSON_LOSS_DESCRIPTION: str = (
    "No native Iceberg JSON type (v2 spec). Stored as string; "
    "structured query semantics lost."
)

# V9 — S3 Tables CreateTable partition transforms
# Confirmed: 2026-06-06
V9_SUPPORTED_PARTITION_TRANSFORMS = (
    "identity", "year", "month", "day", "hour", "bucket", "truncate",
)

# BigQuery time-partition type to Iceberg transform (clean, ADR-0003)
BQ_TO_ICEBERG_PARTITION_TRANSFORM = {
    "DAY": "day",
    "HOUR": "hour",
    "MONTH": "month",
    "YEAR": "year",
}

RANGE_PARTITION_IS_CLEAN: bool = False
