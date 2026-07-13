# Storage target is S3 Tables (Iceberg); Redshift is the query engine

We pivoted the migration target from **Redshift-as-storage** (native tables sized by
node count, with DISTKEY/SORTKEY) to a **decoupled lakehouse**: migrated data lives in
**Amazon S3 Tables (managed Apache Iceberg)**, and **Amazon Redshift Serverless** is the
query/compute engine over it. We chose this because storage and compute now decouple
cleanly — Iceberg stores nested types natively (so STRUCT/ARRAY are no longer a migration
obstacle), Redshift can run `UPDATE/DELETE/MERGE` directly on Iceberg (AWS, Apr 2026), and
Serverless meters compute (RPU-hours) independently of stored volume. **Scope: Serverless
only** — provisioned Redshift and its serverless-vs-provisioned advisor are out.

## Consequences

- Node-sizing-by-storage, DISTKEY/SORTKEY DDL, and the deployment advisor are retired.
- Cost becomes a sum of independent lines (S3 storage + Serverless RPU) rather than node count.
- "Migration complexity" can no longer be one number — see ADR-0002.
- The old Redshift-native-storage path is dropped, not kept as a parallel target. Re-adding
  it later would mean reintroducing a storage-coupled cost/DDL model.
