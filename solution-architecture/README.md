# Solution Architecture

Plugins and tools from the AWS Startups Solution Architecture team for building, migrating, and reviewing architectures on AWS.

## Plugins

- **[`aws-dev-toolkit`](plugins/aws-dev-toolkit/)** — A toolkit for building, migrating, and performing architecture reviews on AWS. Ships **35 skills**, **11 sub-agents**, and **3 MCP servers**. Most skills activate automatically from context: review an architecture against the Well-Architected Framework, debug a failing CloudFormation stack, compare ECS vs EKS, scaffold CDK/Terraform/SAM/CloudFormation projects, or optimize an AWS bill. Deep service skills cover Lambda, EC2, ECS, EKS, S3, DynamoDB, API Gateway, CloudFront, IAM, networking, messaging, observability, Step Functions, RDS/Aurora, IoT, MLOps, Bedrock, and AgentCore, plus GCP/Azure and App Runner migration paths.

See the [plugin README](plugins/aws-dev-toolkit/README.md) for the full skill, agent, and MCP server catalog.

## MCP servers

`aws-dev-toolkit` bundles three MCP servers, declared in [`plugins/aws-dev-toolkit/.mcp.json`](plugins/aws-dev-toolkit/.mcp.json) and provisioned automatically when the plugin is installed:

- **AWS IaC** (`awsiac`, stdio via `uvx awslabs.aws-iac-mcp-server`) — CloudFormation/CDK/Terraform validation and security scanning.
- **AWS Knowledge** (`awsknowledge`, HTTP) — AWS documentation search, recommendations, and regional availability.
- **AWS Pricing** (`awspricing`, stdio via `uvx awslabs.aws-pricing-mcp-server`) — service pricing data, cost reports, and IaC cost analysis.

The stdio servers require [`uv`/`uvx`](https://docs.astral.sh/uv/) on the user's machine.

## Install

### Claude Code

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

## License

Apache-2.0
