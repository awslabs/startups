# Agent Skills for AWS Migration

AI agent skills for migrating workloads to AWS, built for [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview), [Codex](https://openai.com/codex), and [Cursor](https://www.cursor.com/).

## What This Does

Point this plugin at your Terraform files, application code, or billing data. It runs a structured 6-phase assessment — discovering what you have, asking the right questions, designing the AWS architecture, estimating costs with real pricing data, and generating runnable migration artifacts.

**Supported migration sources:**

- **GCP → AWS** — Cloud Run, Cloud SQL, GKE, Cloud Functions, Pub/Sub, Cloud Storage, VPC, and AI/agentic workloads
- **Heroku → AWS** — Dynos, Postgres, Redis, Kafka, Private Spaces, Pipelines, and 13+ common add-ons

**For infrastructure migrations:**

- **Maps your resources to AWS equivalents** — Cloud Run → Fargate, Cloud SQL → RDS or Aurora, Dynos → Fargate, Heroku Postgres → RDS/Aurora, and more
- **Generates production-ready Terraform** — `vpc.tf`, `compute.tf`, `database.tf`, `security.tf`, `baseline.tf` with security controls (GuardDuty, CloudTrail, IMDSv2, ECR scanning), and a full `terraform/README.md`
- **Selects the right database migration tool** — pg_dump for small databases, pgcopydb for parallel copy at scale, AWS DMS for zero-downtime migrations — based on your actual database size
- **Produces numbered migration scripts** — prerequisites validation, data migration, container image migration, secrets migration, and post-migration validation
- **Estimates costs across three tiers** — Premium, Balanced, and Optimized — using real-time AWS pricing, compared against your current spend

**For AI and agentic migrations:**

- **Detects your entire AI stack** — not just "you use GPT-4o" but your agents, tools, orchestration patterns, memory layers, and multi-model pipelines
- **Recommends three migration paths** for agentic workloads: retarget (keep your framework, swap models), AgentCore Harness (config-based managed agents), or Strands Agents (AWS-native multi-agent SDK)
- **Gives honest pricing comparisons** — finds the best Bedrock option for your workload with current pricing data, including side-by-side cost comparisons against your existing OpenAI/Gemini spend
- **Generates runnable AI artifacts** — `harness.json`, provider adapters, deployment scripts, incremental migration scripts — tailored to your specific models, tools, and architecture

## What You Get That a Base LLM Can't Give You

**Infrastructure:**

| Capability                 | Base LLM          | This Plugin                                                                                               |
| -------------------------- | ----------------- | --------------------------------------------------------------------------------------------------------- |
| Terraform generation       | Generic templates | Your actual config translated — instance classes, storage sizes, region, VPC CIDRs, security groups       |
| Security baseline          | Not included      | `baseline.tf` always emitted: GuardDuty, CloudTrail, IMDSv2, ECR scanning, EBS encryption, budget alerts  |
| Database migration tooling | "Use DMS"         | Selects pg_dump / pgcopydb / DMS based on your actual database size; generates the right script           |
| Cost estimation            | Stale guesses     | Three-tier pricing (Premium/Balanced/Optimized) using live AWS Pricing API, compared to your current bill |
| Migration plan             | Generic checklist | Phased timeline with Go/No-Go gates, rollback procedures, and data integrity checks                       |

**AI/Agentic:**

| Capability               | Base LLM                          | This Plugin                                                                                                                |
| ------------------------ | --------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Model recommendation     | Generic "use Bedrock"             | Your specific models mapped with pricing, honest stay-or-migrate recommendation per model                                  |
| Agentic migration        | "Swap ChatOpenAI for ChatBedrock" | Detects your framework, agents, tools, orchestration pattern; recommends retarget vs Harness vs Strands with effort ranges |
| Multi-model coordination | Generic advice                    | Warns about re-embedding requirements, cascade pair testing, tiered strategies — based on your actual model usage          |
| Framework gotchas        | Not covered                       | LangGraph checkpointer incompatibility, CrewAI hierarchical failures with smaller models, async thread pool exhaustion     |
| Regional validation      | Outdated region lists             | Live `get_regional_availability` MCP call — catches "AgentCore Harness isn't in your target region" before you commit      |
| Generated code           | Generic templates                 | Your model IDs, your tool names, your system prompts, your region — in runnable scripts                                    |
| Incremental migration    | Not suggested                     | Run existing OpenAI models on AgentCore infrastructure today, A/B test with Bedrock per-invocation, swap when confident    |

## Plugins

| Plugin               | Description                                                                                                              | Status    |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------- |
| **migration-to-aws** | Assess & plan: resource discovery, architecture mapping, cost analysis, execution planning (GCP and Heroku)              | Available |
| **ai-to-aws**        | Execute: rewrite LLM SDK calls to Bedrock, evaluate quality, deliver a ready-to-merge branch (requires migration-to-aws) | Available |

## Installation

### Claude Code

```bash
# Add the marketplace
/plugin marketplace add awslabs/startups --sparse migrate/plugins

# Install the planning plugin
/plugin install migration-to-aws@startups

# (Optional) Install the AI execution plugin
/plugin install ai-to-aws@startups
```

### Codex

```bash
# Add the marketplace
codex plugin marketplace add awslabs/startups

# Install the planning plugin
codex plugin install migration-to-aws

# (Optional) Install the AI execution plugin
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

**Alternative (local development):** Clone this repository and symlink the plugin directory to `~/.cursor/plugins/local/migration-to-aws`, then reload Cursor:

```bash
ln -s "$(pwd)" ~/.cursor/plugins/local/migration-to-aws
```

## migration-to-aws

### Workflow

1. **Discover** — Scan Terraform files, application code, and/or billing data. Detects infrastructure resources, AI models, agentic frameworks, tools, and orchestration patterns.
2. **Clarify** — Ask targeted questions about migration preferences, AI priorities, agentic migration approach, database sizing, and timeline.
3. **Design** — Map source services to AWS equivalents. For AI workloads: select Bedrock models with honest pricing comparison. For agentic workloads: design AgentCore Harness config or Strands architecture.
4. **Estimate** — Calculate monthly AWS costs using real-time pricing data. Compare to current spend.
5. **Generate** — Create migration artifacts: Terraform, provider adapters, `harness.json`, deployment scripts, incremental migration scripts, and documentation.
6. **Feedback** _(optional)_ — Collect anonymized feedback to improve the tool.

### What It Detects

#### GCP → AWS

| Category             | Examples                                                                                              |
| -------------------- | ----------------------------------------------------------------------------------------------------- |
| Infrastructure       | Cloud Run, Cloud SQL, GKE, Cloud Functions, Pub/Sub, Cloud Storage, VPC, DNS                          |
| AI Models            | OpenAI (GPT-4o, GPT-5.x, o-series, embeddings, image, speech), Gemini (Pro, Flash), Anthropic, Cohere |
| Agentic Frameworks   | LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, Strands, custom agent loops                            |
| Integration Patterns | Direct SDK, LangChain, LlamaIndex, LiteLLM, OpenRouter, MCP servers                                   |
| Agent Architecture   | Single agent, hierarchical, swarm, graph, sequential orchestration                                    |
| Tools & Memory       | Tool definitions with transport/auth classification, memory backends (Redis, Postgres, vector stores) |

#### Heroku → AWS

| Category   | Examples                                                                                       |
| ---------- | ---------------------------------------------------------------------------------------------- |
| Compute    | Dynos (all types) → Fargate (default) or EKS (when user selects Kubernetes preference)         |
| Databases  | Heroku Postgres → RDS or Aurora (plan-matched sizing, DMS/pg_dump migration methods)           |
| Caching    | Heroku Redis → ElastiCache (plan-matched node types, HA/encryption preserved)                  |
| Streaming  | Heroku Kafka → Amazon MSK (broker sizing, topic/partition/replication preserved)               |
| Add-ons    | 13+ common add-ons → deterministic AWS mappings via Fast-Path Table; unknown → specialist gate |
| Networking | Private Spaces → VPC with restricted security groups; VPC peering detection                    |
| CI/CD      | Pipelines and Review Apps → detect-only (recorded in inventory, no automated migration)        |
| Secrets    | Config vars → AWS Secrets Manager or SSM Parameter Store                                       |

### Agent Skill Triggers

| Agent Skill       | Triggers                                                                                                                                                                                                                                                 |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **gcp-to-aws**    | "migrate GCP to AWS", "move from GCP", "GCP migration plan", "migrate Cloud SQL to RDS or Aurora", "move Cloud Run to Fargate", "estimate AWS costs for my GCP infrastructure", "migrate my OpenAI app to Bedrock", "migrate my LangChain agents to AWS" |
| **heroku-to-aws** | "migrate from Heroku", "Heroku to AWS", "move off Heroku", "migrate Heroku Postgres to RDS", "migrate dynos to Fargate", "migrate Heroku Private Space", "leave Heroku", "estimate AWS costs for my Heroku app"                                          |

### MCP Servers

| Server           | Purpose                                                         |
| ---------------- | --------------------------------------------------------------- |
| **awsknowledge** | AWS documentation, regional availability, architecture guidance |
| **awspricing**   | Real-time AWS service pricing for cost estimates                |

## ai-to-aws

The `ai-to-aws` plugin extends the assessment from `migration-to-aws` with actual code execution — rewriting your LLM SDK calls to Amazon Bedrock, running quality evaluation against a golden dataset, and delivering a ready-to-merge git branch.

See the [ai-to-aws README](../ai-to-aws/README.md) for full details on prerequisites, usage, and what it does to your repo.

## Requirements

- Claude Code >=2.1.29, Codex (latest), or [Cursor >= 2.5](https://cursor.com/changelog/2-5)
- AWS CLI configured with appropriate credentials
- At least one input source: Terraform files, application code, or billing data
- **For GCP AI/agentic migration:** Application source code is required (billing/IaC alone cannot detect agent architecture)
- **For Heroku migration:** Terraform files with `heroku_*` resources are required (Procfile/app.json supplements but cannot stand alone)
- **For AI execution (ai-to-aws):** Python 3.10+, `uv`, and Bedrock model access enabled
- **`uvx` required for cost estimation:** The `awspricing` MCP server runs via [`uvx`](https://docs.astral.sh/uv/guides/tools/) (part of the `uv` Python package manager). Install with `pip install uv` or `brew install uv`. Without it, the Estimate phase falls back to cached pricing — migration still works but live pricing lookups are unavailable.

## Architecture & contributing

This plugin ships two migration skills built on **different architectures**, and this
matters if you contribute:

- **heroku-to-aws** is built on the **phase DSL** — a declarative frontmatter grammar
  an LLM interprets at runtime, with a static validator that checks the structure
  before anything runs. It is the reference implementation and the **direction for all
  new work**.
- **gcp-to-aws** predates the DSL and uses the **older prose design**. It is maintained,
  but a future effort will port it onto the DSL.

**New skills and phases follow the DSL pattern** (`heroku-to-aws`), not the prose
pattern. The grammar is documented under [`docs/`](docs/) — start with
[docs/01-concepts.md](docs/01-concepts.md). For the full contributor workflow —
architecture, build/validate tasks, the vendored shared-files contract, and how to add
a validator check — see [CONTRIBUTING.md](CONTRIBUTING.md).

Quick start for a local change:

```bash
mise install     # install pinned tools
mise run build   # the full gate: lint (md, types, DSL frontmatter, shared-sync, tests) + fmt + security
```

## Security

For security issue notifications, see the repo-root
[CONTRIBUTING](../../../CONTRIBUTING.md#security-issue-notifications).

## License

This library is licensed under the Apache-2.0 License. See the LICENSE file.
