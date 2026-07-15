---
_phase: confirm
_title: "Confirm — Winner-specific follow-ups"
_requires_phase: clarify
_input:
  - scoring-result.json
  - answers.json
_assemble:
  _file: phases/confirm/confirm-assemble.md
_produces:
  - confirm.json
_advances_to: design
_preconditions:
  - _check_phase_completed: clarify
    _on_failure: _halt_and_inform
  - _check_file_exists: scoring-result.json
    _on_failure: _unrecoverable
  - _validate_json: scoring-result.json
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: confirm.json
    _on_failure: _halt_and_inform
  - _validate_json: confirm.json
    _on_failure: _halt_and_inform
  - _assert: "confirm.json has a confirmed deployment_model and the final agentcore_services list; chosen_runtime is present when the verdict was co_recommend (the runtime the user picked); tool_choices records any native-vs-gateway decisions from Step 2"
    _on_failure: _halt_and_inform
---

# Phase: Confirm — Winner-specific follow-ups

Runs after scoring, before Design. Only asks what the winning runtime needs.

## Step 1 — Read the scoring result

Read `$RUN_DIR/scoring-result.json`. Branch on `verdict`.

## Step 2 — If verdict includes agentcore

Present the deployment model (`deployment_model` from the result) and let the user **confirm or
switch** between **Harness** (no-code, managed loop — declare the agent as config) and
**Framework on Runtime** (bring Strands/LangGraph/CrewAI/custom code). If they picked a
`deployment_preference` in Clarify, it already drove this — restate it and let them change their
mind here. Record the final choice in `confirm.json`.

Then ask which AgentCore services to enable beyond the always-on set (identity, observability,
evaluations, optimization). Multi-select, seeded from `agentcore_services`:

- Gateway (external APIs / MCP), enhanced Identity (OAuth), Policy (high-risk / multi-tenant),
  Memory (cross-session), Managed KB (internal docs), Code Interpreter, Browser, Web Search,
  Sandbox.
- **Conditional (mention only when signals fit — not by default):** Payments (agent pays /
  transacts on the user's behalf — surface if high-risk/transactional actions are detected) and
  Registry (multi-agent discovery / orchestration — surface if `multi_agent == "yes"`). If
  neither signal is present, leave them out rather than listing them.
  For any selected service that can front external tools/data (Gateway, Managed KB, Web Search,
  Memory), **ask** whether they already use a third-party tool for it (e.g. Tavily, Pinecone,
  Browserbase, a REST/MCP server) — do NOT assume greenfield. If yes: switch to AgentCore native,
  or keep existing and connect via Gateway. If no: default to native. Record the choice in
  `tool_choices`.

## Step 3 — If verdict is ecs / eks / lambda

These hand off to migration-to-aws for compute. Still ask which AgentCore **add-on** services
they want (services run on any runtime). Record them.

## Step 4 — If verdict is co_recommend or no_viable_runtime

- co_recommend: present the tied runtimes with "choose A if X / B if Y" framing; ask the user
  to pick one. Record the pick as `chosen_runtime` (Step 5). Then run Step 2/3 for the pick.
- no_viable_runtime: show `blocking_constraints`; ask which constraint can relax; if one
  changes, rewrite `$RUN_DIR/answers.json` with the changed value and re-run the scoring engine
  (same command as clarify.md Step 5):

  ```bash
  uv run --project ${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/scripts python ${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/scripts/scoring.py $RUN_DIR/answers.json
  ```

  This overwrites `$RUN_DIR/scoring-result.json`. Re-read it and return to Step 1.

## Step 5 — Write confirm.json and state

Write `$RUN_DIR/confirm.json` with:

- `deployment_model` (confirmed; for a `co_recommend` pick, the deployment model of the runtime
  the user CHOSE — recompute for the chosen runtime, do not carry a stale value from the tie),
- `agentcore_services` (final list),
- `chosen_runtime` (REQUIRED when the verdict was `co_recommend` — the runtime id the user
  picked in Step 4; the architecture-diagram composer reads this to know which runtime to draw).
  Omit for single-winner verdicts.
- `tool_choices` (per-capability native-vs-gateway choices from Step 2).

```json
{
  "deployment_model": "harness",
  "agentcore_services": ["identity", "memory"],
  "chosen_runtime": "eks",
  "tool_choices": { "web_search": "native" }
}
```

Set `phases.confirm` = completed (read-merge-write). The flow now advances to Design.
