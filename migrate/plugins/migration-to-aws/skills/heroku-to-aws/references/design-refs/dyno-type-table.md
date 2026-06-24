# Dyno Type → Fargate Sizing Table

## Description

This table maps Heroku dyno types to AWS Fargate task definition CPU and memory allocations. The Design Engine uses this table to produce Fargate task definitions that match or exceed the compute capacity of the source Heroku formation.

## Lookup Table

| Heroku Dyno Type  | CPU (shares) | Memory (MB) | Fargate CPU (units) | Fargate Memory (MiB) |
| ----------------- | ------------ | ----------- | ------------------- | -------------------- |
| standard-1x       | 1x           | 512         | 256                 | 512                  |
| standard-2x       | 2x           | 1024        | 512                 | 1024                 |
| performance-m     | 6x           | 2560        | 1024                | 2048                 |
| performance-l     | 12x          | 14336       | 4096                | 16384                |
| performance-l-ram | 12x          | 30720       | 4096                | 30720                |
| performance-xl    | 12x          | 63488       | 8192                | 65536                |
| performance-2xl   | 12x          | 129024      | 16384               | 122880               |
| private-s         | 1x           | 1024        | 512                 | 1024                 |
| private-m         | 6x           | 2560        | 1024                | 2048                 |
| private-l         | 12x          | 14336       | 4096                | 16384                |
| private-l-ram     | 12x          | 30720       | 4096                | 30720                |
| private-xl        | 12x          | 63488       | 8192                | 65536                |
| private-2xl       | 12x          | 129024      | 16384               | 122880               |
| shield-s          | 1x           | 1024        | 512                 | 1024                 |
| shield-m          | 6x           | 2560        | 1024                | 2048                 |
| shield-l          | 12x          | 14336       | 4096                | 16384                |
| shield-l-ram      | 12x          | 30720       | 4096                | 30720                |
| shield-xl         | 12x          | 63488       | 8192                | 65536                |
| shield-2xl        | 12x          | 129024      | 16384               | 122880               |

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
