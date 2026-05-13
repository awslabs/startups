# Sample Agent Skills for AWS Migration

AI agent skills for migrating workloads to AWS, built for [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview) and [Cursor](https://www.cursor.com/).

## What This Does

Point this plugin at your codebase, Terraform files, or GCP billing data. It runs a structured 6-phase migration assessment — discovering what you have, asking the right questions, designing the AWS architecture, estimating costs with real pricing data, and generating runnable migration artifacts.

**For AI-focused startups**, it goes further:

- **Detects your entire AI stack** — not just "you use GPT-4o" but your agents, tools, orchestration patterns, memory layers, and multi-model pipelines
- **Recommends three migration paths** for agentic workloads: retarget (keep your framework, swap models), AgentCore Harness (config-based managed agents), or Strands Agents (AWS-native multi-agent SDK)
- **Surfaces options you wouldn't find on your own** — like Strands Agents (open-source, powers AgentCore internally) and AgentCore Harness (declare an agent in 3 API calls)
- **Generates runnable artifacts** — `harness.json`, deployment scripts, incremental migration scripts, provider adapters — tailored to your specific models, tools, and architecture
- **Gives honest pricing comparisons** — Gives honest pricing comparisons — finds you the best Bedrock option for your workload with current April 2026 pricing data, including side-by-side cost comparisons against your existing OpenAI/Gemini spend

## What You Get That a Base LLM Can't Give You

| Capability | Base LLM | This Plugin |
|-----------|----------|-------------|
| Model recommendation | Generic "use Bedrock" | Your specific models mapped with pricing, honest assessment per model, stay-or-migrate recommendation |
| Agentic migration | "Swap ChatOpenAI for ChatBedrock" | Detects your framework, agents, tools, orchestration pattern. Recommends retarget vs Harness vs Strands with effort ranges. |
| Multi-model coordination | Generic advice | Warns about re-embedding requirements, cascade pair testing, tiered strategies — based on your actual model usage |
| Framework gotchas | Not covered | Documents real issues: LangGraph checkpointer incompatibility, CrewAI hierarchical process failures with smaller models, async thread pool exhaustion |
| Regional validation | Outdated region lists | Live `get_regional_availability` MCP call — catches "AgentCore Harness isn't in your target region" before you commit |
| Cost estimation | Stale pricing | Three-tier pricing: cached current rates, live AWS Pricing API, fallback. Shows ±5-10% accuracy. |
| Generated code | Generic templates | Your model IDs, your tool names, your system prompts, your region — in runnable scripts |
| Incremental migration | Not suggested | Run existing OpenAI models on AgentCore infrastructure today, A/B test with Bedrock per-invocation, swap when confident |

## Plugins

| Plugin               | Description                                                                                                            | Status    |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------- | --------- |
| **migration-to-aws** | Migrate GCP infrastructure and AI/agentic workloads to AWS with resource discovery, architecture mapping, cost analysis, and execution planning | Available |

## Installation

### Claude Code

```bash
# Add the marketplace
/plugin marketplace add aws-samples/sample-agent-skills-for-aws-migration

# Install the plugin
/plugin install migration-to-aws@sample-agent-skills-for-aws-migration
```

### Cursor

> **Coming soon** — This plugin is not yet published on the Cursor Marketplace. In the meantime, you can use it locally by cloning this repository and pointing Cursor to the plugin directory.

## migration-to-aws

### Workflow

1. **Discover** — Scan Terraform files, application code, and/or billing data. Detects GCP resources, AI models, agentic frameworks, tools, and orchestration patterns.
2. **Clarify** — Ask targeted questions about migration preferences, AI priorities, agentic migration approach, memory requirements, and timeline.
3. **Design** — Map GCP services to AWS equivalents. For AI workloads: select Bedrock models with honest pricing comparison. For agentic workloads: design AgentCore Harness config or Strands architecture.
4. **Estimate** — Calculate monthly AWS costs using real-time pricing data. Compare to current GCP/OpenAI spend.
5. **Generate** — Create migration artifacts: Terraform, provider adapters, `harness.json`, deployment scripts, incremental migration scripts, and documentation.
6. **Feedback** _(optional)_ — Collect anonymized feedback to improve the tool.

### What It Detects

| Category | Examples |
|----------|----------|
| Infrastructure | Cloud Run, Cloud SQL, GKE, Cloud Functions, Pub/Sub, Cloud Storage, VPC, DNS |
| AI Models | OpenAI (GPT-4o, GPT-5.4, o-series, embeddings, image, speech), Gemini (Pro, Flash), Anthropic, Cohere |
| Agentic Frameworks | LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, Strands, custom agent loops |
| Integration Patterns | Direct SDK, LangChain, LlamaIndex, LiteLLM, OpenRouter, MCP servers |
| Agent Architecture | Single agent, hierarchical, swarm, graph, sequential orchestration |
| Tools & Memory | Tool definitions with transport/auth classification, memory backends (Redis, Postgres, vector stores) |

### Agent Skill Triggers

| Agent Skill    | Triggers                                                                                                           |
| -------------- | ------------------------------------------------------------------------------------------------------------------ |
| **gcp-to-aws** | "migrate GCP to AWS", "move from GCP", "GCP migration plan", "estimate AWS costs", "migrate my AI app to AWS" |

### MCP Servers

| Server           | Purpose                                          |
| ---------------- | ------------------------------------------------ |
| **awsknowledge** | AWS documentation, regional availability, architecture guidance |
| **awspricing**   | Real-time AWS service pricing for cost estimates |

## Requirements

- Claude Code >=2.1.29 or [Cursor >= 2.5](https://cursor.com/changelog/2-5)
- AWS CLI configured with appropriate credentials
- At least one input source: Terraform files, application code, or GCP billing data
- **For AI/agentic migration:** Application source code is required (billing/IaC alone cannot detect agent architecture)

## Development

This project uses [mise](https://mise.jdx.dev) for tool management and task running.

```bash
# Install tools
mise install

# Run the full build (lint, format, validate, security)
mise run build

# Individual tasks
mise run lint          # All linters (markdown, manifests, cross-refs)
mise run fmt           # Format with dprint
mise run fmt:check     # Check formatting
mise run security      # All security scanners
```

### Evaluating Changes

Prompt files are the source code of this plugin. Changes to files under
`features/migration-to-aws/skills/gcp-to-aws/` can alter migration behavior
in subtle ways. Run the evaluation harness before submitting a PR:

```bash
# 1. Quick structural check (instant, no Claude API calls)
mise run eval:check

# 2. Run the migration skill against a test fixture (see table below)
cd tests/fixtures/<FIXTURE_NAME>
# In Claude Code: "migrate from GCP to AWS"

# 3. Validate the output
python tools/eval_check.py \
  --migration-dir .migration/<RUN_ID> \
  --fixture <FIXTURE_NAME>

# 4. Commit results
git add .eval-results.json
```

#### Test Fixtures

Pick the fixture that covers your change area. For broad changes, run
`minimal-cloud-run-sql` first, then any fixture specific to your change.

| Fixture                    | Use when you changed...                                                 | Invariants |
| -------------------------- | ----------------------------------------------------------------------- | ---------- |
| `minimal-cloud-run-sql`    | General prompt changes, state machine, phase ordering, generate phase   | 26         |
| `bigquery-specialist-gate` | BigQuery handling, specialist gate, analytics exclusion                 | 9          |
| `ai-workload-openai`       | AI detection, model mapping, lifecycle rules, Category F questions      | 11         |
| `user-preferences`         | Clarify question flow, preference schema, Design preference consumption | 10         |
| `negative-services`        | Classification rules, auth exclusion, forbidden service mappings        | 8          |

See [docs/evaluation-guide.md](docs/evaluation-guide.md) for the full workflow
and how to add new invariants.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
