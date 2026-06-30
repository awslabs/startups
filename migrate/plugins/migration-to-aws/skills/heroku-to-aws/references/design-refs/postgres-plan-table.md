# Heroku Postgres Plan → RDS/Aurora Sizing Table

## Description

This table maps Heroku Postgres plan tiers to recommended AWS RDS PostgreSQL and Aurora PostgreSQL instance classes. The Design Engine uses this table to select the smallest AWS instance class that meets or exceeds the source plan's RAM, storage, and connection capacity.

## Lookup Table

> **Data:** [`knowledge/design/postgres-rds-sizing.json`](../../knowledge/design/postgres-rds-sizing.json)
>
> The Heroku Postgres plan → RDS/Aurora sizing rows are maintained as structured
> data in that JSON file. Read the `rows` map keyed by Heroku plan; each row
> carries `rds_instance_class` and `aurora_instance_class` (select per the engine
> rule below), plus `storage_gb` (minimum storage to allocate) and a `compliance`
> tag on shield-* rows. The `ram` / `connections` / `ha` / `src_connection_pooling`
> fields are provenance only (source-plan facts that explain the row choice) — do
> NOT recompute the instance class from them.

## Interpretation Notes

- **Service selection rule**:
  - If user availability preference is `single-az` or `multi-az` → select **RDS PostgreSQL** using the row's `rds_instance_class` field.
  - If user availability preference is `multi-az-ha` or `multi-region` → select **Aurora PostgreSQL** using the row's `aurora_instance_class` field.
  - If availability preference is unset or unrecognized → default to `multi-az` + RDS PostgreSQL and include a warning.
- **Sizing rule**: Select the smallest instance class that meets or exceeds the source plan's RAM and vCPU capacity. The table already maps each plan to the minimum adequate instance class.
- **Storage rule**: Configure RDS/Aurora storage allocation to meet or exceed the row's `storage_gb` value.
- **Connection pooling**: If the source Heroku Postgres plan has connection pooling enabled, include **RDS Proxy** in the design.
- **HA field**: The row's `ha` field indicates whether the source plan includes high availability. When `ha` is `true` and the user selects RDS, configure Multi-AZ deployment.
- **Shield plans**: These are HIPAA/PCI-compliant equivalents of private plans. Map identically to private plans but note the compliance requirement in the design.

## Error Handling

If a plan tier is not found in this table, reject the mapping and report an error:

> "Unrecognized heroku-postgresql plan tier: `{plan}`. Cannot determine AWS sizing. Deferring to specialist engagement."
