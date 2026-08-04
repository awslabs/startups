# Anthropic Agent Advisor Demo

This fixture exercises the local `agent-advisor` Anthropic-to-Bedrock model
recommendation flow without requiring an AWS account or an Anthropic API key.

For the complete change summary and operator procedure, read
[the Claude Code test SOP](../../../../doc/2026-07-20-agent-advisor-anthropic-recommendation-changes-and-test-sop.md).

The source intentionally contains Claude 3.7 migration surfaces:

- Anthropic Messages API and a custom tool loop
- extended thinking with `budget_tokens`
- legacy sampling parameters
- assistant prefill for JSON output
- prompt caching
- a first-party server tool
- Files API and Message Batches helpers

The application is for static assessment. Unit tests do not call Anthropic.

## Prerequisites

- Claude Code
- `uv`
- This repository checked out on the feature branch

## Load the Current Local Plugin

From this directory:

```bash
./run-claude.sh
```

The script starts Claude Code with the current checkout:

```bash
claude --plugin-dir ./local-plugin
```

`local-plugin/skills/agent-advisor` is a symbolic link to the current checkout's
skill. The wrapper intentionally excludes unrelated plugin skills, so their
validation state cannot affect this focused test. This is preferable to
marketplace installation while the feature branch is not published.

Confirm Claude Code can discover the focused plugin:

```bash
./run-claude.sh plugin details agent-advisor-local-test
```

The component inventory must show `Skills (1) agent-advisor`.

## Scenario A: Messages Continuity

Start the flow with:

```text
Use the agent-advisor skill to assess this existing Anthropic agent and recommend
the AWS agent architecture and Bedrock model/API path. I do not have an AWS
account, so do not run a live probe or deploy anything.
```

Use the requirements already recorded in `CLAUDE.md`. When asked:

- choose the technical audience
- keep the Messages API continuity requirement
- decline the optional live probe because no target AWS account exists
- decline Migration Plan and POC if the goal is only to test recommendation

Expected primary model decision:

```text
decision_status: recommended
api_path: mantle_messages
primary_model: anthropic.claude-opus-4-8
invocation_model_id: anthropic.claude-opus-4-8
verification.probe_status: not_run
```

Sonnet 4.6 ranks first for balanced workloads but is unavailable on Mantle in the
dated catalog, so Opus 4.8 is the first compatible Messages-path candidate.

Validate the artifact:

```bash
uv run python scripts/check_recommendation.py \
  .agent-advisor/<run-id>/model-recommendation.json default
```

## Scenario B: Hard Path Conflict

Use a fresh run directory and prompt:

```text
Use agent-advisor for this project. We must preserve the Anthropic Messages API,
and we also require Bedrock Guardrails. Stop when the model/path conflict is
presented. We do not have an AWS account.
```

Expected result:

```text
decision_status: decision_required
primary_model: null
api_path: null
decision_options: mantle_messages and runtime_converse
```

Validate with:

```bash
uv run python scripts/check_recommendation.py \
  .agent-advisor/<run-id>/model-recommendation.json conflict
```

## Scenario C: Runtime Governance

Use a fresh run directory and prompt:

```text
Use agent-advisor for this project. Messages compatibility is not required.
Require Bedrock Guardrails and invocation logging, allow Global CRIS, and use
balanced model priority. Do not run a live probe because there is no AWS account.
```

Expected primary model decision:

```text
decision_status: recommended
api_path: runtime_converse
primary_model: anthropic.claude-sonnet-4-6
invocation_model_id: global.anthropic.claude-sonnet-4-6
verification.probe_status: not_run
```

Validate with:

```bash
uv run python scripts/check_recommendation.py \
  .agent-advisor/<run-id>/model-recommendation.json runtime
```

## Published Plugin Installation

After this branch is published to the marketplace, Claude Code installation is:

```text
/plugin marketplace add awslabs/startups --sparse migrate/plugins
/plugin install migration-to-aws@startups
```

The marketplace version may not contain this feature until publication.
