# AWS Startups

AI agent plugins, tools, and resources for startup builders on AWS.

## Plugins

| Plugin                                                 | Description                                                                                                                                                    | Status    |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| **[migration-to-aws](migrate/)**                       | Assess & plan: migrate GCP/Azure infrastructure and AI workloads to AWS with resource discovery, architecture mapping, cost analysis, and Terraform generation | Available |
| **[ai-to-aws](migrate/)**                              | Execute: rewrite LLM SDK calls to Amazon Bedrock, evaluate output quality against your test cases, and deliver a ready-to-merge git branch                     | Available |
| **[aws-dev-toolkit](solution-architecture/)**          | AWS development toolkit — 35 skills, 11 agents, and 3 MCP servers for building, migrating, and architecture reviews on AWS                                     | Available |
| **[bq-assess](solution-architecture/clis/bq-assess/)** | Read-only BigQuery migration assessment — two-axis effort/complexity scoring, Iceberg DDL, and BigQuery-vs-AWS cost comparison (CLI + guided skill)            | Available |

## Installation

### Claude Code

```bash
# Add the marketplace
/plugin marketplace add awslabs/startups

# Install plugins
/plugin install migration-to-aws@startups-for-aws
/plugin install ai-to-aws@startups-for-aws
```

### Codex

```bash
codex plugin marketplace add awslabs/startups
codex plugin install migration-to-aws
codex plugin install ai-to-aws
```

### Cursor

> **Coming soon** — Plugins are not yet published on the Cursor Marketplace.

## How migration-to-aws and ai-to-aws Work Together

**migration-to-aws** handles assessment and planning — it scans your infrastructure (Terraform, billing, source code), maps services to AWS equivalents, estimates costs, and generates validated Terraform configurations and migration scripts.

**ai-to-aws** handles execution for AI/LLM migrations — it takes the assessment from migration-to-aws, rewrites your SDK calls to Amazon Bedrock's Converse API, runs quality evaluation against a golden dataset, and delivers the changes on a git branch ready to merge. (On platforms without subagent dispatch it runs in inline mode — slower, but fully functional.)

```
┌─────────────────────┐         ┌─────────────────────┐
│  migration-to-aws   │         │     ai-to-aws       │
│                     │         │                     │
│  Discover           │         │  Assess (delegates) │
│  Clarify            │────────▶│  Rewrite            │
│  Design             │         │  Evaluate           │
│  Estimate           │         │  Report             │
│  Generate           │         │                     │
└─────────────────────┘         └─────────────────────┘
     Plan & Artifacts               Execute & Verify
```

## Repository Structure

Each top-level folder is owned by a team and contains their plugins, tools, or resources:

```
awslabs/startups/
├── .claude-plugin/marketplace.json   # Plugin marketplace (lists all plugins)
├── migrate/                          # Migration tools and plugins
│   └── plugins/
│       ├── migration-to-aws/         # Assess & plan
│       └── ai-to-aws/                # Execute (AI/LLM migrations)
├── solution-architecture/            # Solution Architecture plugins (aws-dev-toolkit)
│   └── clis/
│       └── bq-assess/                # BigQuery migration assessment (CLI + skill)
└── ...                               # Future team folders
```

## Adding a Plugin

To add a new plugin to the marketplace:

1. Create your plugin under your team's folder (e.g., `migrate/plugins/my-plugin/`)
1. Include a `.claude-plugin/plugin.json` manifest in your plugin directory
1. Add an entry to the root `.claude-plugin/marketplace.json`:

```json
{
  "name": "my-plugin",
  "source": "./my-team-folder/plugins/my-plugin",
  "version": "1.0.0",
  "description": "What your plugin does"
}
```

1. Submit a PR — requires approval from `@awslabs/startups-admins` (for marketplace changes) and your team's CODEOWNERS (for plugin content)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines, the first-time publishing process, and documentation requirements.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for security issue notifications.

## License

This project is licensed under the Apache-2.0 License. See [LICENSE](LICENSE) for details.
