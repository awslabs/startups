# aws-dev-toolkit

A Claude Code plugin for building, migrating, and performing architecture reviews on AWS. Ships 35 skills, 11 sub-agents, and 3 MCP servers.

## Installation

```bash
# Add the marketplace
/plugin marketplace add awslabs/startups

# Install the plugin
/plugin install aws-dev-toolkit@startups-for-aws
```

Or load locally during development:

```bash
claude --plugin-dir ./solution-architecture/plugins/aws-dev-toolkit
```

## Prerequisites

- [Claude Code](https://code.claude.com)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (for MCP servers via `uvx`)
- AWS CLI configured with appropriate credentials
- (Optional) `checkov`, `cfn-nag`, `tfsec` for security scanning

## Usage

Most skills activate automatically based on context. Just ask naturally:

```
"Review this architecture for Well-Architected best practices"  → aws-architect
"Why is my CloudFormation stack failing?"                       → aws-debug
"Compare ECS vs EKS for my workload"                            → aws-compare
"Help me optimize my AWS bill"                                  → cost-optimizer agent
```

Some skills are invoked explicitly via slash commands:

```
/aws-dev-toolkit:iac-scaffold cdk "Serverless API with Lambda and DynamoDB"
/aws-dev-toolkit:aws-health-check us-east-1
/aws-dev-toolkit:aws-diagram from-iac
/aws-dev-toolkit:strands-agent "Document processing pipeline"
```

## Skills (35)

| Skill                                | Trigger      | Description                                                                          |
| ------------------------------------ | ------------ | ------------------------------------------------------------------------------------ |
| **Workflows & Planning**             |              |                                                                                      |
| `aws-plan`                           | Auto         | End-to-end architecture planning — discovery, design, security review, cost estimate |
| `aws-architect`                      | Auto         | Design and review AWS architectures against Well-Architected Framework               |
| `well-architected`                   | Auto         | Formal Well-Architected Framework reviews with pillar-by-pillar assessment           |
| `customer-ideation`                  | Auto         | Guided ideation from concept to AWS architecture with service selection              |
| `aws-compare`                        | Auto         | Compare 2-3 architecture options side-by-side                                        |
| `aws-diagram`                        | Auto / Slash | Generate Mermaid/ASCII architecture diagrams from descriptions or IaC                |
| `aws-health-check`                   | Slash        | Quick account health scan — security, cost waste, reliability gaps                   |
| **Scaffolding**                      |              |                                                                                      |
| `iac-scaffold`                       | Slash        | Scaffold CDK, Terraform, SAM, or CloudFormation projects                             |
| `strands-agent`                      | Slash        | Scaffold Strands Agents SDK projects on Bedrock AgentCore (TS/Python)                |
| **Debugging & Review**               |              |                                                                                      |
| `aws-debug`                          | Auto         | Debug deployment failures, Lambda errors, permission issues                          |
| `security-review`                    | Auto         | Audit IaC and AWS configs for security issues                                        |
| `cost-check`                         | Auto         | Analyze and optimize AWS costs                                                       |
| `bedrock`                            | Auto         | Bedrock model selection, agents, knowledge bases, guardrails, cost modeling          |
| `challenger`                         | Auto         | Adversarial reviewer that stress-tests architecture recommendations                  |
| **AWS Services**                     |              |                                                                                      |
| `lambda`                             | Auto         | Lambda functions — runtimes, cold starts, concurrency                                |
| `ec2`                                | Auto         | EC2 workloads — instance selection, AMIs, ASGs                                       |
| `ecs`                                | Auto         | ECS — task definitions, services, Fargate                                            |
| `eks`                                | Auto         | EKS — Kubernetes on AWS, Karpenter, IRSA                                             |
| `s3`                                 | Auto         | S3 — storage optimization, access patterns                                           |
| `dynamodb`                           | Auto         | DynamoDB — table design, access patterns, single-table design, GSIs                  |
| `api-gateway`                        | Auto         | API Gateway — REST vs HTTP APIs, authorizers, throttling                             |
| `cloudfront`                         | Auto         | CloudFront — caching, origins, Lambda@Edge, Functions                                |
| `iam`                                | Auto         | IAM — policies, roles, permission boundaries, least-privilege                        |
| `networking`                         | Auto         | VPC, subnets, security groups, Transit Gateway, VPC endpoints                        |
| `messaging`                          | Auto         | SQS, SNS, EventBridge — queues, fan-out, event routing                               |
| `observability`                      | Auto         | CloudWatch, X-Ray, OpenTelemetry — dashboards, alarms, tracing                       |
| `step-functions`                     | Auto         | Step Functions — state machines, error handling, service integrations                |
| `rds-aurora`                         | Auto         | RDS and Aurora — engine selection, HA, operations                                    |
| `iot`                                | Auto         | AWS IoT — device connectivity, Greengrass, fleet management                          |
| `mlops`                              | Auto         | MLOps — SageMaker, training, inference, pipelines, monitoring                        |
| `agentcore`                          | Auto         | Bedrock AgentCore — platform design, deployment, production ops                      |
| **Migration**                        |              |                                                                                      |
| `migration-gcp-to-aws`               | Auto         | GCP to AWS migration — service mapping, gotchas, assessment                          |
| `migration-azure-to-aws`             | Auto         | Azure to AWS migration — service mapping, gotchas, assessment                        |
| `migration-apprunner-to-ecs-express` | Auto         | App Runner to ECS Express Mode — guided migration with guardrails                    |

## Sub-Agents (11)

| Agent                       | Description                                                             |
| --------------------------- | ----------------------------------------------------------------------- |
| `aws-explorer`              | Read-only AWS environment exploration and context gathering             |
| `well-architected-reviewer` | Deep Well-Architected Framework reviews with evidence-based assessment  |
| `iac-reviewer`              | Reviews IaC changes for correctness, security, and best practices       |
| `migration-advisor`         | Cloud migration expert — 6Rs framework, wave planning, cutover strategy |
| `bedrock-sme`               | Bedrock subject matter expert emphasizing cost-efficient usage          |
| `agentcore-sme`             | AgentCore expert for PoC-to-production agent development                |
| `container-sme`             | Container expert for ECS, EKS, and Fargate architecture decisions       |
| `serverless-sme`            | Serverless expert for Lambda, API Gateway, Step Functions               |
| `networking-sme`            | AWS networking — VPC design, hybrid connectivity, DNS, CDN              |
| `observability-sme`         | CloudWatch, X-Ray, and OpenTelemetry observability expert               |
| `cost-optimizer`            | Deep cost optimization — rightsizing, Savings Plans, waste elimination  |

## MCP Servers (3)

| Server         | Type  | Source                                                                                            |
| -------------- | ----- | ------------------------------------------------------------------------------------------------- |
| `awsiac`       | stdio | `awslabs.aws-iac-mcp-server` — CloudFormation/CDK/Terraform validation and security scanning      |
| `awsknowledge` | http  | `knowledge-mcp.global.api.aws` — AWS documentation search, recommendations, regional availability |
| `awspricing`   | stdio | `awslabs.aws-pricing-mcp-server` — Service pricing data, cost reports, IaC cost analysis          |

## Optional MCP Servers

Some skills benefit from additional MCP servers that are not bundled with the plugin. These must be configured separately by the user.

| Server    | Required by                          | Setup                                                                                                                                                                                                         |
| --------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ecs-mcp` | `migration-apprunner-to-ecs-express` | `mcp-proxy-for-aws` over stdio pointing at the regional ECS MCP endpoint (`ecs-mcp.<region>.api.aws/mcp`). Requires `uv`/`uvx` and AWS credentials. See the skill's SKILL.md for the full `mcp.json` snippet. |

## License

Apache-2.0
