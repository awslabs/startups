# Agent Advisor Test Context

This repository is a static migration-assessment fixture for `agent-advisor`.
Do not rewrite the source application unless the user explicitly asks.

## Workload

- Existing Anthropic customer-support agent using the first-party Messages API.
- Source model: `claude-3-7-sonnet-latest`.
- Sessions normally last 10-20 minutes.
- Traffic is bursty, with fewer than 20 concurrent sessions.
- The application uses a custom tool loop and Anthropic platform features.
- The team prefers low operational overhead and has no Kubernetes requirement.

## Model Requirements

- Preserve the Anthropic Messages API for the first migration.
- Priority: balanced.
- Required capabilities: tool use and extended thinking.
- Required context: at most 200,000 tokens.
- Expected output: at most 16,000 tokens.
- No Bedrock Guardrails, invocation logging, or multi-model Converse requirement.
- Hypothetical target region: `us-east-1`.

## AWS Access

The user does not have a target AWS account yet. Claude Code's own authentication
does not count as a customer target account. Do not run AWS CLI commands or a live
model probe. Keep account availability provisional and verification `not_run`.

## Test Boundary

Run the recommendation flow and generate its local assessment artifacts. Do not
deploy resources. At optional Migration Plan or POC gates, wait for the user's
explicit choice.
