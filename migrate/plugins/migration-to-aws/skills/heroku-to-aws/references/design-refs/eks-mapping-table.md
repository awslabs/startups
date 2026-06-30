# EKS Mapping Table

**Applies to:** Heroku formations when `preferences.json → design_constraints.kubernetes.value` is `"eks-managed"` or `"eks-or-ecs"`.

Maps each Heroku dyno type to Kubernetes pod resource requests, resource limits, and a recommended EC2 node instance type for EKS managed/self-managed node groups.

## Pod Resource Mapping

> **Data:** [`knowledge/design/eks-pod-sizing.json`](../../knowledge/design/eks-pod-sizing.json)
>
> The dyno-type → EKS pod sizing rows are maintained as structured data in that
> JSON file. Read the `rows` map keyed by Heroku dyno type; each row carries
> `req_cpu` / `req_mem` (pod resource requests), `lim_cpu` / `lim_mem` (limits),
> and `node_type` (recommended EC2 node instance type). The file also holds
> `node_size_rank` (for largest-pod-class-wins node selection), the
> `system_overhead_per_node` constants, and the EKS `cluster` constants.

## Design Rationale

- **CPU requests** match documented dyno CPU shares (standard-1x = 1 share ≈ 250m of a core; 12x shares ≈ 4000m)
- **Memory requests** match documented dyno memory exactly
- **CPU limits** are 2× requests to allow bursting (Heroku dynos can burst above their share)
- **Memory limits** equal requests (prevents OOM from over-allocation — Kubernetes kills pods exceeding memory limits)
- **RAM-optimized types** (performance-l-ram, private-l-ram, shield-l-ram) use `r6i` instances for higher memory-to-CPU ratio

## Node Instance Type Selection

Node types are selected to accommodate **≥4 pods** of the given dyno type on a single node, after accounting for Kubernetes system overhead.

### System Overhead Per Node

| Component                 | CPU          | Memory    |
| ------------------------- | ------------ | --------- |
| kubelet                   | ~100m        | 256Mi     |
| kube-proxy                | ~100m        | 128Mi     |
| AWS VPC CNI               | ~10m per ENI | 128Mi     |
| DaemonSets (total)        | ~290m        | —         |
| **Total system overhead** | **500m**     | **512Mi** |

### Node Capacity Validation

| Node Type    | vCPUs            | Memory             | Allocatable CPU | Allocatable Memory | Fits ≥4 Pods Of                                |
| ------------ | ---------------- | ------------------ | --------------- | ------------------ | ---------------------------------------------- |
| m6i.large    | 2 vCPU (2000m)   | 8 GiB (8192Mi)     | 1500m           | 7680Mi             | standard-1x, standard-2x, private-s, shield-s  |
| m6i.xlarge   | 4 vCPU (4000m)   | 16 GiB (16384Mi)   | 3500m           | 15872Mi            | performance-m, private-m, shield-m             |
| m6i.4xlarge  | 16 vCPU (16000m) | 64 GiB (65536Mi)   | 15500m          | 65024Mi            | performance-l, private-l, shield-l             |
| r6i.4xlarge  | 16 vCPU (16000m) | 128 GiB (131072Mi) | 15500m          | 130560Mi           | performance-l-ram, private-l-ram, shield-l-ram |
| m6i.8xlarge  | 32 vCPU (32000m) | 128 GiB (131072Mi) | 31500m          | 130560Mi           | performance-xl, private-xl, shield-xl          |
| m6i.16xlarge | 64 vCPU (64000m) | 256 GiB (262144Mi) | 63500m          | 261632Mi           | performance-2xl, private-2xl, shield-2xl       |

## Matching Rules

- **Exact case-insensitive matching**: dyno type string is compared case-insensitively (e.g., `Standard-1X` matches `standard-1x`)
- **Error on unknown types**: if the input dyno type is not one of the 19 recognized types listed above, the lookup produces a mapping rejection error indicating the unsupported dyno type name
- This behavior is consistent with the existing Dyno_Type_Table used for Fargate mappings

## Lookup Rules

1. **Input**: Heroku dyno type string (case-insensitive)
2. **Exact match** → return pod resource requests, limits, and recommended node type
3. **No match** → error: reject mapping with message indicating the unsupported dyno type name

## Usage Context

This table is consumed by the Design Engine's EKS branch. When `design_constraints.kubernetes.value` is `"ecs-fargate"` or absent, this table is not consulted — the existing `dyno-type-table.md` (Fargate path) is used instead.
