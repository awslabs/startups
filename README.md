# AWS Startups

AI agent plugins, tools, and resources for startup builders on AWS.

## Plugins

| Plugin                           | Description                                                                                                                                   | Status    |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| **[migration-to-aws](migrate/)** | Migrate GCP/Azure infrastructure and AI workloads to AWS with resource discovery, architecture mapping, cost analysis, and execution planning | Available |
| **[aws-startups-advisor](https://github.com/awslabs/startups/tree/main/advisor)**   | Three sibling skills that work alongside each other in any modern AI coding agent (Kiro, Claude Code, Cursor, Codex, GitHub Copilot, and 50+ others)                       | Available |

## Installation

### Claude Code

```bash
# Add the marketplace
/plugin marketplace add awslabs/startups

# Install a plugin
/plugin install migration-to-aws@startups-for-aws
```

### Cursor

> **Coming soon** — Plugins are not yet published on the Cursor Marketplace.

## Repository Structure

Each top-level folder is owned by a team and contains their plugins, tools, or resources:

```
awslabs/startups/
├── .claude-plugin/marketplace.json   # Plugin marketplace (lists all plugins)
├── migrate/                          # Migration tools and plugins
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
