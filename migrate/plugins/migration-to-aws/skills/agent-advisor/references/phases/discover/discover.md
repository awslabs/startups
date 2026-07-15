---
_phase: discover
_title: "Discover — Lightweight Detection"
_requires_phase: intake
_input: workspace
_assemble:
  _file: phases/discover/discover-assemble.md
_produces:
  - context-signals.json
_advances_to: clarify
_preconditions:
  - _check_phase_completed: intake
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: context-signals.json
    _on_failure: _halt_and_inform
  - _validate_json: context-signals.json
    _on_failure: _halt_and_inform
  - _assert: "context-signals.json contains only signals detected with reasonable confidence, with a _detected array; model_provider recorded when detection succeeded"
    _on_failure: _halt_and_inform
---

# Phase: Discover — Lightweight Detection

Only runs for build_deploy / migrate when the user provided a code path. Stays independent
(does NOT require the migration-to-aws plugin).

## Step 1 — Scan for signals (read-only)

In the provided path, look for:

- **Framework** (imports / requirements.txt / package.json): `strands`, `langgraph` /
  `langchain`, `crewai` / `autogen`, `openai` (Agents SDK), else `custom` / `none`.
- **Model provider**: openai / anthropic / google-genai / bedrock mentions.
- **Session/timeout hints**: timeout configs, long-running loops, queue/HITL patterns.
- **Multi-tenant hints**: per-user/tenant scoping, separate contexts.
- **Compute hints**: GPU instance types, heavy compute (compilation, ML inference).
- **Data store hints**: Redis/DynamoDB/vector store connections.
- **Temporal orchestration**: `temporalio` (Python) / `go.temporal.io` (Go) /
  `temporal-sdk` (Java) / `@temporalio/*` (TypeScript) imports or dependencies.

## Step 2 — Map to pre-filled answers

Write `$RUN_DIR/context-signals.json` mapping detected signals onto scoring keys, e.g.:

```json
{
  "framework": "langgraph",
  "multi_agent": "yes",
  "session_state": "hitl",
  "model_provider": "openai",
  "_detected": [
    "framework from imports",
    "multi_agent from graph with 2+ nodes",
    "model_provider from SDK imports"
  ]
}
```

Only include keys you can detect with reasonable confidence. Everything else stays for Clarify.

`model_provider` (openai | anthropic | google-genai | bedrock | none) is not a scoring key —
it records which AI provider the code calls, and gates the migration-plan offer in Generate
Step 6. Include it whenever provider detection succeeded.

## Step 2.5 — Temporal branch offer (only if Temporal SDK detected)

If Step 1 found Temporal SDK usage, write `orchestrator: "temporal"` into
`context-signals.json`, then offer the branch (AskUserQuestion), worded for the `audience`
recorded in `.phase-status.json`:

- `technical`: "Your agents are orchestrated by Temporal. The recommended path migrates the
  Workers to AWS and keeps orchestration code untouched — switch to the Temporal Worker
  branch?"
- `business`: "Your system is built on Temporal — a service that coordinates your automated
  work behind the scenes. There's a dedicated path that moves it to AWS **without changing
  how your business logic works** (lower risk, no rewrite). Use that path?" (Options in the
  same plain terms; avoid "Workers"/"orchestration code" jargon in the labels.)
- **Confirm** → set `entry_point = "temporal_worker"` in `.phase-status.json` (read-merge-write;
  the signal alone is not a routing decision — the persisted entry_point is), set
  `phases.discover` = completed, then load `references/phases/temporal-worker/temporal-worker.md` and follow it.
  Do NOT continue into Clarify.
- **Decline** → set `temporal_branch_declined: true` (top level) in `.phase-status.json` and
  continue the normal flow (Step 3). A resumed session MUST NOT re-offer the branch while this
  flag is set. `orchestrator: "temporal"` stays in context-signals.json as an ordinary signal.
- If `temporal_branch_declined` is already `true` (re-entry after a session break), skip this
  step entirely.

## Step 3 — Tell the user what was detected

List the detected signals so the user can correct them in Clarify. These pre-fills let
Clarify skip questions (Clarify asks fewer for build_deploy/migrate).

**Determinism boundary (important):** these detections are a _best-effort LLM interpretation_
of code, NOT deterministic facts. They become inputs to the deterministic scoring engine, so a
wrong detection silently biases scoring. Mitigation: (1) only write a signal you can detect
with high confidence — when unsure, omit it and let Clarify ask; (2) always present detected
signals to the user as "detected: X (correct me if wrong)" so they have a correction
opportunity before scoring runs. This is the one point where LLM interpretation enters the
otherwise deterministic pipeline.

## Step 4 — Write state

Set `phases.discover` = completed.
