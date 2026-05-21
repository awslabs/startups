# AWS Startups

AI agent plugins for startup builders on AWS — works with Claude Code, Codex, Cursor, Kiro, GitHub Copilot, and 50+ other AI coding agents.

---

## Which plugin do you need?

| I want to... | Use this |
|---|---|
| Understand AWS programs, credits, and partner offers | [advisor-for-startups](#advisor-for-startups) |
| Get architectural guidance and sample code for building on AWS | [advisor-for-startups](#advisor-for-startups) |
| Move my infrastructure from GCP to AWS | [migration-to-aws](#migration-to-aws) |
| Migrate my OpenAI or Gemini app to Amazon Bedrock | [migration-to-aws](#migration-to-aws) |
| Move my LangChain, CrewAI, or AutoGen agents to AWS | [migration-to-aws](#migration-to-aws) |
| Compare AWS vs GCP costs for my stack | [migration-to-aws](#migration-to-aws) |
| Get runnable Terraform for my AWS architecture | [migration-to-aws](#migration-to-aws) |

---

## Plugins

### advisor-for-startups

**Three skills that help you get started on AWS:**

- **`knowledge-base-for-startups`** — AWS Startups knowledge base: FAQ, credits guide, programs, partner offers, sample architectures, and 277 learn articles. All searchable and offline after install.
- **`prompt-library-for-startups`** — 30 AWS-curated prompts plus 4 downloadable agents (Migration, Multi-Account Transition Advisor, Bill Shock Preventer, Service Quota).
- **`start-building-for-startups`** — interactive discovery workflow that gathers your requirements and writes an AWS architectural scaffold directly into your codebase.

The three skills are cross-aware — `start-building-for-startups` consults the knowledge base and prompt library mid-flow.

**Install** (works with 50+ agents including Kiro, Claude Code, Cursor, Codex, GitHub Copilot):

```bash
# Install all three skills into your agent
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/advisor-for-startups --skill '*' --agent <agent>

# Examples
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/advisor-for-startups --skill '*' --agent kiro-cli
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/advisor-for-startups --skill '*' --agent claude-code
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/advisor-for-startups --skill '*' --agent codex
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/advisor-for-startups --skill '*' --agent cursor
```

> **Always pass `--agent`.** Omitting it writes skills to `.agents/skills/` which most agents won't discover. See the [full agent list](https://github.com/vercel-labs/skills#supported-agents) for all 50+ supported values.

Full documentation: [advisor/README.md](advisor/README.md)

---

### migration-to-aws

**Migrate from GCP to AWS — including your entire AI stack.**

Moves infrastructure (Cloud Run → Fargate, Cloud SQL → Aurora, GKE → EKS), OpenAI/Gemini workloads to Amazon Bedrock, and agentic systems (LangChain, CrewAI, AutoGen, OpenAI Agents SDK) to AWS-native frameworks. Generates runnable Terraform, migration scripts, provider adapters, and deployment artifacts. Gives honest model-by-model pricing comparisons so you know exactly when Bedrock saves money and when it doesn't.

**What it does:**

Runs a 6-phase assessment against your Terraform files, application code, or GCP billing data:

1. **Discover** — maps your GCP resources, AI models, agent frameworks, and billing
2. **Clarify** — asks targeted questions to understand your priorities and constraints
3. **Design** — maps GCP services to AWS equivalents; selects the right Bedrock model for your workload with honest pricing comparisons
4. **Estimate** — calculates monthly AWS costs using real-time pricing; compares against your current spend
5. **Generate** — produces runnable Terraform, migration scripts, provider adapters, `harness.json`, and a full migration guide
6. **Feedback** _(optional)_ — anonymized usage data to improve the tool

**Install:**

### Claude Code

```bash
/plugin marketplace add awslabs/startups --sparse migrate/plugins
/plugin install migration-to-aws@startups
```

### Codex

```bash
codex plugin marketplace add awslabs/startups --sparse migrate/plugins
codex plugin install migration-to-aws
```

### Cursor

> Coming soon on the Cursor Marketplace. Clone the repo and point Cursor at `migrate/plugins/migration-to-aws/` to use it locally today.

Full documentation: [migrate/plugins/migration-to-aws/README.md](migrate/plugins/migration-to-aws/README.md)

---

## Repository structure

```
awslabs/startups/
├── advisor/                          # AWS Startups advisor skills
│   └── plugins/
│       └── advisor-for-startups/    # Knowledge base, prompt library, build workflow
├── migrate/                          # Migration plugins
│   └── plugins/
│       └── migration-to-aws/        # GCP → AWS migration plugin
└── ...                               # Future team folders
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines and the plugin publishing process.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for security issue notifications.

## License

Apache-2.0. See [LICENSE](LICENSE).
