# Amazon EKS — Service Card

## One-liner

Kubernetes, full control, portable across clouds, GPU-capable.

## Best for

Existing K8s cluster, platform-engineering team, multi-cloud portability, GPU workloads.

## Hard limits

None that eliminate it for agents (it's the GPU / multi-cloud / full-control winner).

## Six dimensions

- Identity: IRSA / bring-your-own
- Observability: CloudWatch / Prometheus (you configure)
- Guardrails: bring-your-own + Bedrock Guardrails
- Scaling: Spot + Karpenter
- Tool/Gateway: AgentCore services available as add-ons
- Protocols: anything you expose

## Tradeoffs

Highest ops burden; only worth it with existing K8s or GPU/multi-cloud needs.
Hands off to migration-to-aws for compute-layer config.
