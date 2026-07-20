# AWS Startups

AI agent plugins, tools, and resources for startup builders on AWS.

## Plugins

| Plugin                                        | Description                                                                                                                                                                                                                                                                                                                    | Status    |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------- |
| **[migration-to-aws](migrate/)**              | Assess, plan & execute: migrate GCP/Heroku infrastructure and AI workloads to AWS (discovery, architecture mapping, cost analysis, Terraform), rewrite LLM SDK calls to Amazon Bedrock, and select an AWS runtime + build a POC for AI agents. Bundles the gcp-to-aws, heroku-to-aws, llm-to-bedrock, and agent-advisor skills | Available |
| **[aws-dev-toolkit](solution-architecture/)** | AWS development toolkit — 35 skills, 11 agents, and 3 MCP servers for building, migrating, and architecture reviews on AWS                                                                                                                                                                                                     | Available |

## Installation

### Claude Code

```bash
# Add the marketplace
/plugin marketplace add awslabs/startups

# Install the plugin
/plugin install migration-to-aws@startups-for-aws
```

### Codex

```bash
codex plugin marketplace add awslabs/startups
codex plugin install migration-to-aws
```

### Cursor

> **Coming soon** — Plugins are not yet published on the Cursor Marketplace.

## How the migration-to-aws skills work together

`migration-to-aws` is a single plugin bundling four skills that cover assessment, execution, and agent runtime decisions:

- **gcp-to-aws / heroku-to-aws** — assess and plan a platform migration: scan infrastructure (Terraform, billing, source code), map services to AWS equivalents, estimate costs, and generate validated Terraform and migration scripts.
- **llm-to-bedrock** — execute an AI/LLM migration: rewrite your SDK calls to Amazon Bedrock's Converse API, run quality evaluation against a golden dataset, and deliver the changes on a ready-to-merge git branch. (On platforms without subagent dispatch it runs inline — slower, but fully functional.) The migration skills delegate the AI-execution step here.
- **agent-advisor** — decide how and where to run AI agents on AWS: deterministic runtime scoring (AgentCore / ECS / EKS / Lambda / Batch / MicroVMs), multi-workload decomposition into units, Temporal worker handling, and a layered recommendation → migration plan → deployable POC.

```
migration-to-aws (one plugin, four skills)

  gcp-to-aws ─┐
              ├─▶ assess & plan ──▶ llm-to-bedrock ──▶ rewrite · evaluate · branch
  heroku-to-aws ┘   (Terraform,       (AI/LLM execution)
                     cost, scripts)

  agent-advisor ──▶ score runtime ──▶ recommendation · plan · POC
                    (how/where to run agents on AWS)
```

## Repository Structure

Each top-level folder is owned by a team and contains their plugins, tools, or resources:

```
awslabs/startups/
├── .claude-plugin/marketplace.json   # Plugin marketplace (lists all plugins)
├── migrate/                          # Migration tools and plugins
│   └── plugins/
│       └── migration-to-aws/         # Assess, plan, execute + agent runtime advisor
│                                     #   skills: gcp-to-aws, heroku-to-aws,
│                                     #           llm-to-bedrock, agent-advisor
├── solution-architecture/            # Solution Architecture plugins (aws-dev-toolkit)
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
