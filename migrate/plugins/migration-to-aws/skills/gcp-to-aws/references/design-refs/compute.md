# Compute Services Design Rubric

**Applies to:** Cloud Run (v1/v2), Cloud Functions (Gen 1/Gen 2), Compute Engine, GKE, App Engine

**Table lookup first:** Check `fast-path.md` **Direct Mappings** for this Terraform type.

- `google_cloud_run_service`, `google_cloud_run_v2_service`, `google_cloudfunctions_function`, and `google_cloudfunctions2_function` are currently in Direct Mappings and usually resolve with `confidence: "deterministic"` when row conditions are met.
- `google_app_engine_application` is now in Direct Mappings (→ Elastic Beanstalk, confidence: `deterministic`).
- `google_compute_instance` and `google_container_cluster` are not direct-mapped in `fast-path.md`; use the rubric below (typically `confidence: "inferred"`).
- If a resource is not eligible for Direct Mappings (or row conditions are not met), use the rubric below.

## Eliminators (Hard Blockers)

| GCP Service     | AWS        | Blocker                                                                                                                                                        |
| --------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cloud Run       | Lambda     | Execution time >15 min → use Fargate                                                                                                                           |
| Cloud Run       | Fargate    | GPU workload or >16 vCPU or >120 GB memory → use EC2                                                                                                           |
| Cloud Functions | Lambda     | Python version not supported (e.g., Python 2.7) → use custom runtime on Fargate                                                                                |
| GKE             | EKS        | Custom CRI incompatible → manual workaround or ECS                                                                                                             |
| Any             | App Runner | **Closed to new customers (April 30 2026).** Do not target App Runner for new migrations. Use Fargate (default), Lambda (event-driven), or EKS (K8s required). |
| App Engine      | Elastic Beanstalk | `compute_model: "container_orchestration"` or `"serverless"` in preferences → do not use EB, fall through to Fargate or Lambda |

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

- **Kubernetes orchestration explicitly required** (`kubernetes = "eks-managed"` or `"eks-or-ecs"` in `preferences.json`) → EKS
- **Default / no explicit K8s preference** (`kubernetes = "ecs-fargate"` or absent):
  - If `gcp-resource-inventory.json` contains `google_container_cluster` → EKS (IaC signal shows K8s workload)
  - Otherwise → **Fargate** (no K8s signal; lower-ops default)

### App Engine

- **Default** → Elastic Beanstalk (PaaS-to-PaaS, preserves managed platform model)
- **User prefers container control** (`compute_model: "container_orchestration"`) → Fargate
- **Event-driven / scale-to-zero required** → Lambda

After selecting Elastic Beanstalk, load `elastic-beanstalk.md` to populate `aws_config` (platform, deployment policy, IAM, VPC, sizing).

## 6-Criteria Rubric

Apply in order; first match wins:

1. **Eliminators**: Does GCP config violate AWS constraints? If yes: switch to alternative
2. **Operational Model**: Managed (Lambda, Fargate) vs Self-Hosted (EC2, EKS)?
   - Prefer managed unless: Always-on + high baseline cost → EC2
   - For App Engine sources: Elastic Beanstalk (PaaS-to-PaaS) when `compute_model` is absent or `"managed_platform"`
3. **User Preference**: From `preferences.json`: `design_constraints.kubernetes`, `design_constraints.cost_sensitivity`?
   - If `kubernetes = "eks-managed"` → EKS (preserves K8s investment)
   - If `kubernetes = "eks-or-ecs"` → EKS with managed node groups (user is competent with K8s)
   - If `kubernetes = "ecs-fargate"` → Fargate (simpler managed containers)
   - If `kubernetes` is **absent** → Fargate (treat same as `"ecs-fargate"` — do not default to EKS)
   - If `cost_sensitivity` present and high → prefer Fargate (lower operational cost)
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
- → **AWS: EC2 t3.medium + Auto Scaling Group (min=0 in dev)**
- Confidence: `inferred`

### Example 4a: App Engine (standard Python web app, default preference)

- GCP: `google_app_engine_application` (runtime=python39, instance_class=F2)
- Signals: PaaS deployment, `compute_model` absent or `"managed_platform"`
- Fast-path condition met: `compute_model` not set to `"container_orchestration"` or `"serverless"`
- → **AWS: Elastic Beanstalk (Python 3.9, LoadBalanced, t3.small)**
- Confidence: `deterministic` (App Engine → EB direct mapping, condition met)

### Example 4b: App Engine (user chose container orchestration)

- GCP: `google_app_engine_application` (runtime=python39, instance_class=F2)
- Signals: PaaS deployment, but `compute_model: "container_orchestration"` in preferences
- Fast-path condition NOT met: falls through to rubric
- Criterion 1 (Eliminators): EB blocked (user chose container orchestration)
- Criterion 2 (Operational Model): Fargate (managed containers)
- → **AWS: Fargate (0.5 CPU, 1 GB memory)**
- Confidence: `inferred` (rubric-based override of default PaaS mapping)

## Output Schema

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
    "instance_type": "t3.medium",
    "region": "us-east-1"
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
