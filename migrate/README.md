# Migrate

AI agent plugins and tools for migrating workloads to AWS.

## Plugins

| Plugin               | Description                                                                                                                                   | Status    |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| **migration-to-aws** | Migrate GCP/Azure infrastructure and AI workloads to AWS with resource discovery, architecture mapping, cost analysis, and execution planning | Available |

## Installation

### Claude Code

```bash
/plugin marketplace add awslabs/startups --sparse migrate
/plugin install migration-to-aws@startups-migrate
```

### Kiro

Powers are available under `powers/` for direct use with Kiro.

## Structure

```
migrate/
├── plugins/          # Claude Code and Cursor plugins
├── powers/           # Kiro powers (generated from plugin source)
├── docs/             # Documentation
├── tests/            # Evaluation fixtures and invariants
└── tools/            # Evaluation tooling and generators
```

## Ownership

This folder is maintained by the **Startups-Migrate** team. See `OWNERS.yaml` for routing details.
