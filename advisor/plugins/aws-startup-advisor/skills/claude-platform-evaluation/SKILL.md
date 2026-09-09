---
name: claude-platform-evaluation
description: "Help a startup choose among the Anthropic API, Claude Platform on AWS, and Claude on Amazon Bedrock. Use when the user asks where to use Claude, wants a provider/access-path comparison, or needs a small validation plan before committing to one path. Not for rewriting an existing application to Bedrock (use llm-to-bedrock) or selecting an agent runtime such as AgentCore, ECS, or Lambda (use agent-advisor)."
---

# Evaluate Claude Access Paths

Turn a startup's operating constraints into a defensible first-pass choice among:

1. Anthropic API
2. Claude Platform on AWS
3. Claude on Amazon Bedrock

Do not declare a universal winner. Separate requirements from preferences, identify what is
still unknown, and recommend the smallest useful validation step.

**Reference freshness:** 2026-09-09. Capability details change; cite the bundled public source
and state this date when a decision depends on feature availability.

## Route requests correctly

Use this skill for access-path selection before implementation or migration.

- Existing application must be rewritten to Bedrock → use `llm-to-bedrock`.
- User needs an AWS runtime for an agent → use `agent-advisor`.
- User needs a broader startup architecture → use `architect-for-startups`.
- User already chose one path and only needs setup help → answer that setup question directly.

## Start with the user's own description

Invite the user to describe their situation in free form. Do not begin with a long questionnaire.
Extract and show four separate buckets:

- **Must-haves** — a path is disqualified if it cannot meet one.
- **Acceptable alternatives** — a native feature may be replaced by a clearly named integration.
- **Preferences** — useful tie-breakers, not disqualifiers.
- **Unknowns** — unanswered items that could change the recommendation.

Read [`references/decision-guide.md`](references/decision-guide.md) for the product boundaries and
decision-changing questions. Ask only the smallest set of missing questions needed to separate the
remaining paths. Confirm the summary with the user before making a final recommendation.

## Apply hard constraints before preferences

Use this precedence:

1. **AWS-operated inference or AWS private networking is mandatory** → favor Amazon Bedrock.
2. **Anthropic-operated inference is acceptable, AWS procurement is preferred, and
   Anthropic-native API features are important** → evaluate Claude Platform on AWS first.
3. **Direct Anthropic commercial ownership or the broadest current Anthropic-native API and
   administration surface is most important** → evaluate the Anthropic API first.
4. **No path survives every must-have, or an unknown could reverse the decision** → give a
   provisional recommendation and a two-path validation plan.

Never offset a failed must-have with several preferences. Never silently substitute another
provider, endpoint, model, or tool.

## Handle capability gaps explicitly

When a user names web search, files, code execution, agentic coding, multi-model access, a gateway,
or private networking, read
[`references/capability-alternatives.md`](references/capability-alternatives.md).

Use these labels:

- **Native** — provided by the selected access path.
- **Integration alternative** — separately operated component that can meet the underlying need.
- **Not equivalent** — similar outcome, but different behavior, trust boundary, or operations.
- **Unverified** — current documentation or a live test is still required.

Do not describe an AWS-native or third-party integration as the same feature as an
Anthropic-native server tool.

## Produce a decision, not a feature dump

Return this structure:

```markdown
## Recommendation

<Recommended path or "Provisional: validate A vs B">

## Why it fits

- <Must-have matched>
- <Important preference matched>

## Why the other paths fall short

- <Path>: <failed must-have, material trade-off, or "still viable">

## Capability gaps and alternatives

- <Need>: <native / integration alternative / not equivalent / unverified>

## Smallest useful next test

1. <One connectivity or capability test>
2. <Evidence to capture>
3. <Decision that the result changes>

## Open risks and owners

- <Unknown>: <person or team that should resolve it>
```

If the user has not supplied a decision-changing requirement, keep the recommendation provisional.
Do not convert an unknown to `false`.

## Design the smallest useful validation

Start offline. A good first test proves one disputed assumption, not the entire platform.

Examples:

- one synthetic Messages request to prove identity, endpoint, region, and model access
- one native server-tool request when that tool is the reason for considering a path
- one private-network connectivity test when public egress is prohibited
- one gateway request when centralized identity, budgets, or multi-model routing is mandatory

Before any live call:

- get explicit authorization for the provider, expected cost, network access, and test data
- use synthetic data unless the user explicitly approves another classification
- use environment variables, workload roles, or the provider's supported credential chain
- never ask the user to paste a secret into chat or save credentials in a report

For a fair comparison, keep the model snapshot, request, tool schema, and output limit aligned where
the providers support them. Record the provider, endpoint, region, authentication mode, exact model
ID, request ID, latency, token metadata, and result. One request is a connectivity check, not a
latency, quality, reliability, or cost benchmark.

## Example patterns

Read [`references/scenarios.md`](references/scenarios.md) only when an example would clarify the
decision. Adapt the pattern to the user's facts; do not treat examples as customer evidence.

## Boundaries

- Do not make compliance, security, legal, privacy, procurement, or production-approval decisions.
- Do not infer that AWS billing means AWS operates inference; identify the actual operator.
- Do not assume two paths expose the same model or feature on the same date.
- Do not collect credentials or customer prompts in the qualification summary.
- Do not run load tests, deploy gateways, change IAM, enable model access, or subscribe to products
  without a separate explicit request and authorization.
