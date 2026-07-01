# Elastic Beanstalk Design Reference

**Applies to:** Google App Engine (Standard/Flexible)

## Key Distinction

- **EB is application management** (AWS manages lifecycle: provisioning, load balancing, scaling, patching) vs **ECS/Fargate as infrastructure management** (user manages task definitions, service configs, scaling policies).
- "Don't want to manage servers" does **NOT** mean serverless/Lambda. Lambda imposes a different programming model: stateless functions, cold starts, event-driven invocation, 15-min max execution, no persistent connections.
- EB eliminates server management while preserving the standard application programming model: long-running processes, persistent connections, threads, local state, WebSockets.

## When to Use

Routing signals — these apply ONLY when `google_app_engine_application` is in the inventory (any match is sufficient):

- `google_app_engine_application` detected in Terraform (strongest PaaS-to-PaaS signal)
- User answers `compute_model: "managed_platform"` in Clarify (Q7b)
- User explicitly requests "managed platform" or "Elastic Beanstalk" for their App Engine workloads

These signals do NOT apply to Cloud Run resources. Cloud Run maps to Fargate unconditionally via fast-path.

## NOT the Right Choice

- User explicitly wants serverless/Lambda (event-driven functions, stateless, cold starts) → use Lambda
- User wants fine-grained container orchestration control → use ECS/Fargate or EKS
- User requires scale-to-zero → use Lambda or Fargate with scaling policies
- GPU workloads → use EC2 or EKS
- Kubernetes orchestration required → use EKS

## Supported Platforms

| Platform   | Versions          | Base OS | Notes                                    |
| ---------- | ----------------- | ------- | ---------------------------------------- |
| Python     | 3.9, 3.10, 3.11, 3.12 | AL2023  |                                          |
| Node.js    | 18, 20, 22        | AL2023  |                                          |
| Java Corretto | 11, 17, 21     | AL2023  | .jar (standalone) vs .war (Tomcat)       |
| .NET       | 6, 8, 10          | AL2023  | Requires pre-built artifacts             |
| Go         | 1.21+             | AL2023  |                                          |
| Ruby       | 3.2, 3.3          | AL2023  |                                          |
| Docker     | Single/Multi-container | AL2023 |                                       |
| PHP        | 8.1, 8.2, 8.3    | AL2023  |                                          |

## Platform Detection Rules

Detect from app source to select EB platform automatically:

| File/Pattern                              | Platform       |
| ----------------------------------------- | -------------- |
| `requirements.txt` or `Pipfile`           | Python         |
| `package.json`                            | Node.js        |
| `pom.xml` or `build.gradle` with .jar output | Java Corretto |
| `pom.xml` or `build.gradle` with .war output | Java Tomcat   |
| `*.csproj` or `*.sln`                    | .NET           |
| `go.mod`                                  | Go             |
| `Gemfile`                                 | Ruby           |
| `Dockerfile`                              | Docker         |
| `composer.json`                           | PHP            |

## Environment Types

- **Web server** (default): Handles HTTP requests via ALB. Use for APIs, web apps, frontends.
- **Worker**: Processes background jobs from SQS queue. No public endpoint. Use for async tasks, cron-like jobs, batch processing.

## Configuration

**IaC tool:** AWS CLI (`aws elasticbeanstalk` commands). Do not use EB CLI (avoids install dependency on target machine).

**Port:** All AL2023 platforms default to port 5000.

**Deployment policies:**

| Policy                      | Use case                          |
| --------------------------- | --------------------------------- |
| AllAtOnce                   | Dev/test (fastest, brief downtime)|
| Rolling                     | Prod with some tolerance          |
| RollingWithAdditionalBatch  | Prod (maintains full capacity)    |
| Immutable                   | Prod (safe rollback)              |
| TrafficSplitting            | Canary/prod (percentage-based)    |

**Secrets:** Use `environmentsecrets` namespace to pull from Secrets Manager or SSM Parameter Store. Requires platform versions March 2025+.

**IAM:**

- Instance profile: scan source for AWS SDK usage; attach least-privilege policies for accessed services
- Service role: `aws-elasticbeanstalk-service-role` (auto-created on first environment)

**VPC:**

- Web tier: public subnets with ALB
- Worker tier: private subnets (no public access needed)

**Scaling:**

- Configure min/max instances
- Scaling triggers: CPU utilization, network out, latency, request count

## GCP App Engine to EB Mapping

| App Engine Feature              | EB Equivalent                              |
| ------------------------------- | ------------------------------------------ |
| App Engine Standard             | EB with matching platform (Python, Node, etc.) |
| App Engine Flexible             | EB Docker platform                         |
| `app.yaml` env vars            | EB environment properties                  |
| `cron.yaml`                    | EB worker + EventBridge scheduled events   |
| Task queues                    | EB worker + SQS                            |
| `instance_class` (F1/F2/F4)   | Instance type selection (t3.small/medium)  |
| Automatic scaling min/max      | EB auto-scaling min/max instances          |

## Sizing Defaults

| Environment | Type            | Instance    | ALB | Min Instances | Multi-AZ |
| ----------- | --------------- | ----------- | --- | ------------- | -------- |
| Dev         | SingleInstance  | t3.small    | No  | 1             | No       |
| Prod        | LoadBalanced    | t3.medium+  | Yes | 2             | Yes      |

## Output Schema

```json
{
  "gcp_type": "google_app_engine_application",
  "gcp_address": "example-app",
  "gcp_config": {
    "runtime": "python39",
    "instance_class": "F2"
  },
  "aws_service": "Elastic Beanstalk",
  "aws_config": {
    "platform": "Python 3.9",
    "environment_type": "LoadBalanced",
    "instance_type": "t3.small",
    "region": "us-east-1"
  },
  "confidence": "deterministic",
  "rationale": "Direct Mapping: google_app_engine_application → Elastic Beanstalk (compute_model absent or managed_platform)"
}
```
