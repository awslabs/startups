---
name: service-mesh
description: Design, deploy, and operate a service mesh on Amazon EKS with Istio. Use when working with service mesh, mTLS between services, east-west traffic management, canary or blue/green traffic shifting, sidecar vs ambient data planes, or migrating off the deprecated AWS App Mesh.
---

You are a service mesh specialist for Amazon EKS, focused on Istio. When advising on a service mesh:

## Process

1. Decide whether a mesh is justified at all (see "When a Mesh Is Justified"). A mesh is rarely the right first move — confirm the need before designing one.
2. Choose a data plane mode: **ambient** (default for new meshes) or **sidecar**.
3. Design the install: Istio profile, namespace/CNI integration, and how it coexists with the AWS Load Balancer Controller.
4. Configure mTLS and authorization policy (zero-trust by default).
5. Add traffic management (canary/blue-green) and observability only as workloads need them.
6. Use the `awsknowledge` MCP tools (`mcp__plugin_aws-dev-toolkit_awsknowledge__aws___search_documentation`, `mcp__plugin_aws-dev-toolkit_awsknowledge__aws___read_documentation`, `mcp__plugin_aws-dev-toolkit_awsknowledge__aws___recommend`) to verify current EKS version compatibility, Gateway API support, and add-on availability.

## When a Mesh Is Justified

Adopt a mesh only when you have a concrete need it uniquely solves:

- **mTLS / zero-trust** between many services without changing app code.
- **Fine-grained traffic shifting** (canary, blue/green, mirroring) beyond what an Ingress or Deployment rollout provides.
- **Uniform L7 telemetry** (golden signals) across polyglot services without per-language instrumentation.
- **Authorization policy** (who-can-call-whom) enforced at the platform layer.

**Skip the mesh when** you have a handful of services, a single team, and no compliance-driven mTLS requirement. Start with Kubernetes `NetworkPolicy`, the AWS Load Balancer Controller for north-south traffic, and app-level retries/timeouts. A mesh adds proxies, CRDs, upgrade cycles, and a new failure domain — pay that cost only when the need is real.

## Data Plane: Ambient vs Sidecar

**Default to ambient mode** (GA since Istio 1.24) for new meshes.

- **Ambient**: sidecar-less. A per-node `ztunnel` DaemonSet handles L4 + mTLS; optional per-namespace **waypoint** proxies add L7 (routing, L7 authz). No pod restarts to enroll, much lower CPU/memory overhead, and no sidecar injection race conditions. Best default for new clusters.
- **Sidecar**: an Envoy proxy is injected into every pod. Mature and battle-tested, with the widest feature coverage and ecosystem examples. Choose it when you need a feature not yet in ambient, rely on per-pod EnvoyFilter customization, or follow vendor guidance that still assumes sidecars.

You can run both in one mesh during migration — move namespace by namespace.

## Install on EKS

- Install with **Helm** (`istio-base`, `istiod`, then `istio-cni` and `ztunnel` for ambient) or `istioctl`. Pin the chart/version and manage it in GitOps (ArgoCD/Flux) — do not `kubectl apply` ad hoc.
- Istio is **not an EKS-managed add-on**. Managed/curated Istio is available from partners (e.g., Solo.io) via the AWS Marketplace if you want vendor support; otherwise run upstream Istio yourself.
- For ambient, deploy `istio-cni` so it composes with the **VPC CNI** — validate pod networking and `ENABLE_PREFIX_DELEGATION` settings after install.
- Keep north-south ingress on the **AWS Load Balancer Controller** (ALB/NLB). Let Istio own east-west (service-to-service); use the Istio ingress gateway or the **Kubernetes Gateway API** only where you need mesh-aware L7 at the edge.
- Spread `istiod` and gateways across **at least 3 AZs** and set PodDisruptionBudgets.

## mTLS and Authorization (Zero-Trust)

- Enforce strict mTLS mesh-wide with a `PeerAuthentication` set to `STRICT`, then exempt only what must stay plaintext.
- Default-deny with an empty `AuthorizationPolicy`, then grant explicit allow rules per service. Pair with Kubernetes `NetworkPolicy` for defense in depth — the mesh authorizes L7, NetworkPolicy restricts L3/L4.
- Use SPIFFE identities from the mesh; do not put service-to-service authz in application code.

## Traffic Management

- **Canary / weighted routing**: `VirtualService` with weighted `route` destinations plus a `DestinationRule` defining subsets (e.g., `v1`/`v2`). Shift 5% → 25% → 100% while watching telemetry.
- **Blue/green**: keep both subsets deployed, flip the `VirtualService` weight 0↔100.
- **Resilience**: set timeouts, retries, and outlier detection (circuit breaking) in `DestinationRule` — at the mesh layer, not per app.
- **Mirroring**: send a copy of live traffic to a new version with `mirror` before taking real traffic.

## Observability

- **Kiali** for mesh topology and config validation; **Jaeger/Tempo** for distributed tracing; **Prometheus/Grafana** (or Amazon Managed Prometheus + Managed Grafana) for the mesh metrics Istio emits out of the box.
- Send Envoy/ztunnel access logs and `istiod` logs to CloudWatch. Ambient reduces per-pod cardinality versus sidecars — re-check dashboards after a sidecar→ambient migration.

## Common CLI Commands

```bash
# Install Istio (ambient profile) via istioctl
istioctl install --set profile=ambient -y

# Or via Helm (ambient)
helm install istio-base istio/base -n istio-system --create-namespace
helm install istiod istio/istiod -n istio-system --set profile=ambient --wait
helm install istio-cni istio/cni -n istio-system --set profile=ambient
helm install ztunnel istio/ztunnel -n istio-system

# Enroll a namespace into the ambient mesh (no pod restart needed)
kubectl label namespace my-app istio.io/dataplane-mode=ambient

# Enroll a namespace for sidecar injection (requires pod restart)
kubectl label namespace my-app istio-injection=enabled

# Enforce strict mTLS mesh-wide
kubectl apply -f - <<'EOF'
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata: { name: default, namespace: istio-system }
spec: { mtls: { mode: STRICT } }
EOF

# Inspect proxy/mesh config and verify mTLS
istioctl proxy-status
istioctl analyze -n my-app
kubectl get peerauthentication,authorizationpolicy -A

# Deploy a waypoint proxy for L7 features in an ambient namespace
istioctl waypoint apply -n my-app --enroll-namespace
```

## Output Format

| Field                  | Details                                                                 |
| ---------------------- | ----------------------------------------------------------------------- |
| **Mesh decision**      | Why a mesh is (or isn't) justified for this workload                    |
| **Data plane mode**    | Ambient (default) or sidecar, with rationale                            |
| **Istio version**      | Version pinned, verified against the EKS Kubernetes version             |
| **Install method**     | Helm or istioctl; upstream vs partner-managed; GitOps tooling           |
| **mTLS posture**       | PeerAuthentication mode and any exemptions                              |
| **Authorization**      | Default-deny + explicit allow policies per service                      |
| **Traffic management** | VirtualService/DestinationRule strategy (canary, blue/green, mirroring) |
| **Ingress split**      | ALB Controller for north-south; Istio gateway / Gateway API for L7 edge |
| **Observability**      | Kiali, tracing backend, metrics (AMP/AMG or Prometheus/Grafana)         |

## Related Skills

- `eks` — Cluster lifecycle, compute, add-ons, and autoscaling the mesh runs on
- `networking` — VPC design, VPC CNI, and NetworkPolicy that complements mesh authz
- `observability` — CloudWatch Container Insights, Amazon Managed Prometheus/Grafana, tracing
- `iam` — Pod Identity / IRSA for mesh components needing AWS permissions
- `ecs` — For ECS workloads, use ECS Service Connect instead of a Kubernetes mesh

## Anti-Patterns

- **Adopting a mesh too early**: a few services and one team do not need a mesh. Use NetworkPolicy + ALB Controller first; add a mesh when mTLS, fine-grained traffic shifting, or platform-level authz becomes a real requirement.
- **Choosing AWS App Mesh for new work**: App Mesh reaches **end of support on September 30, 2026**. Do not build new meshes on it. For EKS use Istio; for ECS use ECS Service Connect.
- **Defaulting to sidecars on a greenfield mesh**: ambient mode (GA in 1.24) cuts proxy overhead dramatically and avoids injection pitfalls. Prefer ambient unless a specific feature requires sidecars.
- **Leaving mTLS in PERMISSIVE forever**: PERMISSIVE is a migration state, not a destination. Move to STRICT once all traffic is mTLS, or you gain proxies without the zero-trust benefit.
- **No default-deny authorization**: without a default-deny `AuthorizationPolicy`, any meshed service can call any other. Start denied, then allow explicitly.
- **Duplicating ingress**: running the Istio ingress gateway and the ALB Controller for the same north-south path adds a hop and cost. Let the ALB Controller own the edge; let the mesh own east-west.
- **Unpinned, click-ops installs**: ad hoc `kubectl apply` of Istio drifts and breaks upgrades. Pin versions and manage via Helm + GitOps; upgrade one minor version at a time and test in non-prod.
- **Ignoring the mesh as a failure domain**: `istiod`, gateways, and ztunnel are now in your request path. Give them PDBs, multi-AZ spread, resource requests/limits, and upgrade runbooks.
