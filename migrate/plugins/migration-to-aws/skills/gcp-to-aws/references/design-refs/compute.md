# Compute Services Design Rubric

**Applies to:** Cloud Run (v1/v2), Cloud Functions (Gen 1/Gen 2), Compute Engine, GKE, App Engine

**Table lookup first:** Check `fast-path.md` **Direct Mappings** for this Terraform type.

- `google_cloud_run_service`, `google_cloud_run_v2_service`, `google_cloudfunctions_function`, and `google_cloudfunctions2_function` are currently in Direct Mappings and usually resolve with `confidence: "deterministic"` when row conditions are met.
- `google_app_engine_application` is now in Direct Mappings (→ Elastic Beanstalk, confidence: `deterministic`) **only when `compute_model` is absent/`"managed_platform"` and `compute` ≠ `"eks"`**; under `compute: "eks"` (Q5 = multi-cloud) it falls through to the rubric and routes to EKS (`confidence: "inferred"`).
- `google_compute_instance` and `google_container_cluster` are not direct-mapped in `fast-path.md`; use the rubric below (typically `confidence: "inferred"`).
- If a resource is not eligible for Direct Mappings (or row conditions are not met), use the rubric below.

## Eliminators (Hard Blockers)

| GCP Service     | AWS               | Blocker                                                                                                                                                                                                                                                                                                                           |
| --------------- | ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cloud Run       | Lambda            | Execution time >15 min → use Fargate                                                                                                                                                                                                                                                                                              |
| Cloud Run       | Fargate           | GPU workload or >16 vCPU or >120 GB memory → use EC2                                                                                                                                                                                                                                                                              |
| Cloud Functions | Lambda            | Python version not supported (e.g., Python 2.7) → use custom runtime on Fargate                                                                                                                                                                                                                                                   |
| GKE             | EKS               | Custom CRI incompatible → manual workaround or ECS. **Auto Mode caveat:** node-level needs Auto Mode disallows (custom AMIs/OS, node-managing privileged DaemonSets, SSH/host access, custom CRI or kubelet flags) → use standard EKS managed node groups (`kubernetes: "eks-standard"`), not Auto Mode.                          |
| Any             | App Runner        | **Closed to new customers (April 30 2026).** Do not target App Runner for new migrations. Use Fargate (default for non-K8s containers), Lambda (event-driven), or EKS Auto Mode (K8s workloads).                                                                                                                                  |
| App Engine      | Elastic Beanstalk | `compute_model: "container_orchestration"` or `"serverless"` in preferences → do not use EB, fall through to Fargate or Lambda _(preference override, not a technical blocker)_. Also `compute: "eks"` (Q5 = multi-cloud) → do not use EB, route to **standard EKS** (portable; not Auto Mode) _(top-level portability override)_ |

## Signals (Decision Criteria)

### Cloud Run

- **Always-on** or **cold-start sensitive** → Fargate (not Lambda)
- **Stateless microservice** + **<15 min execution** → Lambda
- **HTTP-only** + **container-native** → Fargate preferred (better dev/prod parity)

Note: Cloud Run maps to Fargate via deterministic fast-path ("Always"). The `compute_model` preference does not affect Cloud Run mapping.

### Cloud Functions

- **Event-driven** + **<15 min** + **Python/Node/Go** → Lambda
- **Always-on or long** → run as Container on Fargate or ECS

### Compute Engine (VMs)

- **Always-on workload** → EC2 (reserved or on-demand based on cost sensitivity)
- **Batch/periodic jobs** → EC2 with Auto Scaling (scale to 0 in dev)
- **Windows-only workload** → EC2 (Lambda/Fargate support limited)

### GKE

GKE usage signals Kubernetes adoption, so the **default is to keep Kubernetes on EKS Auto Mode** — AWS operates the nodes (the GKE Autopilot equivalent, and AWS's recommended approach going forward). Branch on `preferences.json` → `design_constraints.kubernetes` (set by Q8):

- **`kubernetes = "eks-auto"` or absent** → **EKS Auto Mode** (default). An absent preference resolves to Auto Mode, not Fargate — teams that want to manage nodes or leave Kubernetes say so in Clarify (Q8 B/C).
- **`kubernetes = "eks-standard"`** → **EKS with managed node groups** (standard cluster; user explicitly wants node control).
- **`kubernetes = "ecs-fargate"`** → **Fargate** (user chose to drop Kubernetes).
- **Autopilot signal:** when the source `google_container_cluster` has `config.autopilot_enabled: true`, Auto Mode is the direct 1:1 mapping — record it in the rationale (`"GKE Autopilot → EKS Auto Mode (managed-node equivalent)"`). A Standard cluster (`autopilot_enabled: false`) still defaults to Auto Mode but `eks-standard` is the natural opt-out if the user wants to preserve node pools.
- **Auto Mode eliminator:** if the workload needs node-level customization Auto Mode disallows (see Eliminators), fall back to `eks-standard`, not Fargate.

### App Engine

- **Multi-cloud portability required** (`compute: "eks"` from Q5) → **EKS standard node groups** (`kubernetes: "eks-standard"`) — top-level portability override; takes precedence over the EB default and any `compute_model` preference (Q7b does not fire under multi-cloud). Same override that forces GKE → standard EKS. **Auto Mode is NOT used for multi-cloud** — its node management is AWS-specific and defeats the portability that Q5 requires; a standard EKS cluster is the portable target.
- **Default** → Elastic Beanstalk (PaaS-to-PaaS, preserves managed platform model)
- **User prefers container control** (`compute_model: "container_orchestration"`) → Fargate
- **Event-driven / scale-to-zero required** → Lambda

After selecting Elastic Beanstalk, load `elastic-beanstalk.md` to populate `aws_config` (platform, deployment policy, IAM, VPC, sizing). When `compute: "eks"` routes App Engine to EKS (standard node groups under multi-cloud), do **not** run the EB fan-out or load `elastic-beanstalk.md` — the app_version resources are skipped like any other non-EB path.

## CPU Architecture (Graviton vs x86)

After selecting the AWS compute service, set its CPU architecture. **Load** `references/shared/graviton.md` (tier behavior) and `references/shared/schema-graviton.md` (the `graviton` block schema).

Branch on `preferences.json` → `design_constraints.cpu_architecture.value` (set by Clarify; defaults to `graviton` when all compute services were `tier: ready`):

- **`graviton`** (or absent when the matching `graviton_profile.tier` is `ready`): emit the Graviton instance type for EC2 (e.g., `m7g.xlarge`), Fargate ARM64, Lambda `arm64`, and Graviton families for managed services. Map x86 → Graviton via the table in `graviton.md`.
- **`graviton` with `graviton_profile.tier == "conditional"`**: still target Graviton, but copy the profile's `caveats[]` into the design and add `"validate compatibility with a load test after migration"`.
- **`x86` or `graviton_profile.tier == "incompatible"`**: emit the x86 instance type; record the blocker in the rationale.
- Containers default to **arm64-only** builds; use multi-arch only when `cpu_architecture.value == "mixed"` or the user chose per-service.

Add a `graviton` block (see `schema-graviton.md`) to the service's output. GPU/CUDA workloads are always x86 here and routed to G5/G6 in the rubric eliminators.

## 6-Criteria Rubric

Apply in order; first match wins:

1. **Eliminators**: Does GCP config violate AWS constraints, or does a top-level preference override apply? If yes: switch to alternative. **`compute: "eks"` (Q5 = multi-cloud) is a hard override — App Engine (and all compute) → EKS standard node groups (portable Kubernetes; Auto Mode is NOT used for multi-cloud); stop here, do not evaluate the managed-platform/EB branch below.** For GKE (AWS-only, Auto Mode default), the Auto Mode eliminator applies: node-level customization Auto Mode disallows → `eks-standard`, not Fargate.
2. **Operational Model**: Managed (Lambda, Fargate, **EKS Auto Mode** — AWS operates the nodes) vs Self-Hosted (EC2, **standard EKS managed node groups**)?
   - Prefer managed unless: Always-on + high baseline cost → EC2, or the user explicitly wants node control → `eks-standard`
   - For App Engine sources: Elastic Beanstalk (PaaS-to-PaaS) when `compute_model` is absent or `"managed_platform"` **and `compute` ≠ `"eks"`** (when `compute: "eks"`, the criterion-1 override already selected EKS Auto Mode)
3. **User Preference**: From `preferences.json`: `design_constraints.compute`, `design_constraints.kubernetes`, `design_constraints.cost_sensitivity`?
   - If `compute = "eks"` (Q5 = multi-cloud) → **EKS standard node groups** for all compute, including App Engine (top-level portability override; overrides EB default and `compute_model`). Auto Mode is excluded here — it is AWS-specific and defeats multi-cloud portability.
   - If `kubernetes = "eks-auto"` → **EKS Auto Mode** (keep Kubernetes, AWS runs the nodes)
   - If `kubernetes = "eks-standard"` → **EKS with managed node groups** (user explicitly wants node control)
   - If `kubernetes = "ecs-fargate"` → Fargate (user chose to drop Kubernetes)
   - If `kubernetes` is **absent** → **EKS Auto Mode** for GKE sources (do not default to Fargate; GKE signals Kubernetes adoption). Non-GKE containers (Cloud Run) map to Fargate via their own fast-path.
   - If `cost_sensitivity` present and high → still keep Auto Mode for GKE (lowest-ops K8s); the management fee is modest vs the ops savings — do not silently drop to Fargate against a K8s preference
4. **Feature Parity**: Does GCP config require AWS-unsupported features?
   - Example: GCP auto-scaling to zero + cold-start-sensitive → Fargate (not Lambda)
5. **Cluster Context**: Are other resources in this cluster using EKS/EC2/Fargate?
   - Prefer same platform (affinity)
6. **Simplicity**: Fewer resources = higher score
   - Fargate (1 service) > EC2 (N services for ASG + monitoring)

## Examples

### Example 1: Cloud Run (stateless API)

- GCP: `google_cloud_run_service` (memory=512MB, timeout=60s, min_instances=1)
- Fast-path: `google_cloud_run_service` → Fargate (Always, condition met)
- → **AWS: Fargate (0.5 CPU, 1 GB memory)**
- Confidence: `deterministic` (Direct Mapping, no rubric needed)

### Example 2a: Cloud Functions (event processor, short-running)

- GCP: `google_cloudfunctions_function` (runtime=python39, timeout=540s)
- Fast-path: `google_cloudfunctions_function` → Lambda (Always, condition met)
- → **AWS: Lambda with EventBridge trigger**
- Confidence: `deterministic` (Direct Mapping, no rubric needed)

### Example 2b: Cloud Functions (long-running, timeout exceeds Lambda limit)

- GCP: `google_cloudfunctions_function` (runtime=python39, timeout=1200s)
- Fast-path: `google_cloudfunctions_function` → Lambda (Always)
- However, Eliminator fires: timeout 1200s > Lambda max 900s → **cannot use Lambda**
- Eliminator overrides fast-path → falls through to rubric
- Criterion 2 (Operational Model): Fargate (managed + can handle longer execution)
- → **AWS: Fargate (0.5 CPU, 1 GB memory) with EventBridge trigger**
- Confidence: `inferred` (eliminator forced rubric fallback)

### Example 3: Compute Engine (background job)

- GCP: `google_compute_instance` (machine_type=e2-medium, region=us-central1, startup_script=...)
- Signals: Periodic batch job (inferred from startup script), always-on
- Criterion 1 (Eliminators): PASS
- Criterion 2 (Operational Model): EC2 (explicit compute control)
- Criterion 3 (User Preference): If `design_constraints.gcp_monthly_spend` indicates cost sensitivity, prefer auto-scaling → EC2 + ASG (scale to 0)
- → **AWS: EC2 t4g.medium + Auto Scaling Group (min=0 in dev)** (Graviton default; use t3.medium if `cpu_architecture` is `x86` or the workload is incompatible — see CPU Architecture section)
- Confidence: `inferred`

### Example 4a: App Engine (standard Python web app, default preference)

- GCP: `google_app_engine_application` with one service (`default`) whose `google_app_engine_standard_app_version` has runtime=python39, instance_class=F4, `automatic_scaling`
- Note: `runtime`/`instance_class`/scaling come from the `*_app_version` resource, not the parent. The App Engine fan-out step (`phases/design/design-infra.md`) emits one EB environment per service; `gcp_type` stays `google_app_engine_application`.
- Signals: PaaS deployment, `compute_model` absent or `"managed_platform"`
- Fast-path condition met: `compute_model` not set to `"container_orchestration"` or `"serverless"`
- → **AWS: Elastic Beanstalk (Python 3.9, LoadBalanced, t4g.medium, arm64)** — LoadBalanced from the version's `automatic_scaling`; t4g.medium from `instance_class` F4; Graviton default (per `elastic-beanstalk.md` Sizing Defaults, which size from the version's own config, not Q6)
- Confidence: `deterministic` (App Engine → EB direct mapping, condition met)

### Example 4b: App Engine (user chose container orchestration)

- GCP: `google_app_engine_application` with one service (`default`), app_version runtime=python39, instance_class=F2
- Signals: PaaS deployment, but `compute_model: "container_orchestration"` in preferences
- Fast-path condition NOT met: falls through to rubric
- Criterion 1 (Eliminators): EB blocked (user chose container orchestration)
- Criterion 2 (Operational Model): Fargate (managed containers)
- → **AWS: Fargate (0.5 CPU, 1 GB memory)**
- Confidence: `inferred` (rubric-based override of default PaaS mapping)

### Example 4c: App Engine (Q5 = multi-cloud portability required)

- GCP: `google_app_engine_application` with one service (`default`), app_version runtime=python39, instance_class=F2
- Signals: PaaS deployment, but `compute: "eks"` in preferences (Q5 = multi-cloud); Q7b did not fire, so `compute_model` is absent
- Fast-path condition NOT met: `compute` = `"eks"`, so the Direct Mapping row does not match — falls through to rubric
- Criterion 1 (Eliminators): EB blocked (`compute: "eks"` multi-cloud override)
- Criterion 3 (User Preference): `compute = "eks"` → EKS standard node groups (multi-cloud portability override; Auto Mode excluded — AWS-specific, not portable)
- → **AWS: EKS standard node groups** (no EB fan-out; app_version resources skipped like any other non-EB path)
- Confidence: `inferred` (rubric-based override of default PaaS mapping)

### Example 5a: GKE Autopilot cluster (default)

- GCP: `google_container_cluster` with `config.autopilot_enabled: true`
- Signals: fully node-managed Kubernetes; Q5 ≠ multi-cloud; `kubernetes` absent or `"eks-auto"` (Q8 default)
- Criterion 1 (Eliminators): PASS (no node-level customization blockers)
- Criterion 3 (User Preference): `kubernetes = "eks-auto"` (or absent, GKE default) → EKS Auto Mode
- → **AWS: EKS Auto Mode** — direct equivalent of GKE Autopilot; AWS provisions/scales/patches the nodes
- Confidence: `inferred`
- Rationale: `"GKE Autopilot → EKS Auto Mode (managed-node equivalent)"`

### Example 5b: GKE Standard cluster, user wants node control

- GCP: `google_container_cluster` with `config.autopilot_enabled: false`, node pool `machine_type=n2-standard-4`
- Signals: self-managed node pools; Q8 = B (`kubernetes: "eks-standard"`)
- Criterion 3 (User Preference): `kubernetes = "eks-standard"` → EKS with managed node groups
- → **AWS: EKS with managed node groups (m7g.xlarge, Graviton default)** — preserves direct node control
- Confidence: `inferred`

### Example 5c: GKE cluster, team wants off Kubernetes

- GCP: `google_container_cluster` (Standard), stateless HTTP services
- Signals: Q8 = C (`kubernetes: "ecs-fargate"` — team chose to drop Kubernetes)
- Criterion 3 (User Preference): `kubernetes = "ecs-fargate"` → Fargate
- → **AWS: ECS Fargate** — no Kubernetes control plane or manifests to operate
- Confidence: `inferred`

### Example 5d: GKE cluster requiring node-level customization

- GCP: `google_container_cluster` running privileged DaemonSets that manage the node and a custom node OS
- Signals: `kubernetes = "eks-auto"` (or default), but workload needs node-level access Auto Mode disallows
- Criterion 1 (Eliminators): Auto Mode caveat fires → fall back to standard node groups (not Fargate)
- → **AWS: EKS with managed node groups** — Kubernetes preserved with the node control the workload requires
- Confidence: `inferred`
- Rationale: `"GKE → EKS standard node groups (Auto Mode incompatible: node-level customization required)"`

## Output Schema

Deterministic (fast-path) mappings omit `rubric_applied`; inferred (rubric-based) mappings include it.

**Deterministic (fast-path) example:**

```json
{
  "gcp_type": "google_cloud_run_service",
  "gcp_address": "example-service",
  "gcp_config": {
    "memory_mb": 512,
    "timeout_seconds": 60
  },
  "aws_service": "Fargate",
  "aws_config": {
    "cpu": "0.5",
    "memory_mb": 1024,
    "region": "us-east-1"
  },
  "graviton": {
    "compatibility": "ready",
    "target_architecture": "arm64",
    "caveats": []
  },
  "confidence": "deterministic",
  "rationale": "Direct Mapping: google_cloud_run_service → Fargate (Always)"
}
```

**Inferred (rubric-based) example:**

```json
{
  "gcp_type": "google_compute_instance",
  "gcp_address": "batch-worker",
  "gcp_config": {
    "machine_type": "e2-medium",
    "region": "us-central1"
  },
  "aws_service": "EC2",
  "aws_config": {
    "instance_type": "t4g.medium",
    "region": "us-east-1"
  },
  "graviton": {
    "compatibility": "ready",
    "target_architecture": "arm64",
    "caveats": []
  },
  "confidence": "inferred",
  "rationale": "Rubric: Compute Engine (always-on batch job) → EC2 with Auto Scaling",
  "rubric_applied": [
    "Eliminators: PASS",
    "Operational Model: EC2 (explicit compute control)",
    "User Preference: cost_sensitivity → Auto Scaling",
    "Feature Parity: Full",
    "Cluster Context: N/A",
    "Simplicity: EC2 + ASG"
  ]
}
```
