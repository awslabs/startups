# aws-startups-solution-architecture

Field practice from the AWS Startups Solution Architecture team, for the Solutions Architects and technical founders who run startup engagements.

This plugin carries only what is specific to startups: how to scope a review to a company's stage and runway, how to judge a design that will be operated by a team with no dedicated ops or security staff, and how to pressure-test a plan against the failure modes that actually end early-stage companies. All general-purpose AWS service depth comes from [Agent Toolkit for AWS](https://github.com/aws/agent-toolkit-for-aws) as an upstream dependency, so it is maintained in one place rather than restated here.

## Skills

| Skill                         | Use it when                                                                                                                                                           |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `startup-architecture-review` | Preparing or running a design review, architecture deep dive, or pre-diligence review for a startup. Scopes findings to runway and delivers a written recommendation. |
| `founder-build-loop`          | A founder wants something built on AWS and the cost of process would exceed the cost of the work. Align in a sentence, sketch in five bullets, then build.            |
| `startup-design-challenger`   | A design is on the table and someone should argue against it, before the team spends runway building it.                                                              |

## Upstream dependencies

Declared in `.claude-plugin/plugin.json` and resolved automatically at install time:

- [`aws-core`](https://github.com/aws/agent-toolkit-for-aws/tree/main/plugins/aws-core): infrastructure-as-code authoring, core services, IAM, observability, cost management.
- [`aws-agents`](https://github.com/aws/agent-toolkit-for-aws/tree/main/plugins/aws-agents): building, deploying, and operating AI agents on AWS.

Both live in the `claude-plugins-official` marketplace, so this repo's `marketplace.json` lists that marketplace in `allowCrossMarketplaceDependenciesOn`. Without that entry, install fails with a `cross-marketplace` error. See [plugin dependencies](https://code.claude.com/docs/en/plugin-dependencies).

Installing this plugin also installs and enables both dependencies. The skills here defer to them for service specifics rather than duplicating that guidance.

## Install

```bash
# Add the marketplace
/plugin marketplace add awslabs/startups

# Install the plugin
/plugin install aws-startups-solution-architecture@startups-for-aws
```

Or load locally during development:

```bash
claude --plugin-dir ./solution-architecture/plugins/aws-startups-solution-architecture
```

## Scope

Contributions here must be startup-specific rather than general-purpose AWS guidance. Content that would read identically for an enterprise belongs in Agent Toolkit for AWS. Founder-facing stage advice, AWS Activate, and credits guidance belong in [AWS Startup Advisor](../../../advisor/). See the [contributing guide](../../../CONTRIBUTING.md).

## License

Apache-2.0
