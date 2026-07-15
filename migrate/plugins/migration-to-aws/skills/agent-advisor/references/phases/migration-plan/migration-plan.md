---
_phase: migration-plan
_title: "Migration Plan — inline execution of gcp-to-aws phases"
_requires_phase: generate
_input:
  - design.json
  - confirm.json
  - answers.json
_fragments:
  - _id: migration-plan-gcp-constraints
    _trigger: { _when: "always (gcp-to-aws is the migration engine)" }
    _file: phases/migration-plan/migration-plan-gcp-constraints.md
_assemble:
  _file: phases/migration-plan/migration-plan-assemble.md
_produces:
  - { file: migration-plan-injection.json, _when: "the target repo exists (not an idea-only migrate — otherwise migration_plan is not_applicable and the phase stops)" }
_advances_to: poc
_preconditions:
  - _check_phase_completed: generate
    _on_failure: _halt_and_inform
_postconditions:
  - _assert: "unless migration_plan was set not_applicable (idea-only) — migration-plan-injection.json exists and is valid JSON, carrying the translated injected constraints, the advisor rationale, and the absolute repo + migration_dir paths"
    _on_failure: _halt_and_inform
  - _assert: "the inline engine's Generate phase reached HANDOFF_OK (aws-design-ai.json exists with a non-empty ai_architecture in the recorded migration_dir), and migration_plan_ctx {repo, migration_dir} was recorded in .phase-status.json"
    _on_failure: _halt_and_inform
---

# Phase: Migration Plan — inline execution of gcp-to-aws phases

Reached after Generate when the user confirmed **Gate 1** (offered in generate.md Step 6).
This phase produces a complete migration plan by directly reading and executing
the sibling `gcp-to-aws` skill's phase instruction files — no Skill tool call, no turn
boundary. Everything runs inside the current agent-advisor session, so Steps 5–6
(record artifacts, offer Gate 2) execute in the same turn without interruption.

gcp-to-aws files are **read-only**: this phase never edits them.

## Path definitions (resolve first, before any other step)

```
$GCP_BASE = ${CLAUDE_PLUGIN_ROOT}/skills/gcp-to-aws
```

**IMPORTANT — relative path resolution table:** gcp-to-aws
instruction files use several relative path prefixes. Resolve each as follows (the only path
that does NOT go under `$GCP_BASE`is`$MIGRATION_DIR`, which stays under the target repo per Step 1):

| Path prefix in instruction     | Resolves to                                      |
| ------------------------------ | ------------------------------------------------ |
| `references/shared/...`        | `$GCP_BASE/references/shared/...`                |
| `references/design-refs/...`   | `$GCP_BASE/references/design-refs/...`           |
| `references/clustering/...`    | `$GCP_BASE/references/clustering/...`            |
| `references/phases/...`        | `$GCP_BASE/references/phases/...`                |
| `shared/...` (short form)      | `$GCP_BASE/references/shared/...`                |
| `design-refs/...` (short form) | `$GCP_BASE/references/design-refs/...`           |
| `data/...`                     | `$GCP_BASE/data/...` (**not** under references/) |
| `phases/...` (short form)      | `$GCP_BASE/references/phases/...`                |

Examples:

- `shared/pricing-cache.md` → `$GCP_BASE/references/shared/pricing-cache.md`
- `data/sdk-capability-map.json` → `$GCP_BASE/data/sdk-capability-map.json`
- `references/clustering/terraform/classification-rules.md` → `$GCP_BASE/references/clustering/terraform/classification-rules.md`

## Step 0 — Update agent-advisor state immediately

Before doing anything else, read-merge-write agent-advisor's `.phase-status.json`:

- `current_phase` = `"migration_plan"`
- `phases.migration_plan` = `"in_progress"`

This must happen **first** so that if the session is interrupted at any point, the advisor
resumes at migration-plan.md rather than at generate.md.

## Step 1 — Resolve the target repo and set $MIGRATION_DIR

The plan needs the repo containing the workload to migrate. If Discover ran (`phases.discover
== "completed"`), reuse the repo path the user gave then (from `context-notes.md` or
`context-signals.json`). Otherwise ask for it now. Resolve to an absolute path (`$REPO`).

If the user has no code (idea-only migrate), STOP: tell them a migration plan needs an
existing workload, set `phases.migration_plan = "not_applicable"`, and continue to the Gate
2 branch in generate.md Step 7.

Set `$MIGRATION_DIR` using the gcp-to-aws convention: `$REPO/.migration/<MMDD-HHMM>/`
(current timestamp). Create the directory and `.migration/.gitignore` (`*\n!.gitignore`).
All gcp-to-aws artifacts are written here.

## Step 2 — Assemble the injection context

Read ALL of: `$RUN_DIR/answers.json`, `$RUN_DIR/design.json`, `$RUN_DIR/confirm.json`, and
`$RUN_DIR/handoff-summary.md`. If `handoff-summary.md` does not exist (build_deploy path),
write it first by following `references/handoff/handoff-migration.md` Step 1, then return.

**`answers.json` is nested:** shape is `{"entry_point": "...", "answers": {...}}`.
Every answer key is read from the inner `answers` object.

Build the injection context — this is carried forward into every gcp-to-aws phase execution
as the set of already-determined constraints. Translate per this table (never inject `unknown`):

| Source                                                                             | Inject as (gcp-to-aws field)                | Translation                                                                    |
| ---------------------------------------------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------ |
| `design.json.deployment_model == "harness"`                                        | `ai_constraints.agentic.migration_approach` | `"harness"`                                                                    |
| `deployment_model == "framework_on_runtime"` AND `.answers.framework == "strands"` | same                                        | `"strands"`                                                                    |
| `deployment_model == "framework_on_runtime"` (langgraph/crewai/custom)             | same                                        | `"retarget"`                                                                   |
| winning runtime NOT agentcore (ecs/eks/lambda/microvms)                            | same                                        | `"retarget"` + compute note                                                    |
| `.answers.memory_needs`                                                            | `ai_constraints.agentic.memory_requirement` | `cross_session`→`"cross_session"`, `session_only`→`"session"`, `none`→`"none"` |
| `.answers.session_duration`                                                        | `ai_constraints.agentic.task_duration`      | `under_15min`→`"medium"`, `15min_to_8hr`→`"long"`, `over_8hr`→`"very_long"`    |
| `.answers.region` — only when a **specific** region was named                      | `design_constraints.target_region`          | pass through; bare single/multi/global → do not inject                         |
| `ai_constraints.agentic.incremental_migration`                                     | —                                           | never injected                                                                 |

**Non-AgentCore verdicts:** inject `migration_approach: "retarget"` and add a note:
"Compute target is `<runtime>` per agent-advisor scoring — do not recommend AgentCore
Runtime as the compute layer."

**AgentCore verdicts only — deployment-target note:** when the winning runtime IS
agentcore, add a deployment-target note to the context (this is a serving requirement of
the target runtime, NOT a migration-approach constraint — it does not conflict with
`retarget`): "The app will be deployed on AgentCore Runtime, which invokes it via
`POST /invocations` and health-checks it via `GET /ping`. The Design phase's
`code_migration` output should account for exposing these entrypoints alongside the app's
existing interface." gcp-to-aws has no schema field for this — it is best-effort context;
the POC phase tolerates its absence from `aws-design-ai.json` and applies the standard
contract regardless.

Write the injection context to `$RUN_DIR/migration-plan-injection.json`:

```json
{
  "injected_constraints": {/* the translated fields above */},
  "deployment_target_note": "<the AgentCore entrypoint note above, or null for non-AgentCore>",
  "advisor_rationale": "<top 3 scoring signals from handoff-summary.md>",
  "repo": "<abs $REPO>",
  "migration_dir": "<abs $MIGRATION_DIR>"
}
```

**Suppression is best-effort:** gcp-to-aws's Clarify may still ask questions whose answers
were injected — present the injected value as the pre-selected default so the user can
confirm with one keypress.

## Step 2.5 — Load global constraints

Read `references/phases/migration-plan/migration-plan-gcp-constraints.md` and follow everything in it
for the duration of this phase. It covers: design principles (dev sizing, no human costs,
re-platform default, BigQuery gate), context loading budget, conditional file table,
feedback checkpoint auto-skip, and hybrid stack warning.

## Step 3 — Announce the transition

Tell the user:

> "I'm now generating the full migration plan. I'll run the migration analysis directly
> (Discover → Clarify → Design → Estimate → Generate) in this same session, so your
> runtime and deployment choices carry over — you won't be asked those again. It may ask
> a few additional questions that weren't covered above, such as monthly AI spend and
> migration priority."

## Step 4 — Execute gcp-to-aws phases in order

Execute each phase by reading its instruction file and following it **exactly** as if it
were loaded by gcp-to-aws's own state machine. The path rule from the header applies: all
relative references in those files resolve from `$GCP_BASE`.

**Two separate state files — do NOT mix them up:**

- `$MIGRATION_DIR/.phase-status.json` — gcp-to-aws's own state. Each phase file
  (discover.md, clarify.md, etc.) writes and reads this file itself per its own protocol.
  migration-plan.md does NOT touch it — let each phase file manage it.
- `$RUN_DIR/.phase-status.json` — agent-advisor's state. Already set to
  `current_phase = "migration_plan"` in Step 0 and NOT touched again until Step 5.
  gcp-to-aws's files never read or write this file (they only know about `$MIGRATION_DIR`).

This separation is what keeps the two state machines independent. After each phase's
`HANDOFF_OK`, simply proceed to the next phase — no extra state writes needed.

### Phase A — Discover

Read and execute: `$GCP_BASE/references/phases/discover/discover.md`

Key behaviors:

- `$MIGRATION_DIR` is already created (Step 1) — when discover.md Step 0 checks for
  existing runs, the directory exists but has no `.phase-status.json` yet → treat as
  fresh run (skip the resume/fresh/cancel prompt)
- discover.md writes its own `.phase-status.json` to `$MIGRATION_DIR` — let it do so
- Injection context is NOT applied at this stage; it's carried as live context for Clarify
- On `HANDOFF_OK`: `ai-workload-profile.json` (and/or IaC artifacts) present in `$MIGRATION_DIR`

### Phase B — Clarify

Read and execute: `$GCP_BASE/references/phases/clarify/clarify.md`
(which in turn loads `clarify-ai-only.md` or `clarify-ai.md` as appropriate)

Key behavior — apply injection context:
When Clarify asks a question whose answer is already in the injection context (Step 2),
treat it as extracted (`chosen_by: "extracted"`) and do NOT re-ask it — present it in the
detection summary as pre-filled. Only ask what remains (typically: monthly AI spend, migration
priority, cross-cloud preference).

Also inject `design_constraints.target_region` into `preferences.json` directly when a
specific region was named (mark `chosen_by: "extracted"`).

On `HANDOFF_OK`: `preferences.json` present in `$MIGRATION_DIR`.

### Phase C — Design

Read and execute: `$GCP_BASE/references/phases/design/design.md`
(which routes to `design-ai.md`, `design-infra.md`, etc.)

On `HANDOFF_OK`: `aws-design-ai.json` (and/or other design artifacts) present.

### Phase D — Estimate

Read and execute: `$GCP_BASE/references/phases/estimate/estimate.md`

On `HANDOFF_OK`: `estimation-ai.json` (and/or other estimate artifacts) present.

### Phase E — Generate

Read and execute: `$GCP_BASE/references/phases/generate/generate.md`
(which routes to `generate-ai.md`, `generate-artifacts-ai.md`, etc.)

**Skip the Feedback phase** — feedback is optional user telemetry and produces no data
artifacts needed by the POC. After generate's `HANDOFF_OK`, go directly to Step 5 below
— do NOT load `$GCP_BASE/references/phases/feedback/feedback.md`.

On `HANDOFF_OK`: `generation-ai.json` + `MIGRATION_GUIDE.md` + `README.md` + artifact
files present in `$MIGRATION_DIR`.

## Step 5 — Record context and validate artifacts

Read-merge-write `$RUN_DIR/.phase-status.json`:

- `phases.migration_plan` = `"completed"`
- `migration_plan_ctx` = `{"repo": "<abs $REPO>", "migration_dir": "<abs $MIGRATION_DIR>"}`

Verify `$MIGRATION_DIR/aws-design-ai.json` exists and has a non-empty `ai_architecture`.
If missing → AI path did not complete; show the error, set `phases.migration_plan =
"in_progress"`, and stop. `estimation-ai.json` may be absent on some routes — note it,
don't fail.

**Verdict check:** if agent-advisor's winning runtime is NOT agentcore but the produced
plan centers AgentCore as the compute layer, surface the disagreement explicitly: show
both choices, state that agent-advisor's deterministic scoring is authoritative, and let
the user decide.

## Step 5.5 — Regenerate the architecture diagram (plan-backed)

The diagram written during Generate is the generic Path 1 selection diagram — it does not
show the app's real components. Now that `aws-design-ai.json` exists, re-generate it as the
**Path 2 plan-backed app architecture**: load `references/diagram/build-diagram.md` and
follow its **Path 2**, overwrite `$RUN_DIR/diagram.md`, and re-embed the new diagram into
Section 4 of `$RUN_DIR/recommendation.md` (replacing the Path 1 diagram). If an HTML report
was already generated, note that it will show the updated diagram only if regenerated — it
is acceptable to leave the HTML report's diagram as-is (it links to recommendation.md for
the authoritative version).

## Step 5.6 — Inject the help banner into the migration report (post-process)

gcp-to-aws's Generate produces `$MIGRATION_DIR/migration-report.html`. gcp-to-aws is
read-only, so do NOT edit its report generator — instead post-process the OUTPUT file:
load `references/report-help-banner.md`, and if `migration-report.html` exists, inject the
banner's CSS rules before `</style>` (or add a new `<style>` before `</head>` if none) and
the banner's HTML block at the TOP — right after the opening `<body>` / the report's header,
before the first content block. Substitute `{{ HELP_URL }}`. This gives the migration report
the same top-of-page "Need help?" CTA as the recommendation and POC reports, without touching
gcp-to-aws. If the file doesn't exist (report generation was skipped), skip this step silently.

## Step 6 — Offer Gate 2 (immediately after gcp-to-aws Generate's own summary)

gcp-to-aws's `generate.md` already outputs a full structured summary (artifacts produced,
timelines, risks, TODOs, next steps) — that IS the plan summary. Do not re-summarize it.

Immediately after that summary, add ONE follow-up message that contains:

1. The recommendation one-liner: "Recommendation: `<runtime>` + `<deployment model>`, model `<model>`"
2. Gate 2 via AskUserQuestion:

> "Do you want a deployable proof-of-concept for this recommendation? I'll generate the
> agent code, deployment plan, and scripts."
>
> - **Yes** → set `phases.poc = "in_progress"`, load `references/phases/poc/poc.md`
> - **No** → set `phases.poc = "skipped"` — flow complete

Gate 2 is asked for ANY winning runtime (agentcore / ecs / eks / lambda /
lambda_microvms) — the POC shape follows the verdict (poc.md Step 3 dispatch).

## Failure handling

If any phase fails mid-execution (error in a tool call, user aborts): keep all previously
written artifacts, set `phases.migration_plan = "in_progress"` (resumable — re-entering
this phase checks `$MIGRATION_DIR/.phase-status.json` and resumes from the last completed
phase). Then, by entry point:

- `build_deploy`: offer Gate 2 with the fallback clearly labeled — POC from `design.json`
  only, not plan-backed.
- `migrate`: no fallback POC. Offer to resume the migration plan later, or end with
  Stage 1 outputs + `handoff-summary.md`.
