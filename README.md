# AWS Startups

> [!IMPORTANT]
> **This repository is deprecated.** Its plugins have moved to
> [**aws/agent-toolkit-for-aws**](https://github.com/aws/agent-toolkit-for-aws), which is the successor
> to the MCP servers, skills, and plugins AWS released under [AWS Labs](https://github.com/awslabs).
>
> `aws-startup-advisor` and `migration-to-aws` are no longer maintained here. Existing installations
> will keep working, but they will receive no further updates of any kind — no new features, no fixes.
> All development continues in the Agent Toolkit, so migrate to get anything beyond what is already
> installed. See [Where things moved](#where-things-moved) for the plugin-by-plugin mapping and
> updated install commands.

AI agent plugins, tools, and resources for startup builders on AWS.

## Where things moved

| This repository                        | Replacement                                                                                                 | Notes                                                                                                                         |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **aws-startup-advisor**                | [`aws-startup-advisor`](https://github.com/aws/agent-toolkit-for-aws/tree/main/plugins/aws-startup-advisor) | Moved as-is. All twelve skills are present in the Agent Toolkit copy.                                                         |
| **migration-to-aws**                   | [`aws-startup-advisor`](https://github.com/aws/agent-toolkit-for-aws/tree/main/plugins/aws-startup-advisor) | Folded in rather than ported separately — all seven of its skills ship inside `aws-startup-advisor`. Install that one plugin. |
| **aws-startups-solution-architecture** | No replacement yet                                                                                          | `agentcore-patterns`, `multi-tenant-isolation`, and `self-hosted-llm-batch-inference` have not moved. Keep using this repo.   |

### Why the Agent Toolkit

- **IAM condition keys** that distinguish agent actions from human actions, so a policy can allow read-only
  access through the MCP server even when the underlying role can write.
- **CloudWatch metrics and CloudTrail logging** for every request, so agent activity is monitorable and auditable.
- **End-to-end skill evaluations**, so workflows are verified to complete rather than assumed to.

## Plugins

| Plugin                                                           | Description                                                                                                                                                                                                                                                                                                                                                                                        | Status                                    |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| **[aws-startup-advisor](advisor/)**                              | Startup-focused build + migrate guidance built on patterns from 350,000+ startups: AWS Activate credits & offers, a knowledge base (sample architectures, learn articles), a copy-paste prompt library, stage-aware architecture advice, and interactive scaffolding — plus the full migration toolkit (azure-to-aws, gcp-to-aws, heroku-to-aws, llm-to-bedrock, agent-advisor, tf-best-practices) | Deprecated — [moved](#where-things-moved) |
| **[migration-to-aws](migrate/)**                                 | Assess, plan & execute: migrate Azure/GCP/Heroku infrastructure and AI workloads to AWS (discovery, architecture mapping, cost analysis, Terraform), rewrite LLM SDK calls to Amazon Bedrock, and select an AWS runtime + build a POC for AI agents. Bundles the azure-to-aws, gcp-to-aws, heroku-to-aws, llm-to-bedrock, and agent-advisor skills                                                 | Deprecated — [moved](#where-things-moved) |
| **[aws-startups-solution-architecture](solution-architecture/)** | Technical AWS solutions for the problems startups get stuck on: multi-tenant SaaS isolation enforced in IAM rather than application code, and running a judgment agent such as an LLM reviewer inside a CI path. Draws general-purpose AWS service depth from Agent Toolkit for AWS as an upstream dependency                                                                                      | Available                                 |

## Installation

Install `aws-startup-advisor` from the Agent Toolkit. It supersedes both `aws-startup-advisor` and
`migration-to-aws` from this repository.

### Claude Code

```bash
# Add the marketplace
/plugin marketplace add aws/agent-toolkit-for-aws

# Install the plugin
/plugin install aws-startup-advisor@agent-toolkit-for-aws
```

### Codex

```bash
codex plugin marketplace add aws/agent-toolkit-for-aws

codex plugin install aws-startup-advisor@agent-toolkit-for-aws
```

### Cursor

> **Coming soon** — Plugins are not yet published on the Cursor Marketplace.

### Already installed from this repository?

Remove the old marketplace so you do not run two copies of the same skills:

```bash
# Claude Code
/plugin uninstall aws-startup-advisor@startups-for-aws
/plugin uninstall migration-to-aws@startups-for-aws
/plugin marketplace remove startups-for-aws
```

`aws-startups-solution-architecture` has not moved. If you use it, keep this marketplace added and
install only that plugin:

```bash
/plugin install aws-startups-solution-architecture@startups-for-aws
```

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
├── advisor/                           # AWS Startup Advisor plugin
│   └── plugins/
│       └── aws-startup-advisor/       # Architecture, cost, security & migration
│                                      #   skills: architect-for-startups,
│                                      #           knowledge-base-for-startups,
│                                      #           start-building-for-startups,
│                                      #           prompt-library-for-startups,
│                                      #           migration-to-aws
├── migrate/                          # Migration tools and plugins
│   └── plugins/
│       └── migration-to-aws/         # Assess, plan, execute + agent runtime advisor
│                                      #   skills: gcp-to-aws, heroku-to-aws,
│                                      #           llm-to-bedrock, agent-advisor
├── solution-architecture/            # Solution Architecture plugins
│   └── plugins/
│       └── aws-startups-solution-architecture/
│                                      #   skills: multi-tenant-isolation,
│                                      #           agentcore-patterns
│                                      #   deps: aws-core, aws-agents (Agent Toolkit for AWS)
└── ...                               # Future team folders
```

## Adding a Plugin

> [!NOTE]
> This marketplace is closed to new plugins. Add new plugins to
> [aws/agent-toolkit-for-aws](https://github.com/aws/agent-toolkit-for-aws) instead. The steps below
> remain only for maintaining `aws-startups-solution-architecture`, which has not moved.

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

New contributions belong in [aws/agent-toolkit-for-aws](https://github.com/aws/agent-toolkit-for-aws).
The only code still maintained in this repository is `aws-startups-solution-architecture`, which has
not moved.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines, the first-time publishing process, and documentation requirements.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for security issue notifications.

## License

This project is licensed under the Apache-2.0 License. See [LICENSE](LICENSE) for details.
