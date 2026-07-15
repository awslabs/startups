# Migration to AWS

AI agent skills for migrating workloads to AWS, built for [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview), [Codex](https://openai.com/codex), and [Cursor](https://www.cursor.com/).

## What This Does

Point this plugin at your Terraform files, application code, or billing data. It runs a structured 6-phase assessment — discovering what you have, asking the right questions, designing the AWS architecture, estimating costs with real pricing data, and generating runnable migration artifacts.

**Supported migration sources:**

- **GCP → AWS** — Cloud Run, Cloud SQL, GKE, Cloud Functions, Pub/Sub, Cloud Storage, VPC, and AI/agentic workloads
- **Heroku → AWS** — Dynos (→ Elastic Beanstalk by default; Fargate or EKS overrides), Postgres, Redis, Kafka, Private Spaces, Pipelines, and 13+ common add-ons

**For infrastructure migrations:**

- **Maps your GCP resources to AWS equivalents** — Cloud Run → Fargate, Cloud SQL → RDS or Aurora (based on availability requirements), GKE → EKS, Cloud Storage → S3, VPC → VPC, and more
- **Generates production-ready Terraform** — `vpc.tf`, `compute.tf`, `database.tf`, `security.tf`, `baseline.tf` with security controls (GuardDuty, CloudTrail, IMDSv2, ECR scanning), and a full `terraform/README.md`
- **Selects the right database migration tool** — pg_dump for small databases, pgcopydb for parallel copy at scale, AWS DMS for zero-downtime migrations — based on your actual database size
- **Produces numbered migration scripts** — prerequisites validation, data migration, container image migration (GCR → ECR), secrets migration (GCP Secret Manager → AWS Secrets Manager), and post-migration validation
- **Estimates monthly costs across three tiers** — Premium, Balanced, and Optimized — using real-time AWS pricing, compared against your current GCP spend

**For AI and agentic migrations:**

- **Detects your entire AI stack** — not just "you use GPT-4o" but your agents, tools, orchestration patterns, memory layers, and multi-model pipelines
- **Recommends three migration paths** for agentic workloads: retarget (keep your framework, swap models), AgentCore Harness (config-based managed agents), or Strands Agents (AWS-native multi-agent SDK)
- **Gives honest pricing comparisons** — finds the best Bedrock option for your workload with current pricing data, including side-by-side estimated monthly cost comparisons against your existing OpenAI/Gemini spend
- **Generates runnable AI artifacts** — `harness.json`, provider adapters, deployment scripts, incremental migration scripts — tailored to your specific models, tools, and architecture

## Plugins

| Plugin               | Description                                                                                                              | Status    |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------- |
| **migration-to-aws** | Assess & plan: resource discovery, architecture mapping, cost analysis, execution planning                               | Available |
| **ai-to-aws**        | Execute: rewrite LLM SDK calls to Bedrock, evaluate quality, deliver a ready-to-merge branch (requires migration-to-aws) | Available |

## Installation

### Claude Code

```bash
# Add the marketplace
/plugin marketplace add awslabs/startups --sparse migrate/plugins

# Install the plugins
/plugin install migration-to-aws@startups
/plugin install ai-to-aws@startups
```

### Codex

```bash
codex plugin marketplace add awslabs/startups
codex plugin install migration-to-aws
codex plugin install ai-to-aws
```

### Cursor

Install from the [Cursor Marketplace](https://cursor.com/marketplace) (AWS Agent Plugins collection):

1. Open **Cursor Settings**
2. Go to **Plugins**
3. Search for **AWS** or **Migration to AWS**
4. Click **Add to Cursor** and choose user or workspace scope
5. Confirm it appears under **Plugins → Installed**

Requires [Cursor >= 2.5](https://cursor.com/changelog/2-5). See the [Cursor plugins documentation](https://cursor.com/docs/plugins) for details.

> **Note:** Cursor installs are distributed via the [Agent Plugins for AWS](https://github.com/awslabs/agent-plugins) marketplace. Claude Code and Codex installs use the `awslabs/startups` marketplace above.

**Alternative (local development):** Clone this repository and symlink the plugin directory to `~/.cursor/plugins/local/migration-to-aws`, then reload Cursor.

## How to Use

After installation, just describe what you want to migrate:

**GCP migrations:**

- "Migrate my GCP infrastructure to AWS"
- "Move my Cloud Run services to Fargate"
- "Migrate my OpenAI app to Amazon Bedrock"
- "Estimate AWS costs for my GCP workload"
- "Migrate my LangChain agents to AWS"

**Heroku migrations:**

- "Migrate my Heroku app to AWS"
- "Move my Heroku Postgres to RDS"
- "Migrate from Heroku to Fargate"
- "Migrate from Heroku to Elastic Beanstalk"
- "Estimate AWS costs for my Heroku workload"
- "Migrate my Heroku Private Space to AWS"

The skill creates a `.migration/<session>/` directory in the current working directory with all artifacts.

## What It Detects

### GCP → AWS

| Category             | GCP → AWS                                                                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Containers           | Cloud Run → Fargate, GKE → EKS                                                                                                                          |
| Serverless           | Cloud Functions → Lambda                                                                                                                                |
| Databases            | Cloud SQL (PostgreSQL/MySQL) → RDS or Aurora (Q6), Cloud SQL (SQL Server) → RDS, Firestore → DynamoDB, Memorystore → ElastiCache, Spanner → Aurora DSQL |
| Storage              | Cloud Storage → S3, Filestore → EFS                                                                                                                     |
| Networking           | VPC → VPC, Cloud Load Balancing → ALB/NLB, Cloud DNS → Route 53, Cloud Armor → WAF + Shield                                                             |
| Secrets              | Secret Manager → Secrets Manager                                                                                                                        |
| AI Models            | OpenAI (GPT-4o, GPT-5.x, o-series), Gemini (Pro, Flash), embeddings, image, speech → Amazon Bedrock                                                     |
| Agentic Frameworks   | LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, Strands, custom agent loops                                                                              |
| Integration Patterns | Direct SDK, LangChain, LlamaIndex, LiteLLM, OpenRouter, MCP servers                                                                                     |
| Agent Architecture   | Single agent, hierarchical, swarm, graph, sequential orchestration                                                                                      |
| Tools & Memory       | Tool definitions with transport/auth classification, memory backends (Redis, Postgres, vector stores)                                                   |

### Heroku → AWS

| Category       | Heroku → AWS                                                                                                                                                               |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Compute        | Dynos (all types) → Elastic Beanstalk (default) — Fargate override for direct container control (and horizontally scaled non-web dynos), EKS override for Kubernetes teams |
| Databases      | Heroku Postgres → RDS or Aurora (plan-matched sizing, DMS/pg_dump/bucardo/wal-g migration methods)                                                                         |
| Caching        | Heroku Redis → ElastiCache (plan-matched node types, HA/encryption preserved)                                                                                              |
| Streaming      | Heroku Kafka → Amazon MSK (broker sizing, topic/partition/replication preserved)                                                                                           |
| Add-ons        | 13+ common add-ons → deterministic AWS mappings via Fast-Path Table; unknown → specialist gate                                                                             |
| Networking     | Private Spaces → VPC with restricted security groups; VPC peering detection and reuse                                                                                      |
| CI/CD          | Pipelines and Review Apps → detect-only (recorded in inventory, no automated migration)                                                                                    |
| Secrets        | Config vars → AWS Secrets Manager or SSM Parameter Store                                                                                                                   |
| Load Balancing | Web dynos → ALB; non-web → no ALB                                                                                                                                          |

## What You Get That a Base LLM Can't

**Infrastructure:**

| Capability                 | Base LLM          | This Plugin                                                                                                                   |
| -------------------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Terraform generation       | Generic templates | Your actual GCP config translated — instance classes, storage sizes, region, VPC CIDRs, security groups                       |
| Security baseline          | Not included      | `baseline.tf` always emitted: GuardDuty, CloudTrail, IMDSv2, ECR scanning, EBS encryption, budget alerts                      |
| Database migration tooling | "Use DMS"         | Selects pg_dump / pgcopydb / DMS based on your actual database size; generates the right script                               |
| Cost estimation            | Stale guesses     | Estimated monthly costs across three tiers (Premium/Balanced/Optimized) using live AWS Pricing API, compared to your GCP bill |
| Migration plan             | Generic checklist | Phased timeline with Go/No-Go gates, rollback procedures, and data integrity checks                                           |

**AI/Agentic:**

| Capability               | Base LLM                          | This Plugin                                                                                                                |
| ------------------------ | --------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Model recommendation     | Generic "use Bedrock"             | Your specific models mapped with estimated monthly costs, honest stay-or-migrate recommendation per model                  |
| Agentic migration        | "Swap ChatOpenAI for ChatBedrock" | Detects your framework, agents, tools, orchestration pattern; recommends retarget vs Harness vs Strands with effort ranges |
| Multi-model coordination | Generic advice                    | Warns about re-embedding requirements, cascade pair testing, tiered strategies — based on your actual model usage          |
| Framework gotchas        | Not covered                       | LangGraph checkpointer incompatibility, CrewAI hierarchical failures with smaller models, async thread pool exhaustion     |
| Regional validation      | Outdated region lists             | Live `get_regional_availability` MCP call — catches "AgentCore Harness isn't in your target region" before you commit      |
| Generated code           | Generic templates                 | Your model IDs, your tool names, your system prompts, your region — in runnable scripts                                    |
| Incremental migration    | Not suggested                     | Run existing OpenAI models on AgentCore infrastructure today, A/B test with Bedrock per-invocation, swap when confident    |

## Agent Skill Triggers

| Agent Skill       | Triggers                                                                                                                                                                                                                                                 |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **gcp-to-aws**    | "migrate GCP to AWS", "move from GCP", "GCP migration plan", "migrate Cloud SQL to RDS or Aurora", "move Cloud Run to Fargate", "estimate AWS costs for my GCP infrastructure", "migrate my OpenAI app to Bedrock", "migrate my LangChain agents to AWS" |
| **heroku-to-aws** | "migrate from Heroku", "Heroku to AWS", "move off Heroku", "migrate Heroku Postgres to RDS", "migrate dynos to Elastic Beanstalk", "migrate dynos to Fargate", "migrate Heroku Private Space", "leave Heroku", "estimate AWS costs for my Heroku app"    |

## MCP Servers

| Server           | Purpose                                                         |
| ---------------- | --------------------------------------------------------------- |
| **awsknowledge** | AWS documentation, regional availability, architecture guidance |
| **awspricing**   | Real-time AWS service pricing for cost estimates                |

## Requirements

- Claude Code >=2.1.29, Codex (latest), or [Cursor >= 2.5](https://cursor.com/changelog/2-5)
- AWS CLI configured with appropriate credentials
- At least one input source: Terraform files, application code, or billing data
- **For GCP AI/agentic migration:** Application source code is required (billing/IaC alone cannot detect agent architecture)
- **For Heroku migration:** Terraform files with `heroku_*` resources are required (Procfile/app.json supplements but cannot stand alone)

## Structure

```
migrate/
├── plugins/                 # Claude Code, Codex, and Cursor plugins
└── docs/                   # Documentation
```
