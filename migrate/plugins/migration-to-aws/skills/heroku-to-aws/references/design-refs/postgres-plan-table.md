# Heroku Postgres Plan → RDS/Aurora Sizing Table

## Description

This table maps Heroku Postgres plan tiers to recommended AWS RDS PostgreSQL and Aurora PostgreSQL instance classes. The Design Engine uses this table to select the smallest AWS instance class that meets or exceeds the source plan's RAM, storage, and connection capacity.

## Lookup Table

| Heroku Plan | RAM | Storage | Connections | HA | Connection Pooling | Recommended RDS Instance Class | Recommended Aurora Instance Class |
|------------|-----|---------|-------------|----|--------------------|-------------------------------|----------------------------------|
| essential-0 | 0 MB (shared) | 1 GB | 20 | No | No | db.t4g.micro | db.t4g.medium |
| essential-1 | 0 MB (shared) | 10 GB | 20 | No | No | db.t4g.micro | db.t4g.medium |
| essential-2 | 0 MB (shared) | 32 GB | 40 | No | No | db.t4g.micro | db.t4g.medium |
| hobby-dev | 0 MB (shared) | 1 GB | 20 | No | No | db.t4g.micro | db.t4g.medium |
| hobby-basic | 0 MB (shared) | 10 GB | 20 | No | No | db.t4g.micro | db.t4g.medium |
| standard-0 | 4 GB | 64 GB | 120 | No | Yes | db.t4g.medium | db.t4g.medium |
| standard-2 | 8 GB | 256 GB | 400 | Yes | Yes | db.m6g.large | db.r6g.large |
| standard-3 | 15 GB | 512 GB | 500 | Yes | Yes | db.m6g.xlarge | db.r6g.xlarge |
| standard-4 | 30 GB | 1 TB | 500 | Yes | Yes | db.m6g.2xlarge | db.r6g.2xlarge |
| standard-5 | 61 GB | 1 TB | 500 | Yes | Yes | db.m6g.4xlarge | db.r6g.4xlarge |
| standard-6 | 122 GB | 1.5 TB | 1500 | Yes | Yes | db.m6g.8xlarge | db.r6g.8xlarge |
| standard-7 | 244 GB | 2 TB | 1500 | Yes | Yes | db.m6g.16xlarge | db.r6g.16xlarge |
| premium-0 | 4 GB | 64 GB | 120 | Yes | Yes | db.t4g.medium | db.t4g.medium |
| premium-2 | 8 GB | 256 GB | 400 | Yes | Yes | db.m6g.large | db.r6g.large |
| premium-3 | 15 GB | 512 GB | 500 | Yes | Yes | db.m6g.xlarge | db.r6g.xlarge |
| premium-4 | 30 GB | 1 TB | 500 | Yes | Yes | db.m6g.2xlarge | db.r6g.2xlarge |
| premium-5 | 61 GB | 1 TB | 500 | Yes | Yes | db.m6g.4xlarge | db.r6g.4xlarge |
| premium-6 | 122 GB | 1.5 TB | 1500 | Yes | Yes | db.m6g.8xlarge | db.r6g.8xlarge |
| premium-7 | 244 GB | 2 TB | 1500 | Yes | Yes | db.m6g.16xlarge | db.r6g.16xlarge |
| premium-8 | 488 GB | 3 TB | 1500 | Yes | Yes | db.r6g.16xlarge | db.r6g.16xlarge |
| premium-9 | 768 GB | 4 TB | 1500 | Yes | Yes | db.x2g.16xlarge | db.r6g.16xlarge |
| private-0 | 4 GB | 64 GB | 120 | Yes | Yes | db.t4g.medium | db.t4g.medium |
| private-2 | 8 GB | 256 GB | 400 | Yes | Yes | db.m6g.large | db.r6g.large |
| private-3 | 15 GB | 512 GB | 500 | Yes | Yes | db.m6g.xlarge | db.r6g.xlarge |
| private-4 | 30 GB | 1 TB | 500 | Yes | Yes | db.m6g.2xlarge | db.r6g.2xlarge |
| private-5 | 61 GB | 1 TB | 500 | Yes | Yes | db.m6g.4xlarge | db.r6g.4xlarge |
| private-6 | 122 GB | 1.5 TB | 1500 | Yes | Yes | db.m6g.8xlarge | db.r6g.8xlarge |
| private-7 | 244 GB | 2 TB | 1500 | Yes | Yes | db.m6g.16xlarge | db.r6g.16xlarge |
| shield-0 | 4 GB | 64 GB | 120 | Yes | Yes | db.t4g.medium | db.t4g.medium |
| shield-2 | 8 GB | 256 GB | 400 | Yes | Yes | db.m6g.large | db.r6g.large |
| shield-3 | 15 GB | 512 GB | 500 | Yes | Yes | db.m6g.xlarge | db.r6g.xlarge |
| shield-4 | 30 GB | 1 TB | 500 | Yes | Yes | db.m6g.2xlarge | db.r6g.2xlarge |
| shield-5 | 61 GB | 1 TB | 500 | Yes | Yes | db.m6g.4xlarge | db.r6g.4xlarge |
| shield-6 | 122 GB | 1.5 TB | 1500 | Yes | Yes | db.m6g.8xlarge | db.r6g.8xlarge |
| shield-7 | 244 GB | 2 TB | 1500 | Yes | Yes | db.m6g.16xlarge | db.r6g.16xlarge |

## Interpretation Notes

- **Service selection rule**:
  - If user availability preference is `single-az` or `multi-az` → select **RDS PostgreSQL** using the "Recommended RDS Instance Class" column.
  - If user availability preference is `multi-az-ha` or `multi-region` → select **Aurora PostgreSQL** using the "Recommended Aurora Instance Class" column.
  - If availability preference is unset or unrecognized → default to `multi-az` + RDS PostgreSQL and include a warning.
- **Sizing rule**: Select the smallest instance class that meets or exceeds the source plan's RAM and vCPU capacity. The table already maps each plan to the minimum adequate instance class.
- **Storage rule**: Configure RDS/Aurora storage allocation to meet or exceed the source plan's storage column value.
- **Connection pooling**: If the source Heroku Postgres plan has connection pooling enabled, include **RDS Proxy** in the design.
- **HA column**: Indicates whether the source plan includes high availability. When HA is "Yes" and the user selects RDS, configure Multi-AZ deployment.
- **Shield plans**: These are HIPAA/PCI-compliant equivalents of private plans. Map identically to private plans but note the compliance requirement in the design.

## Error Handling

If a plan tier is not found in this table, reject the mapping and report an error:

> "Unrecognized heroku-postgresql plan tier: `{plan}`. Cannot determine AWS sizing. Deferring to specialist engagement."
