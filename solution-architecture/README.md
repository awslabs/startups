# Solution Architecture

Startup-specific plugins and tools from the AWS Startups Solution Architecture team.

## Plugins

- **[`aws-startups-solution-architecture`](plugins/aws-startups-solution-architecture/)**. Field practice for the Solutions Architects and technical founders who run startup engagements. Scope an architecture review to a company's stage and runway, run a low-ceremony build loop with a founder, and pressure-test a design before it gets built. Draws all general-purpose AWS service depth from [Agent Toolkit for AWS](https://github.com/aws/agent-toolkit-for-aws) as an upstream dependency rather than restating it.

## Where aws-dev-toolkit went

`aws-dev-toolkit` was removed. Its skills and agents were overwhelmingly general-purpose AWS engineering guidance, which Agent Toolkit for AWS now owns, and that overlap is why it was deprecated. Nothing was ported.

- **Startup-specific guidance:** install AWS Startup Advisor with `/plugin install aws-startup-advisor@claude-plugins-official`, or see [`advisor/`](../advisor/).
- **General-purpose AWS guidance:** use Agent Toolkit for AWS with `aws configure agent-toolkit` (requires AWS CLI 2.35+).

Existing `aws-dev-toolkit` installs continue to function but receive no updates.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the content gate that applies to this folder, and the [root CONTRIBUTING guide](../CONTRIBUTING.md) for the RFC process, code of conduct, and licensing.

Contributions here must pass all three criteria: startup-specific rather than general-purpose AWS guidance, no overlap with Agent Toolkit for AWS, and no reference to deprecated or sunset AWS services. The gate exists so this folder does not re-create the overlap that led to the previous plugin's removal.

## License

Apache-2.0
