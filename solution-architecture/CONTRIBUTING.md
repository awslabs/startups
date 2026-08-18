# Contributing to `solution-architecture/`

This folder is open to contribution. It is also the folder whose previous plugin, `aws-dev-toolkit`, was removed because its content had grown into a duplicate of [Agent Toolkit for AWS](https://github.com/aws/agent-toolkit-for-aws). The gate below exists so that does not happen again.

Read the [root contributing guide](../CONTRIBUTING.md) first for the RFC process, code of conduct, security reporting, and licensing. This document adds the content gate specific to this folder.

## The gate: all three criteria must pass

A contribution is accepted only if it passes **all three**. Two out of three is a rejection, not a majority.

### 1. Startup-specific, not general-purpose AWS

The contribution must be meaningfully tailored to startups: startup stage, runway, credits and AWS Activate, lean-team defaults (no dedicated ops or security staff), or founder workflows.

General-purpose AWS service guidance that would read identically for an enterprise fails this criterion and belongs in Agent Toolkit for AWS.

This is the criterion that keeps the folder from re-accumulating the general-purpose content that caused the previous removal.

**Referencing AWS products and services is expected and allowed.** The test is whether the _framing_ is startup-specific, not whether AWS services are named. A skill about DynamoDB capacity modes fails. A skill about what to do when your credits expire in six weeks and DynamoDB is your largest line item passes.

### 2. No overlap with Agent Toolkit for AWS

If Agent Toolkit for AWS already covers the capability, the contribution is a duplicate and fails.

**This is the load-bearing check**, because overlap is the conflict that drove the previous deprecation. Before contributing, check the upstream skill list in [`aws-core`](https://github.com/aws/agent-toolkit-for-aws/tree/main/plugins/aws-core/skills) and [`aws-agents`](https://github.com/aws/agent-toolkit-for-aws/tree/main/plugins/aws-agents/skills). Those plugins are declared as upstream dependencies, so their skills are already available to anyone who installs from this folder. Restating them here is strictly worse than depending on them.

Also check [AWS Startup Advisor](../advisor/) for overlap. Founder-facing stage advice, AWS Activate, and credits guidance live there, not here.

Do not use the word "toolkit" in a plugin, skill, or agent name in this folder.

### 3. No deprecated or sunset AWS services

Contributions must not reference, recommend, or depend on AWS services that are deprecated, sunset, or closed to new customers.

Naming a sunset service in order to warn against it, or to describe a migration away from it, is fine. Recommending one as a forward-looking choice is not. Verify current status against AWS documentation rather than from model memory, which reproduces retired service names and deprecated constructs from stale training data.

## Make "startup-specific" explicit, not inferred

A reviewer should not have to infer startup-specificity from prose. Declare it so the check is deterministic and auditable.

- **Required frontmatter field.** Every `SKILL.md` in this folder must declare `audience: startup` under `metadata`:

  ```yaml
  ---
  name: your-skill
  description: "..."
  metadata:
    audience: startup
  ---
  ```

- **Startup framing in the description.** The `description` should state the startup framing directly (stage, runway, credits, lean-team context), the way the AWS Startup Advisor skills do, rather than describing a generic AWS capability.

- **Keywords.** Startup-relevant keywords (`activate`, `credits`, `startup`, `stage`, `runway`) should appear in the skill metadata where they genuinely apply. Do not keyword-stuff: a skill that mentions runway once to pass a grep, while otherwise being general-purpose service guidance, fails criterion 1 on review.

The frontmatter field is the mechanical signal. The reviewer still judges criteria 1 and 2 on substance, because a declared field can be added to any file, and the point of the gate is the substance rather than the field.

## Prefer an upstream dependency over a copy

If a capability exists in Agent Toolkit for AWS, declare it as a dependency rather than vendoring it. See [plugin dependencies](https://code.claude.com/docs/en/plugin-dependencies).

Dependencies on plugins in `claude-plugins-official` require that marketplace to be listed in `allowCrossMarketplaceDependenciesOn` in the root `.claude-plugin/marketplace.json`, which it already is. Note that a semver constraint on those dependencies will fail to resolve until the upstream repository publishes `{plugin-name}--v{version}` git tags, so declare them unversioned for now.

## Before opening a PR

- `mise run fmt` and `mise run lint:md` are clean.
- `claude plugin validate <your-plugin-dir>` passes, and `claude plugin validate .` passes if you touched the marketplace.
- If you added a plugin or changed dependencies, install it from a local marketplace once and confirm it enables with no dependency errors.
- Every new `SKILL.md` declares `audience: startup`.
- No em dashes or en dashes, matching the existing prose style in this folder.

## Review

Changes here require review from the Solution Architecture team, plus admin review for marketplace, `SKILL.md`, and plugin-manifest changes. See [CODEOWNERS](../.github/CODEOWNERS) for the current routing.

**AgentCore review.** Contributions to this folder additionally require review from the AgentCore SME. Agent and AgentCore guidance is owned upstream by the [`aws-agents`](https://github.com/aws/agent-toolkit-for-aws/tree/main/plugins/aws-agents) plugin, which this folder consumes as a dependency, so agent-related content here is the likeliest place for criterion 2 overlap to reappear. Request that review on every PR in this folder rather than only on files with "agent" in the name, since the overlap usually arrives inside a skill about something else.

This requirement is documented here rather than in `CODEOWNERS` because GitHub silently ignores a `CODEOWNERS` entry that names a team which does not exist or lacks write access to the repository. Add the entry once the reviewing team or user handle is confirmed, at which point this paragraph can point at it instead.
