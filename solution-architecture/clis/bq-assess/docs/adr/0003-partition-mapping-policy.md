# Partition/sort mapping: clean mappings are annotations, non-clean are scored effort

When mapping BigQuery partitioning/clustering to Iceberg partition transforms and sort
order (S3 Tables `CreateTable` accepts both at create time), we treat **clean 1:1 mappings
as zero-effort annotations the tool derives automatically**, and **non-clean mappings as
scored Migration Effort with a "review this transform" flag**. Clean = explicit-field time
partitioning (DAY/HOUR/MONTH/YEAR → `day/hour/month/year(col)`) and multi-column sort
order. Non-clean = **ingestion-time** partitioning (`_PARTITIONTIME`, no real column),
**range** partitioning (no Iceberg range transform — `bucket`/`truncate` aren't
equivalent), and ambiguous multi-column clustering intent.

We did this because a blanket "partitioning is free on Iceberg" would silently mis-handle
the cases where the tool genuinely _cannot_ derive the right layout and a human must decide
— and a blanket "partitioning is always effort" would penalize the common clean case.

## Consequences

- The scanner must capture `range_partitioning` (today it reads only `time_partitioning`,
  so range-partitioned tables currently look unpartitioned — a latent bug).
- Effort scoring distinguishes partition _kinds_, not just presence/absence.
- The slot↔transform mapping table and the exact non-clean set should be verified against
  live S3 Tables transform support at implementation.
