# Migration to AWS

AI agent skills for migrating workloads to AWS, built for [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview), [Codex](https://openai.com/codex), and [Cursor](https://www.cursor.com/).

## What This Does

Point this plugin at your Heroku account (via your authenticated Heroku CLI, read-only and consent-gated), your Terraform files, application code, or billing data. It runs a structured 6-phase assessment — discovering what you have, asking the right questions, designing the AWS architecture, estimating costs with real pricing data, and generating runnable migration artifacts.

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

**For running AI agents on AWS (agent-advisor):**

- **Recommends the right runtime** — deterministic scoring picks AgentCore, ECS/EKS, Lambda, AWS Batch, or Lambda MicroVMs for your agent, based on session duration, traffic shape, isolation, memory, and ops preferences — not a generic "use AgentCore"
- **Decomposes multi-workload systems into units** — a system of several agents, batch jobs, and services is broken into workload units, each scored independently, with a consolidation option (one platform vs best-fit-per-unit) and a whole-system architecture
- **Handles Temporal workers** — self-hosted or Temporal Cloud; worker polling tiers and Activity execution classes become units, Workflow orchestration code is never rewritten
- **Generates a layered recommendation, a migration plan, and a deployable POC** — from "which runtime" through a full plan (reusing the migration engine) to runnable proof-of-concept code and deploy scripts on the chosen runtime
- **Not a cloud migration** — this is the entry point for deciding how and where to run agents on AWS, whether you're building fresh, deploying existing code, or adding AgentCore capabilities to agents already on AWS

**For Vercel migrations:**

- **Derives what it can't export** — Vercel's infrastructure (CloudFront-equivalent behaviors, function tuning, edge routing) isn't directly readable, so discovery works from your build output, source configs (`next.config.js`, `middleware.ts`, `vercel.json`), and the Vercel API instead
- **Computes a Coupling Score** — ISR, edge middleware, edge runtime routes, image optimization, streaming SSR, preview deployments, and Vercel-managed stores (KV/Postgres/Blob/Edge Config/Cron), each with a detection method and why it matters
- **Runs 10 named Pre-Flight Checks** — including a flagship check for cached routes that intersect with middleware (a behavior change on every AWS target, not just one), computed unconditionally and filtered to whatever outcome fits you
- **Recommends one of three honest outcomes** — OpenNext/SST (serverless), ECS Fargate (containerized), or a Vercel+AWS Hybrid (your backend moves, your Next.js app and PR previews stay on Vercel) — via a fixed, auditable decision order, never a guess
- **Tells you what you'd lose** — PR preview deployments first, always — and says plainly when this tooling isn't a fit for you (a low-traffic app with no AWS credits is often better served by a VPS)
- **Estimates costs with Vercel comparison** — three-tier AWS projection (Premium/Balanced/Optimized) compared against your current Vercel spend, using cached AWS pricing data with live MCP fallback
- **Generates production-ready Terraform** — `baseline.tf` (GuardDuty, CloudTrail, IMDSv2, budget alerts), VPC, compute (Fargate/Lambda/SST per outcome), peripherals (RDS, ElastiCache, S3, EventBridge), and numbered migration scripts with dry-run defaults

## Plugins

| Plugin               | Description                                                                                                                                                                                                                           | Status    |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| **migration-to-aws** | Assess, plan & execute: GCP/Heroku resource discovery, architecture mapping, cost analysis, execution planning, LLM code rewrite to Bedrock (llm-to-bedrock skill), and AI-agent runtime selection + POC on AWS (agent-advisor skill) | Available |

## Installation

### Claude Code

```bash
# Add the marketplace
/plugin marketplace add awslabs/startups --sparse migrate/plugins

# Install the plugin
/plugin install migration-to-aws@startups
```

### Codex

```bash
codex plugin marketplace add awslabs/startups
codex plugin install migration-to-aws
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
- "Discover my GCP project and estimate AWS costs"
- "Move my Cloud Run services to Fargate"
- "Migrate my OpenAI app to Amazon Bedrock"
- "Estimate AWS costs for my GCP workload"
- "Migrate my LangChain agents to AWS"

**Heroku migrations:**

- "Migrate my Heroku app to AWS"
- "Discover my Heroku apps and estimate AWS costs"
- "Move my Heroku Postgres to RDS"
- "Migrate from Heroku to Fargate"
- "Migrate from Heroku to Elastic Beanstalk"
- "Estimate AWS costs for my Heroku workload"
- "Migrate my Heroku Private Space to AWS"

**Vercel assessments:**

- "Migrate my Next.js app off Vercel"
- "Assess my Vercel migration"
- "Should I migrate off Vercel"
- "Vercel to Fargate"
- "Vercel coupling score"

**Running AI agents on AWS (agent-advisor):**

- "Which runtime should I use for my agent — AgentCore, ECS, EKS, or Lambda?"
- "Deploy my LangGraph agent on AWS and build a POC"
- "I have an agent idea — what should I build on AWS?"
- "Migrate my Temporal workers to AWS"
- "I'm already on AWS and want to add AgentCore memory/gateway to my agent"

GCP/Heroku migrations write a `.migration/<session>/` directory; agent-advisor writes a `.agent-advisor/<session>/` directory. Both land in the current working directory with all artifacts.

**Live Heroku discovery — how it works:** No Terraform or exports needed. If `heroku login` works in your terminal, just ask — the agent requests your consent, then inventories your account using read-only list/info CLI commands. It captures app names, dyno types, add-on plans and prices, domains, pipelines, and config var **key names only**. It never reads config var values, credentials, or your API token, and never runs a command that creates, changes, or deletes anything. If you also have `heroku_*` Terraform, the agent cross-checks it against your live account and reports drift.

**Live GCP discovery — how it works:** No Terraform or exports needed. If `gcloud auth login` works in your terminal, just ask — the agent confirms the target project and requests your consent, then inventories it using read-only list/describe commands. It captures resource names, types, regions, sizing, network topology, and env var **names only** — never env var values, secret values, database contents, or access tokens, and never a command that creates, changes, or deletes anything. If you also have Terraform, the agent cross-checks it against your live project and reports drift. (AI/agentic detection still needs your application code.)

**Live Heroku discovery — how it works:** No Terraform or exports needed. If `heroku login` works in your terminal, just ask — the agent requests your consent, then inventories your account using read-only list/info CLI commands. It captures app names, dyno types, add-on plans and prices, domains, pipelines, and config var **key names only**. It never reads config var values, credentials, or your API token, and never runs a command that creates, changes, or deletes anything. If you also have `heroku_*` Terraform, the agent cross-checks it against your live account and reports drift.

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

### Vercel → AWS

| Category            | Vercel → AWS                                                                                                      |
| ------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Compute (Outcome A) | Next.js app → OpenNext/SST (server functions, CloudFront, ISR tag cache + revalidation queue, image optimization) |
| Compute (Outcome B) | Next.js app → ECS Fargate (`next start` behind ALB + CloudFront)                                                  |
| Compute (Outcome C) | Backend/API routes → API Gateway + Lambda or Fargate (Terraform); Next.js app + PR previews stay on Vercel        |
| Storage             | Blob → S3, Postgres → RDS/Aurora (Neon often correct to keep), KV → ElastiCache (Upstash often correct to keep)   |
| Config/Secrets      | Edge Config → Parameter Store/AppConfig, env vars → Secrets Manager/SSM                                           |
| Scheduling          | Cron → EventBridge Scheduler                                                                                      |
| Detect-only         | Preview deployments (no AWS equivalent — this drives the Hybrid outcome and is the top "what you lose" item)      |

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

| Agent Skill       | Triggers                                                                                                                                                                                                                                                                                                                        |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **gcp-to-aws**    | "migrate GCP to AWS", "move from GCP", "GCP migration plan", "migrate Cloud SQL to RDS or Aurora", "move Cloud Run to Fargate", "estimate AWS costs for my GCP infrastructure", "migrate my OpenAI app to Bedrock", "migrate my LangChain agents to AWS"                                                                        |
| **heroku-to-aws** | "migrate from Heroku", "Heroku to AWS", "move off Heroku", "migrate Heroku Postgres to RDS", "migrate dynos to Elastic Beanstalk", "migrate dynos to Fargate", "migrate Heroku Private Space", "leave Heroku", "estimate AWS costs for my Heroku app"                                                                           |
| **vercel-to-aws** | "migrate from Vercel", "Vercel to AWS", "move off Vercel", "migrate Next.js off Vercel", "assess my Vercel migration", "leave Vercel", "Vercel to Fargate", "Vercel to OpenNext", "should I migrate off Vercel"                                                                                                                 |
| **agent-advisor** | "which runtime for my agent", "AgentCore vs ECS vs EKS vs Lambda", "deploy an AI agent on AWS", "I have an agent idea — what do I build", "move my agents to AWS with a plan", "add AgentCore memory/gateway/identity to my agent", "migrate Temporal workers to AWS", "run Temporal on AWS", "build a POC for my agent on AWS" |

## MCP Servers

| Server            | Purpose                                                                                                                                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **awsknowledge**  | AWS documentation, regional availability, architecture guidance                                                                                                                                                       |
| **awspricing**    | Real-time AWS service pricing for cost estimates                                                                                                                                                                      |
| **temporal-docs** | Temporal Knowledge Base, operated by kapa.ai (queries are sent to that third-party service). Used only by the agent-advisor Temporal branch; one-time login via `/mcp`, falls back to a public-web lookup if declined |

## Requirements

- Claude Code >=2.1.29, Codex (latest), or [Cursor >= 2.5](https://cursor.com/changelog/2-5)
- AWS CLI configured with appropriate credentials
- At least one input source: an authenticated `gcloud` or `heroku` CLI (live discovery), Terraform files, application code, or billing data
- **For GCP infrastructure migration:** an authenticated `gcloud` CLI (recommended — live, read-only discovery with your consent, with drift detection against any Terraform found) or Terraform files / billing exports
- **For GCP AI/agentic migration:** Application source code is required (billing/IaC/live discovery alone cannot detect agent architecture)
- **For Heroku migration:** an authenticated Heroku CLI (recommended — live, read-only discovery with your consent) or Terraform files with `heroku_*` resources (Procfile/app.json supplements but cannot stand alone). When both are available, live data is authoritative for current state and Terraform drift is surfaced.
- **For Vercel migration:** repo access with a locally-runnable `next build`, plus a Vercel API token, are both required — the assessment does not run on partial Tier 1 inputs. Vercel tokens can't be permission-scoped to read-only, so scope by resource instead (project-scoped when one project is in scope), pick a short expiration, and revoke after the assessment; the skill only ever issues read (GET) requests, enforced by its capture-step endpoint whitelist
- **For agent-advisor:** `uv` (for deterministic scoring); application source code when deploying/migrating existing agents (an idea-only run needs no code)

## Structure

```
migrate/
├── plugins/                 # Claude Code, Codex, and Cursor plugins
└── docs/                   # Documentation
```
