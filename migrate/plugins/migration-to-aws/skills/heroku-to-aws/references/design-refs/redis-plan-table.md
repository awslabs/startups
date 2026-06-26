# Heroku Redis Plan → ElastiCache Sizing Table

## Description

This table maps Heroku Redis (Key-Value Store) plan tiers to recommended AWS ElastiCache for Redis node types. The Design Engine uses this table to select the smallest ElastiCache node type whose available memory meets or exceeds the source plan's memory limit.

## Lookup Table

| Heroku Plan | Memory Limit | HA  | Encryption | Redis Version | Recommended ElastiCache Node Type |
| ----------- | ------------ | --- | ---------- | ------------- | --------------------------------- |
| hobby       | 25 MB        | No  | No         | 6.2           | cache.t4g.micro                   |
| premium-0   | 50 MB        | Yes | Yes        | 7.0           | cache.t4g.micro                   |
| premium-1   | 100 MB       | Yes | Yes        | 7.0           | cache.t4g.micro                   |
| premium-2   | 250 MB       | Yes | Yes        | 7.0           | cache.t4g.micro                   |
| premium-3   | 500 MB       | Yes | Yes        | 7.0           | cache.t4g.small                   |
| premium-4   | 1 GB         | Yes | Yes        | 7.0           | cache.t4g.small                   |
| premium-5   | 2.5 GB       | Yes | Yes        | 7.0           | cache.t4g.medium                  |
| premium-6   | 5 GB         | Yes | Yes        | 7.0           | cache.m6g.large                   |
| premium-7   | 10 GB        | Yes | Yes        | 7.0           | cache.m6g.xlarge                  |
| premium-8   | 15 GB        | Yes | Yes        | 7.0           | cache.m6g.xlarge                  |
| premium-9   | 25 GB        | Yes | Yes        | 7.0           | cache.m6g.2xlarge                 |
| premium-10  | 50 GB        | Yes | Yes        | 7.0           | cache.m6g.4xlarge                 |
| premium-11  | 75 GB        | Yes | Yes        | 7.0           | cache.m6g.8xlarge                 |
| premium-12  | 100 GB       | Yes | Yes        | 7.0           | cache.m6g.8xlarge                 |
| premium-13  | 150 GB       | Yes | Yes        | 7.0           | cache.m6g.12xlarge                |
| premium-14  | 200 GB       | Yes | Yes        | 7.0           | cache.m6g.16xlarge                |
| private-1   | 1 GB         | Yes | Yes        | 7.0           | cache.t4g.small                   |
| private-2   | 2.5 GB       | Yes | Yes        | 7.0           | cache.t4g.medium                  |
| private-3   | 5 GB         | Yes | Yes        | 7.0           | cache.m6g.large                   |
| private-4   | 10 GB        | Yes | Yes        | 7.0           | cache.m6g.xlarge                  |
| private-5   | 25 GB        | Yes | Yes        | 7.0           | cache.m6g.2xlarge                 |
| private-6   | 50 GB        | Yes | Yes        | 7.0           | cache.m6g.4xlarge                 |
| private-7   | 100 GB       | Yes | Yes        | 7.0           | cache.m6g.8xlarge                 |

## Interpretation Notes

- **Matching rule**: Select the row where the Heroku Redis plan exactly matches (case-insensitive) the source add-on's `plan` field.
- **Memory sizing**: The recommended ElastiCache node type provides available memory that meets or exceeds the source plan's memory limit. Select the smallest node type that satisfies the memory constraint.
- **High availability (HA)**:
  - If the source plan has HA = "Yes", configure ElastiCache with **Multi-AZ** enabled and **automatic failover** enabled.
  - If the source plan has HA = "No", configure a single-node ElastiCache cluster without Multi-AZ or failover.
- **Encryption**:
  - If the source plan has Encryption = "Yes", configure ElastiCache with **in-transit encryption** enabled.
  - If the source plan has Encryption = "No", do not enable in-transit encryption.
- **Redis version compatibility**: Select an ElastiCache Redis engine version that is compatible with the source plan's Redis version. Use the same major version where possible (e.g., source 7.0 → ElastiCache engine 7.0).
- **Private plans**: These run in Heroku Private Spaces and require network isolation. The VPC design should account for private connectivity to the ElastiCache cluster.

## Error Handling

If a plan tier is not found in this table, reject the mapping and report an error:

> "Unrecognized heroku-redis plan tier: `{plan}`. Cannot determine ElastiCache node type. Deferring to specialist engagement."
