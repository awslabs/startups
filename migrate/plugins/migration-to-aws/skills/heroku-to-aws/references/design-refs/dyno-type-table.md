# Dyno Type → Fargate Sizing Table

## Description

This table maps Heroku dyno types to AWS Fargate task definition CPU and memory allocations. The Design Engine uses this table to produce Fargate task definitions that match or exceed the compute capacity of the source Heroku formation.

## Lookup Table

> **Data:** [`knowledge/design/dyno-fargate-sizing.json`](../../knowledge/design/dyno-fargate-sizing.json)
>
> The dyno-type → Fargate sizing rows are maintained as structured data in that
> JSON file. Read the `rows` map keyed by Heroku dyno type; each row carries
> `fargate_cpu` (CPU units, 1024 = 1 vCPU) and `fargate_memory` (MiB). The
> `heroku_cpu_share` and `heroku_memory_mb` fields are provenance only (they
> explain why the row meets-or-exceeds the source) — do NOT recompute the Fargate
> values from them.

## Interpretation Notes

- **Matching rule**: Select the row where the Heroku dyno type exactly matches (case-insensitive) the source formation's `dyno_type` field.
- **CPU units**: Fargate CPU is specified in CPU units where 1024 units = 1 vCPU. Values map to the smallest Fargate-compatible allocation that meets or exceeds the Heroku dyno's CPU share.
- **Memory**: Fargate memory is specified in MiB. Values map to the smallest Fargate-compatible allocation that meets or exceeds the Heroku dyno's memory allocation.
- **Fargate valid combinations**: Fargate enforces specific CPU/memory pairings. All rows in this table use valid Fargate combinations.
- **Desired count**: The source formation `quantity` field maps directly to the Fargate service `desired_count` (valid range: 0–100).
- **Load balancer**: If the process type is `web`, include an Application Load Balancer (ALB) in the design. Non-web process types do not get a load balancer.

## Error Handling

If a dyno type is not found in this table, reject the mapping and report an error:

> "Unsupported dyno type: `{type}`. Cannot map to Fargate. Please contact support or provide manual sizing."
