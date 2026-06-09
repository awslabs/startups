# ECS
## Launch Type Selection

**Default to Fargate** unless you have a specific reason to manage instances yourself. Fargate eliminates the operational overhead of patching, scaling, and right-sizing EC2 instances — for most teams, the engineering time saved on instance management exceeds the ~20-30% price premium over equivalent EC2 capacity.

- **Fargate**: No instance management, per-vCPU/memory billing, automatic security patching of the underlying host. Use Fargate Spot for fault-tolerant batch/worker tasks (up to 70% savings).
- **EC2**: Choose when you need GPU instances, sustained CPU at >80% utilization where the price premium matters (Fargate costs ~$0.04/vCPU-hour vs ~$0.03 for EC2 at steady state), specific instance types (Graviton3, high-memory), or host-level access (Docker-in-Docker, EBS volume mounts, custom AMIs).

## Task Definitions

- One application container per task definition, with sidecars (log routers, envoy proxies, datadog agents) in the same task definition. Reason: ECS scales, deploys, and health-checks at the task level. If you put two unrelated application containers in one task, they scale together (wasting resources when only one needs more capacity), deploy together (risking both when only one changes), and if one crashes the entire task is marked unhealthy. Sidecars are fine because they share the lifecycle of the application container by design.
- Always set `cpu` and `memory` at the task level for Fargate. For EC2 launch type, set container-level limits.
- Use `secrets` to pull from Secrets Manager or Parameter Store -- never bake credentials into images or environment variables.
- Use `dependsOn` with `condition: HEALTHY` for sidecar ordering.
- Set `essential: true` only on the primary container. Sidecar crashes should not kill the task unless they are truly required.
- Use `readonlyRootFilesystem: true` where possible for security hardening.

## Service Configuration & Networking

- **awsvpc** network mode is mandatory for Fargate and recommended for EC2. Each task gets its own ENI.
- Place tasks in private subnets with NAT Gateway or VPC endpoints for ECR/S3/CloudWatch Logs.
- Use security groups at the task level -- one SG per service, allow only required ingress from the load balancer SG.
- **Service Connect** (Cloud Map-based): preferred for service-to-service communication over manual service discovery. Provides built-in retries, timeouts, and observability.

## Load Balancer Integration

- **ALB**: Default for HTTP/HTTPS services. Use path-based or host-based routing to multiplex services on one ALB.
- **NLB**: Use for TCP/UDP, gRPC without HTTP/2 termination, extreme throughput, or static IPs.
- Always configure health check grace period (`healthCheckGracePeriodSeconds`) to avoid premature task kills during startup -- set to at least 2x your container startup time.
- Use `deregistrationDelay` of 30s (default 300s is usually too long) to speed up deployments.

## Auto-Scaling

- **Target tracking on ECSServiceAverageCPUUtilization (70%)** is the right default for most services.
- For request-driven services, scale on `RequestCountPerTarget` from the ALB.
- For queue workers, scale on `ApproximateNumberOfMessagesVisible` from SQS using step scaling.
- Set `minCapacity` >= 2 for production services (multi-AZ resilience).
- Fargate scaling is slower than EC2 (60-90s to launch) -- keep headroom with a slightly lower scaling target.

## Deployment Strategies

- **Rolling update** (default): Good for most workloads. Set `minimumHealthyPercent: 100` and `maximumPercent: 200` to deploy with zero downtime.
- **Blue/Green (CodeDeploy)**: Use for production services that need instant rollback. Requires ALB. Configure `terminateAfterMinutes` to keep the old task set alive during validation.
- **Canary**: Use CodeDeploy with `CodeDeployDefault.ECSCanary10Percent5Minutes` for high-risk changes.
- Circuit breaker: Always enable `deploymentCircuitBreaker` with `rollback: true` to auto-rollback failed deployments.

## Anti-Patterns

- **Using :latest tag in production**: Always use immutable image tags (git SHA or semantic version). `:latest` makes rollbacks impossible and deployments non-deterministic.
- **One giant cluster per account**: Use separate clusters per environment (dev/staging/prod) or per team. Cluster-level IAM and capacity provider strategies are easier to manage.
- **Oversized task definitions**: Right-size CPU and memory. A 4 vCPU / 8 GB task running at 10% utilization is burning money. Start small, scale up based on CloudWatch Container Insights metrics.
- **Skipping health checks**: Always define container health checks in the task definition AND target group health checks. Without both, ECS cannot detect unhealthy tasks.
- **Ignoring ECS Exec**: Enable `ExecuteCommandConfiguration` on the cluster and `enableExecuteCommand` on the service. It replaces SSH access to containers and is essential for debugging.
- **No deployment circuit breaker**: Without it, a bad deployment will keep cycling failing tasks indefinitely, consuming capacity and generating noise.
- **Putting secrets in environment variables**: Use the `secrets` field with Secrets Manager or SSM Parameter Store references. Environment variables are visible in the console and API.
- **Running as root**: Set `user` in the task definition to a non-root user. Combine with `readonlyRootFilesystem` for defense in depth.
