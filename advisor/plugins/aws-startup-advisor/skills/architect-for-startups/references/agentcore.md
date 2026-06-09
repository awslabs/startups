# AgentCore

## Runtime
### Development vs Production Deployment

**Development and testing**: Use the AgentCore CLI or Starter Toolkit for fast iteration — scaffolding, local dev, quick deploys, and testing.

**Production**: Define all AgentCore resources in IaC (CDK, Terraform, CloudFormation, or SAM). CLI-created resources are useful for prototyping but should not be the source of truth for production infrastructure. The Starter Toolkit's CDK templates are a solid starting point for production IaC.

### Deployment Options
- **AgentCore CLI** (dev/test): Fastest path — `agentcore init` → `agentcore deploy` in minutes
- **CDK / Terraform / SAM** (production): Define resources in IaC, deploy via CI/CD pipeline
- **Container image** (manual): Docker image pushed to ECR, deployed to Runtime — full control over build

## AgentCore CLI

The [AgentCore CLI](https://github.com/aws/agentcore-cli) is the preferred tool for scaffolding, local development, and rapid iteration on agents. It abstracts away container builds, ECR pushes, and runtime configuration into simple commands. Use it for dev/test workflows — for production, define the same resources in IaC.

### Runtime Configuration

| Setting          | Recommendation                                | Notes                                                       |
|------------------|-----------------------------------------------|-------------------------------------------------------------|
| CPU/Memory       | Start with 1 vCPU / 2 GiB                     | Scale based on model inference needs and tool call overhead |
| Session TTL      | 600s for real-time, up to 28,800s for async   | Idle sessions consume resources                             |
| VPC connectivity | Enable for agents accessing private resources | Uses ENIs in your VPC                                       |
| Endpoint type    | Use agent endpoints for routing               | Supports alias-based traffic splitting                      |

### Production Deployment Pattern
1. Define all AgentCore resources in IaC (CDK, Terraform, or CloudFormation) — Runtime, Gateway, Memory, Identity, Policy
2. Build agent container with AgentCore SDK decorators (CI/CD pipeline)
3. Push to ECR via pipeline (not manual `docker push`)
4. Deploy via `cdk deploy` / `terraform apply` / CloudFormation changeset
5. Create aliases for version management in IaC (never use TSTALIASID in production)
6. Configure resource-based policies for cross-account access if needed
7. Use the AgentCore CLI's `agentcore invoke` for smoke testing deployed agents

## Policy

### Common Policy Patterns

| Pattern            | Cedar Example                                                                  | Use Case                     |
|--------------------|--------------------------------------------------------------------------------|------------------------------|
| Amount limits      | `forbid when { resource.refundAmount > 1000 }`                                 | Financial guardrails         |
| User-scoped access | `permit when { principal.department == "engineering" }`                        | Role-based tool access       |
| Tool restriction   | `forbid action == Action::"invoke" when { resource.toolName == "deleteUser" }` | Prevent dangerous operations |
| Time-based         | `permit when { context.hour >= 9 && context.hour <= 17 }`                      | Business-hours-only actions  |

## Multi-Agent Architectures

### Bedrock Multi-Agent Collaboration (Managed)
- Supervisor agent orchestrates collaborator agents
- Built-in task delegation and response aggregation
- Each agent has its own tools, knowledge bases, guardrails
- Best for: teams wanting managed orchestration with minimal custom code

### A2A Protocol (Agent-to-Agent)
- Cross-framework interoperability (Strands + LangGraph + custom agents can communicate)
- Agents advertise capabilities via Agent Cards
- Task-based request lifecycle with artifacts
- OAuth 2.0 and IAM authentication for secure inter-agent communication
- Best for: heterogeneous agent ecosystems, cross-team agent integration

### Agents-as-Tools Pattern
- Specialized agents registered as tools of a supervisor agent
- All agents run within the same AgentCore Runtime
- Supervisor selects and delegates dynamically
- Best for: monolithic deployments where all agents are owned by one team

### Architecture Decision

| Factor                | Multi-Agent Collaboration | A2A Protocol              | Agents-as-Tools              |
|-----------------------|---------------------------|---------------------------|------------------------------|
| Framework flexibility | Bedrock Agents only       | Any framework             | Any framework (same runtime) |
| Cross-account         | No                        | Yes                       | No                           |
| Managed orchestration | Yes                       | No (custom)               | Partial                      |
| Setup complexity      | Low                       | Medium-High               | Low                          |
| Best for              | All-in on Bedrock Agents  | Cross-team, heterogeneous | Single-team, single runtime  |

## Anti-Patterns

- **Using TSTALIASID in production.** Create proper aliases with version pinning. Test aliases have no SLA and no rollback capability.
- **Skipping observability until "later".** Instrument from day one. Debugging an unobservable agent in production is flying blind.
- **God agent that does everything.** If you need "and" in the agent's job description, you need two agents. Decompose into focused, composable agents.
- **Embedding credentials in agent instructions or environment variables.** Use AgentCore Identity for OAuth/API keys, IAM roles for AWS resources.
- **Not setting session TTLs.** Idle sessions consume compute resources. Set appropriate TTLs based on actual usage patterns.
- **Skipping Policy for tool access.** Without Policy, any agent can call any tool with any parameters. In production, that is a compliance and security gap.
- **Over-engineering the PoC.** Ship something that works with Runtime + Observability first. Add Memory, Gateway, Policy as needs emerge.
- **Ignoring token costs during development.** Track token usage per agent/session from the start. Costs compound fast with multi-step reasoning loops.
- **Manual prompt management.** Treat system prompts like code — version control, review, test. Prompt drift is a production incident waiting to happen.
- **Not evaluating before production.** Run evals (built-in or DeepEval) in CI/CD. "It looks right" is not a quality gate.
- **CLI-deployed resources as production infrastructure.** The AgentCore CLI is excellent for dev/test, but production resources should be defined in IaC (CDK, Terraform, CloudFormation). CLI-created resources are not version-controlled, not reproducible, and not auditable.

## Output Format

When recommending an AgentCore architecture, include:

| Component     | Choice                                              | Rationale                             |
|---------------|-----------------------------------------------------|---------------------------------------|
| Runtime       | Container on ECR, 1 vCPU / 2 GiB                    | Standard agent workload               |
| Framework     | Strands Agents                                      | Python-native, AWS-integrated         |
| Model         | Claude Sonnet via Bedrock                           | Capable reasoning, tool calling       |
| Memory        | Short-term + long-term (episodic)                   | Customer support needs continuity     |
| Gateway       | 3 Lambda targets (orders, refunds, FAQ KB)          | Existing APIs wrapped as MCP tools    |
| Identity      | OAuth2 for Salesforce, IAM for DynamoDB             | Third-party + AWS resource access     |
| Policy        | Cedar: refund amount limits, role-based tool access | Financial compliance                  |
| Observability | AgentCore native + Langfuse                         | Infra health + LLM behavior analytics |
| Evaluations   | 5 built-in evaluators + custom tool-use eval        | CI/CD quality gate                    |
