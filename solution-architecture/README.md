# Solution Architecture

Startup-specific plugins and tools from the AWS Startups Solution Architecture team.

No plugins are currently published from this folder.

## Where aws-dev-toolkit went

`aws-dev-toolkit` was removed. Its skills and agents were overwhelmingly general-purpose AWS engineering guidance, which Agent Toolkit for AWS now owns, and that overlap is why it was deprecated. Nothing was ported.

- **Startup-specific guidance:** install AWS Startup Advisor with `/plugin install aws-startup-advisor@claude-plugins-official`, or see [`advisor/`](../advisor/).
- **General-purpose AWS guidance:** use Agent Toolkit for AWS with `aws configure agent-toolkit` (requires AWS CLI 2.35+).

Existing `aws-dev-toolkit` installs continue to function but receive no updates.

## Contributing

See the [root CONTRIBUTING guide](../CONTRIBUTING.md). Contributions to this folder must be startup-specific rather than general-purpose AWS guidance, so they do not re-create the overlap with Agent Toolkit for AWS that led to the previous plugin's removal.

## License

Apache-2.0
