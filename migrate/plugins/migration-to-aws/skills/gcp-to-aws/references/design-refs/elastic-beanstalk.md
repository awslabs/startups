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

Detect the **platform name** (below), then resolve the exact platform version at generate time. **Do not hardcode language version numbers** — the EB platform lineup changes frequently (versions are added and retired). Look up the current version against the [EB supported platforms documentation](https://docs.aws.amazon.com/elasticbeanstalk/latest/platforms/platforms-supported.html) or `aws elasticbeanstalk list-available-solution-stacks`, and pick the newest platform version that supports the app's language version.

| Platform           | Base OS | Notes                                                                       |
| ------------------ | ------- | --------------------------------------------------------------------------- |
| Python             | AL2023  |                                                                             |
| Node.js            | AL2023  |                                                                             |
| Java SE (Corretto) | AL2023  | Standalone `.jar` applications                                              |
| Tomcat             | AL2023  | **Separate platform** from Java SE; for `.war` web apps (Corretto + Tomcat) |
| .NET Core on Linux | AL2023  | Requires pre-built artifacts                                                |
| Go                 | AL2023  |                                                                             |
| Ruby               | AL2023  |                                                                             |
| PHP                | AL2023  |                                                                             |
| Docker             | AL2023  | Single container, or ECS-managed multi-container                            |

All current platforms run on Amazon Linux 2023 (AL2 branches are being retired).

## Platform Detection Rules

Detect from app source to select EB platform automatically:

| File/Pattern                                 | Platform           |
| -------------------------------------------- | ------------------ |
| `requirements.txt` or `Pipfile`              | Python             |
| `package.json`                               | Node.js            |
| `pom.xml` or `build.gradle` with .jar output | Java SE (Corretto) |
| `pom.xml` or `build.gradle` with .war output | Tomcat             |
| `*.csproj` or `*.sln`                        | .NET Core on Linux |
| `go.mod`                                     | Go                 |
| `Gemfile`                                    | Ruby               |
| `Dockerfile`                                 | Docker             |
| `composer.json`                              | PHP                |

## Environment Types

- **Web server** (default): Handles HTTP requests via ALB. Use for APIs, web apps, frontends.
- **Worker**: Processes background jobs from SQS queue. No public endpoint. Use for async tasks, cron-like jobs, batch processing.

## Configuration

**IaC tool:** AWS CLI (`aws elasticbeanstalk` commands). Do not use EB CLI (avoids install dependency on target machine).

**Port:** On AL2023 platforms the reverse proxy (nginx) forwards to the application on port **5000** by default, and EB sets the `PORT` environment variable to that value. However, most application frameworks bind to their own default port unless told otherwise (e.g. Node/Express often 3000, Python/gunicorn 8000, .NET/Kestrel 5000/8080). **The app must listen on the port EB advertises**, or the first deploy fails its health checks. Two safe options:

- **Have the app read `PORT`** and bind to it (e.g. `process.env.PORT`, `os.environ["PORT"]`) — recommended, and how App Engine apps already behave.
- **Set the `PORT` environment property** (namespace `aws:elasticbeanstalk:application:environment`) to whatever fixed port the app listens on.

Migrated App Engine apps already read `PORT` (App Engine sets it too), so the first option usually works with no code change.

**Deployment policies:**

| Policy                     | Use case                           |
| -------------------------- | ---------------------------------- |
| AllAtOnce                  | Dev/test (fastest, brief downtime) |
| Rolling                    | Prod with some tolerance           |
| RollingWithAdditionalBatch | Prod (maintains full capacity)     |
| Immutable                  | Prod (safe rollback)               |
| TrafficSplitting           | Canary/prod (percentage-based)     |

**Secrets:** Use the `aws:elasticbeanstalk:application:environmentsecrets` namespace to fetch values from Secrets Manager or SSM Parameter Store into environment variables at instance bootstrap. Supported on platform versions released **on or after March 26, 2025**. (JSON-key extraction from a Secrets Manager secret — appending `:keyName` to the ARN — requires platform versions on or after January 13, 2026.) Values are pulled at bootstrap only; rotate via `UpdateEnvironment` or `RestartAppServer`.

**IAM:**

- Instance profile: scan source for AWS SDK usage; attach least-privilege policies for accessed services
- Service role: `aws-elasticbeanstalk-service-role` (auto-created on first environment)

**VPC:**

- Web tier: ALB in public subnets, EC2 instances in private subnets (instances reach the internet via NAT for outbound; only the ALB is public-facing)
- Worker tier: instances in private subnets (no public access needed)

**Scaling:**

- Configure min/max instances
- Scaling triggers: CPU utilization, network out, latency, request count

## GCP App Engine to EB Mapping

| App Engine Feature          | EB Equivalent                                       |
| --------------------------- | --------------------------------------------------- |
| App Engine Standard         | EB with matching platform (Python, Node, etc.)      |
| App Engine Flexible         | EB Docker platform                                  |
| `app.yaml` env vars         | EB environment properties                           |
| `cron.yaml`                 | EB worker + EventBridge scheduled events            |
| Task queues                 | EB worker + SQS                                     |
| `instance_class` (F1/F2/F4) | Instance type selection (see Sizing Defaults below) |
| Automatic scaling min/max   | EB auto-scaling min/max instances                   |

### Where the config comes from (Terraform)

In Terraform, `google_app_engine_application` is only the **container** for an app — it carries the project/location, not the workload config. The `runtime`, `instance_class`, `env`, and scaling settings live on the **`google_app_engine_standard_app_version`** / **`google_app_engine_flexible_app_version`** resources (one per App Engine _service_/version).

When mapping, treat the app_version resources as **config sources for the EB mapping**, not skipped resources:

- **One EB environment per App Engine service.** A multi-service App Engine app (multiple `service` values across app_version resources) maps to **multiple EB environments** under one EB application — do **not** collapse it to a single mapping.
- Read `runtime` → EB platform (via Platform Detection Rules above).
- Read `instance_class` → EB instance type (see Sizing Defaults).
- Read `automatic_scaling` / `manual_scaling` → EB min/max instances.
- Read `env_variables` → EB environment properties.

If **only** `google_app_engine_application` is present (no app_version resources — e.g. billing-only or partial Terraform), map a single EB environment and detect the platform/runtime from the app source instead, noting the assumption in `warnings`.

## Sizing Defaults

| Environment | Type           | Instance   | ALB | Min Instances | Multi-AZ |
| ----------- | -------------- | ---------- | --- | ------------- | -------- |
| Dev         | SingleInstance | t3.small   | No  | 1             | No       |
| Prod        | LoadBalanced   | t3.medium+ | Yes | 2             | Yes      |

## Output Schema

One mapping **per App Engine service** (per app_version resource). `runtime` and `instance_class` are read from the `*_app_version` resource, not from the parent `google_app_engine_application`. `instance_type` follows the Sizing Defaults table (LoadBalanced → t3.medium+; SingleInstance → t3.small).

```json
{
  "gcp_type": "google_app_engine_standard_app_version",
  "gcp_address": "default/v1",
  "gcp_config": {
    "service": "default",
    "runtime": "python39",
    "instance_class": "F2"
  },
  "aws_service": "Elastic Beanstalk",
  "aws_config": {
    "eb_application": "example-app",
    "eb_environment": "default",
    "platform": "Python 3.9 running on 64bit Amazon Linux 2023",
    "environment_type": "LoadBalanced",
    "instance_type": "t3.medium",
    "region": "us-east-1"
  },
  "confidence": "deterministic",
  "rationale": "Direct Mapping: App Engine service (google_app_engine_standard_app_version) → Elastic Beanstalk environment (compute_model absent or managed_platform)"
}
```
