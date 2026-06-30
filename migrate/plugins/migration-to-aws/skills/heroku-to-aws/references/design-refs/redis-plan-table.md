# Heroku Redis Plan → ElastiCache Sizing Table

## Description

This table maps Heroku Redis (Key-Value Store) plan tiers to recommended AWS ElastiCache for Redis node types. The Design Engine uses this table to select the smallest ElastiCache node type whose available memory meets or exceeds the source plan's memory limit.

## Lookup Table

> **Data:** [`knowledge/design/redis-elasticache-sizing.json`](../../knowledge/design/redis-elasticache-sizing.json)
>
> The Heroku Redis plan → ElastiCache sizing rows are maintained as structured
> data in that JSON file. Read the `rows` map keyed by Heroku plan; each row
> carries `node_type`, `ha`, and `encryption`. The `memory_limit` and
> `redis_version` fields are provenance only — do NOT recompute the node type from
> `memory_limit`, and do NOT derive the engine version from `redis_version` (the
> engine version is pinned; see the Redis version note below).

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
