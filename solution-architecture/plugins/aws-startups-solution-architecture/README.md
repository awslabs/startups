# aws-startups-solution-architecture

Technical AWS solutions for the problems startups actually get stuck on, from the AWS Startups Solution Architecture team.

This plugin provides **technical architecture skills and reference patterns**. It exists so Startup SAs have somewhere to contribute the hard technical patterns they solve repeatedly in the field. If you are an SA with a pattern you have explained more than twice, it belongs here. See [what to contribute](#what-to-contribute).

## Scope

Technical architecture and AWS problem solving. Not founder coaching, not stage-appropriateness advice, not business guidance.

The startup qualifier means the **technical constraints** are startup constraints: no dedicated platform or security team, a fixed cost ceiling that is someone's runway, capacity you cannot commit years to, and a deadline that is a funding milestone. Those constraints change the correct technical answer, and that difference is what this plugin captures.

| This plugin                                                           | Not this plugin                                                        |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Tenant isolation enforced in IAM for a team with no security engineer | How to write an IAM policy (see `aws-iam` in `aws-core`)               |
| Securing scarce GPU capacity without a multi-year commitment          | Which GPU instance family is fastest (see `aws-compute` in `aws-core`) |
| The technical shape of a problem given startup constraints            | Whether a startup is ready for Series A (see AWS Startup Advisor)      |

Two neighbors own adjacent surface, and staying off theirs is the point:

- **[Agent Toolkit for AWS](https://github.com/aws/agent-toolkit-for-aws)** owns general AWS service depth. Consumed here as an upstream dependency, never restated.
- **[AWS Startup Advisor](../../../advisor/)** owns founder-facing and business-facing guidance: stage, runway, credits, AWS Activate, fundraise readiness.

## Skills

The following examples illustrate recurring field problems within this plugin's scope. The OpenAI-on-Bedrock workflows are described separately below.

| Skill                    | Problem it solves                                                                                                                                                                                       |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `multi-tenant-isolation` | Tenancy model per layer, isolation enforced in IAM and the database rather than application code, per-tenant cost attribution, and what to do when one large customer demands dedicated infrastructure. |
| `agentcore-patterns`     | Running a judgment agent inside your own CI path: what it may block, measuring verdict stability before it gates anything, confidence banding, and warm-container staleness.                            |

`agentcore-patterns` is also the layout exemplar: a thin `SKILL.md` router with the depth in `references/`. That is the intended shape for this plugin, since solution-architecture content is mostly reference material.

### OpenAI on Amazon Bedrock

These workflows add current-documentation, retention/residency, managed-state, and standalone review checks around the official AWS migration skills. They help a small team without a separate migration reviewer identify unverified release assumptions and carry explicit constraints into execution.

| Skill                                                                          | Purpose                                                                                                   |
| ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| [`openai-on-bedrock-assessment`](skills/openai-on-bedrock-assessment/SKILL.md) | Check additional release requirements without changing files or running upstream migration phases.        |
| [`openai-on-bedrock-migration`](skills/openai-on-bedrock-migration/SKILL.md)   | Pass the agreed constraints to the official migration workflow, inspect its results, and invoke review.   |
| [`openai-on-bedrock-review`](skills/openai-on-bedrock-review/SKILL.md)         | Review a supplied proposal or change independently, with prioritized findings and explicit evidence gaps. |

SDK migration and its evaluation/reporting pipeline belong to `Skill("aws-startup-advisor:llm-to-bedrock")`. Agent architecture and migration planning belong to `Skill("aws-startup-advisor:agent-advisor")`; general Bedrock mechanics belong to `Skill("aws-core:amazon-bedrock")`. The declared `aws-startup-advisor` dependency supplies the upstream migration skill and its assessment siblings. An unavailable dependency or incompatible installed implementation blocks delegated execution; it does not trigger a local rewrite fallback.

All three workflows read the shared [OpenAI on Bedrock migration playbook](references/openai-on-bedrock-migration-playbook.md). OpenAI Developer Docs and AWS Knowledge MCP connections support current evidence, with official-web fallback. Current AWS endpoint guidance takes precedence over embedded skill preferences, subject to model/API/Region/feature compatibility. Read-only checks do not run the upstream pipeline's writes or live probes.

On hosts without a native Skill tool, resolve and read the installed namespaced skill and its resources. Reading a file does not replace a native capability required by the installed upstream revision: report that limitation and use its documented manual handoff when available. Verify the actual handoff and installed dependency revision; successful plugin discovery alone does not prove migration execution. Local checks, live inference, and model-quality evidence are reported separately.

Original author: Danny Wigg (`dwigg@openai.com`).

For example, in Codex:

```text
Use $aws-startups-solution-architecture:openai-on-bedrock-assessment to check this migration's current documentation, retention, residency, and managed-state readiness. Do not change files.
```

## What to contribute

Verified gaps: as of this writing, neither Agent Toolkit for AWS nor AWS Startup Advisor covers the following, and each is a recurring startup engagement topic. This is the call for contribution.

- **Self-hosted inference serving.** Continuous batching, paged attention and KV cache behavior, concurrency and batch tuning, choosing a serving stack, and when a self-hosted endpoint genuinely beats a managed one on cost at real utilization. Currently zero coverage of the serving mechanics in either neighbor.
- **Scale-to-zero architectures** where an idle environment must cost approximately nothing, including which managed services have a nonzero floor and what that floor actually is.
- **Service quota and limit strategy** ahead of a launch or traffic event, treating quota as lead-time-bound rather than instantaneous.
- **Compliance groundwork** (SOC 2, HIPAA) implemented by a team with no compliance function, scoped to the technical controls and evidence rather than the audit process.
- **Cost regression detection** in the deploy path, so a per-unit cost increase is caught before the monthly bill.

Bring your own topic if it fits the scope test above. Every contribution must pass all three criteria in the [contributing guide](../../CONTRIBUTING.md); criterion 2, no overlap with Agent Toolkit for AWS, rejects most proposals, so check the upstream skill list first.

The existing skills are the intended shape and depth: decision tables, the failure mode named explicitly, an anti-pattern list, and service mechanics delegated upstream rather than restated.

## Upstream dependencies

Declared in `.claude-plugin/plugin.json` and resolved automatically at install time:

- [`aws-core`](https://github.com/aws/agent-toolkit-for-aws/tree/main/plugins/aws-core): infrastructure-as-code authoring, core services, IAM, observability, cost management.
- [`aws-agents`](https://github.com/aws/agent-toolkit-for-aws/tree/main/plugins/aws-agents): building, deploying, and operating AI agents on AWS.
- [`aws-startup-advisor`](https://github.com/aws/agent-toolkit-for-aws/tree/main/plugins/aws-startup-advisor): SDK migration, its required assessment siblings, and agent architecture/migration planning.

All three live in the `claude-plugins-official` marketplace, so this repo's `marketplace.json` lists that marketplace in `allowCrossMarketplaceDependenciesOn`. Without that entry, install fails with a `cross-marketplace` error. They are intentionally unversioned: version constraints resolve against `{plugin-name}--v{version}` git tags, and the upstream repo publishes none, so a semver range would fail with `no-matching-tag`. See [plugin dependencies](https://code.claude.com/docs/en/plugin-dependencies).

On Claude Code, installing this plugin resolves its declared dependencies. Disabling a required dependency can prevent the SA plugin and its skills from loading; restore that dependency before retrying. Verify their installed versions and availability in the host being used. The skills here defer to them for service specifics rather than duplicating that guidance.

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

## License

Apache-2.0
