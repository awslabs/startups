# Privacy Policy

Last updated: 2026-04-24

This document describes how the `aws-dev-toolkit` Claude Code plugin handles data. The plugin is maintained by Amazon Web Services and distributed under the Apache-2.0 license.

## What this plugin is

The plugin is a static bundle of:

- Skill definitions (`SKILL.md` markdown files)
- Subagent definitions (markdown files)
- Hook definitions (`hooks.json`)
- MCP server configuration (`.mcp.json`)

It ships no runtime binaries, no background processes, and no remote services operated by the plugin maintainers.

## Data the plugin collects

**The plugin itself collects no data.** It does not run telemetry, analytics, crash reporting, or usage tracking. It does not send any information to the plugin maintainers or to AWS.

## Data the plugin causes to be sent to third parties

When you enable the plugin, it configures three MCP servers that run locally on your machine. These servers make outbound requests on your behalf using credentials and configuration you provide:

| MCP Server     | Upstream Destination                                                     | What is sent                        | Whose policy governs                                    |
| -------------- | ------------------------------------------------------------------------ | ----------------------------------- | ------------------------------------------------------- |
| `awsiac`       | `awslabs.aws-iac-mcp-server` (runs locally)                              | Template content you ask it to lint | Runs on your machine; sends nothing to Anthropic or AWS |
| `awsknowledge` | `knowledge-mcp.global.api.aws`                                           | Your documentation search queries   | [AWS Privacy Notice](https://aws.amazon.com/privacy/)   |
| `awspricing`   | `awslabs.aws-pricing-mcp-server` (runs locally, queries AWS Pricing API) | Service / region filter requests    | [AWS Privacy Notice](https://aws.amazon.com/privacy/)   |

Skills and agents in the plugin may also suggest or issue AWS CLI calls. Those calls use **your** AWS credentials and are governed by your agreement with AWS, not by the plugin maintainers.

## Data Anthropic / Claude Code receives

When you use any Claude Code plugin, the content of your conversation — including text loaded from skill and agent files — is sent to Anthropic as part of the normal model inference flow. That data flow is governed by Anthropic's privacy policy, not this document. See Anthropic's privacy policy at <https://www.anthropic.com/legal/privacy>.

## Sensitive data

The plugin never requests secrets, credentials, or personally identifiable information. If you paste sensitive values into a prompt while this plugin is enabled, that content follows the normal Claude Code data flow described above — the plugin does not intercept, log, or store it.

## Children's privacy

The plugin is not directed at children and the maintainers do not knowingly collect information from children. The plugin collects no information.

## Changes

Changes to this policy are tracked in the repository's git history.

## Contact

For questions about this policy, open an issue at <https://github.com/awslabs/startups/issues>.
