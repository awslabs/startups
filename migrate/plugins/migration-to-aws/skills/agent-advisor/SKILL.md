---
name: agent-advisor
description: "Unified entry point for AI-agent work on AWS: evaluate and pick a runtime, generate a full migration plan (for existing workloads), and build an executable POC — all in one flow. Triggers on: which runtime for my agent, AgentCore vs ECS vs EKS vs Lambda, AgentCore vs Lambda MicroVMs, deploy an AI agent on AWS, agent architecture on AWS, I have an agent idea what do I build, move my agents to AWS, migrate my agents to AWS with a plan, agent migration plan, add AgentCore services, add memory/gateway/identity/policy to my agent, enable AgentCore Memory, add observability to my agent, I'm already on AWS and want to add agent capabilities, migrate Temporal workers to AWS, Temporal to AWS, run Temporal on AWS, Temporal workers on AWS, we use Temporal and want to move to AWS, our service is orchestrated by Temporal, what do I build on AWS for my Temporal workers, move a Temporal-based service to AWS, Temporal Cloud or self-hosted on AWS. Runs a phased flow: Intake (entry point + technical background), Discover (lightweight code detection), Clarify (adaptive questions), deterministic scoring, Design (runtime + deployment model + services + model), Estimate (coarse cost), Generate (layered recommendation doc + scaffolding), then optional gated stages: Migration Plan (full plan generated in-skill by reusing this plugin's gcp-to-aws engine, with the advisor's decisions carried over) and POC (deployment plan + deployable proof-of-concept on the recommended runtime — AgentCore, ECS, EKS, or Lambda; generated deliverables by default, or assisted build in your account on explicit opt-in). An add-capabilities branch (for teams already running agents on AWS) recommends which AgentCore services to enable on any runtime — no runtime scoring. A temporal-worker branch moves Temporal Workers to AWS (ECS/EKS/Serverless Workers polling tier + per-Activity execution tier) without rewriting Workflow orchestration code — never a Step Functions translation. Not for: pure LLM SDK rewrite without agent architecture (use llm-to-bedrock) or detailed per-model pricing."
---

# AWS Agent Advisor

Helps startups decide how and where to run AI agents on AWS. Deterministic scoring
recommends a runtime; the conversation adapts to the user's technical background.

## Definitions

- **"Load"** = Read the file with the Read tool and follow it. Do not summarize or skip.
- **`$RUN_DIR`** = the run directory under `.agent-advisor/` (e.g. `.agent-advisor/0630-1430/`),
  created in Intake.
- **`$PLUGIN`** = `${CLAUDE_PLUGIN_ROOT}` (the installed plugin root). On Claude Code this token
  substitutes inline. **If `${CLAUDE_PLUGIN_ROOT}` does not resolve** (some Cursor/Codex builds,
  or a literal `${CLAUDE_PLUGIN_ROOT}` string showing up in a path error), fall back to the
  skill's own directory: this SKILL.md lives at `<plugin>/skills/agent-advisor/SKILL.md`, so the
  engine and its data are all inside this skill — scripts at `./scripts/...`, runtime profiles at
  `./references/runtimes/...`, and decision refs at `./references/decision-refs/...` relative to
  it. Prefer `${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/...`; use the relative fallback only when
  it fails to resolve.

## Prerequisites

- `uv` available (for scoring). Check: `uv --version`. If missing, tell the user to install
  it (`curl -LsSf https://astral.sh/uv/install.sh | sh`) and stop.

## Phase Structure (frontmatter)

Phase, fragment, and assembler files carry a YAML frontmatter block that declares how each
phase is composed — its inputs, triggers, fragments, assembler, artifacts, gates, and
ordering. The execution contract is the vendored `references/vendored/dsl/INTERPRETER.md`:
it defines every frontmatter key, the fragment/assembler model, the gate protocol
(`HANDOFF_OK` / `GATE_FAIL`), and the interpreter loop. **Load it first** (once, at the
start of a run), then execute each phase file's prose body. Elsewhere in this skill,
`INTERPRETER.md` (without a path) refers to this loaded contract.

## Execution

This skill is driven by the interpreter loop in `INTERPRETER.md` (§ The interpreter loop):
it reads `.phase-status.json`, determines the current phase, runs each phase's
`_preconditions` / fragments / `_assemble` / `_postconditions`, advances on `HANDOFF_OK`
via `_advances_to`, and validates state. The backbone (intake → discover → clarify →
confirm → design → estimate → generate → migration-plan → poc → complete) and the
three checkpoint branches (add-capabilities, temporal-worker, temporal-poc) are derived
from the phase files' frontmatter — they are not restated here.

**Cold start (entry phase).** With no run under `.agent-advisor/` carrying a
`.phase-status.json`, begin at `references/phases/intake/intake.md` — this skill's entry
phase (the one carrying `_init: true`). On a warm start, `current_phase` in
`.phase-status.json` is authoritative (`INTERPRETER.md` § The interpreter loop).

**Skill bindings (`INTERPRETER.md` § Skill bindings).** This skill declares:

- **Run root**: `.agent-advisor/` — `$RUN_DIR` is this skill's name for the run directory
  (`.agent-advisor/[MMDD-HHMM]/`). Intake's own prose performs the `_init` bootstrap.
- **State shape**: § State file below (advisor-specific keys such as `entry_point`,
  `audience`, `recommendation_reviewed`, `migration_plan_ctx`); the shared state schema is
  not vendored.
- **Resolved statuses**: `skipped` (routing resolved the phase without running it), plus
  `not_applicable` for `migration_plan` only.
- **Conditional backbone routing**: the entry-point routing below. When a routing rule
  marks a phase not-applicable, set it `skipped` and advance through its `_advances_to` in
  the same state write.

## Routing & gates (orchestration)

Checkpoint placement and conditional backbone routing are orchestration prose owned by
this file (`INTERPRETER.md` § Skill bindings, § Backbone vs checkpoint).

**Entry-point routing:**

- `build_scratch` → skip Discover; Clarify → Confirm → Design → Estimate → Generate → **Gate 2 → POC (if AgentCore)**. No migration plan (nothing existing to migrate).
- `build_deploy` → Discover (if code) → Clarify → Confirm → Design → Estimate → Generate → **Gate 1 → Migration Plan (if existing non-AWS AI workload detected and user confirms)** → **Gate 2 → POC (if AgentCore)**.
- `migrate` → Discover (if code) → Clarify → Confirm → Design → **(skip Estimate)** → Generate → **Gate 1 → Migration Plan (in-skill, reusing the sibling `gcp-to-aws` skill)** → **Gate 2 → POC (if AgentCore and the plan was produced)**. Declining Gate 1 keeps the classic handoff: pointer to `/migration-to-aws:llm-to-bedrock` with `handoff-summary.md`.
- `add_capabilities` → load `references/phases/add-capabilities/add-capabilities.md` and follow it (no runtime
  scoring; writes `capabilities-recommendation.md`). This is a self-contained branch — it does
  NOT pass through Clarify / Confirm / Design / Estimate / Generate, so the phase gate
  below never applies to it.
- `temporal_worker` → load `references/phases/temporal-worker/temporal-worker.md` and follow it (moves Temporal
  Workers to AWS; Workflow orchestration code untouched; writes `temporal-migration-plan.md`).
  Same self-contained-branch exemption as `add_capabilities`. Entered two ways: Intake detects a
  Temporal signal in the opening message and the user confirms, or Discover (under `migrate` /
  `build_deploy`) detects the Temporal SDK and the user accepts the offer — both persist
  `entry_point = temporal_worker` in `.phase-status.json` before loading the branch. If the user
  DECLINES Discover's offer, `temporal_branch_declined: true` is persisted and the normal flow
  continues; a resumed session must not re-offer the branch.

**Checkpoint re-entry order:** on resume, evaluate the `temporal_poc` trigger
(`phases.temporal_poc == "in_progress"`, set when the user answers Gate T "yes" —
temporal-worker.md Step 5.7) BEFORE the `temporal_worker` trigger, which would otherwise
swallow the route.

**Gate semantics (backbone tail):**

- **Gate 1 → `migration_plan`** runs only when `generate` is done AND
  `recommendation_reviewed == true` (generate.md Step 5.5) AND entry point ∈ {migrate,
  build_deploy} AND the run is migration-eligible (generate.md Step 6) AND the user
  confirmed Gate 1. Otherwise resolve it: `not_applicable` (build_scratch / no migratable
  workload) or `skipped` (declined) — and advance.
- **Gate 2 → `poc`** runs only when `phases.poc == "in_progress"` (set when the user
  answers Gate 2 "yes" — asked in generate.md Step 7 or migration-plan.md Step 6) AND
  `recommendation_reviewed == true`. Any winning runtime (agentcore / ecs / eks / lambda /
  lambda_microvms) — the POC shape follows the verdict (poc.md Step 3 dispatch on
  `references/decision-refs/poc-shapes.md`). Gate 2 is only offered when `migration_plan`
  ∈ {completed, skipped, not_applicable} — or `in_progress` on build_deploy only (Stage 2
  failed/aborted; fallback POC from design.json per migration-plan.md failure handling);
  for entry point `migrate`, only when `migration_plan == "completed"` (a migrate-POC
  without a plan has nothing to implement).
- Persisting Gate 2 as `phases.poc = "in_progress"` BEFORE poc.md loads makes the
  confirmation resumable: if the session breaks between the "yes" and the load, the
  interpreter re-enters `poc` without re-asking. (A declared deviation from
  `INTERPRETER.md` § The interpreter loop step 5's gate-then-`in_progress` ordering — the
  user's confirmation is the entry event worth persisting.)

**Phase gate:** Do NOT load design.md / estimate.md / generate.md unless
`$RUN_DIR/.phase-status.json` exists and BOTH `phases.clarify == "completed"` AND
`phases.confirm == "completed"`. Confirm confirms the deployment model, the service
set, and (for a co_recommend tie) the user's `chosen_runtime` — Design and the diagram depend on
its `confirm.json` output, so it must not be skipped. If the user asks to skip Clarify or Pass 2,
refuse briefly and run it.

## State file (`.phase-status.json`)

```json
{
  "run_id": "0630-1430",
  "entry_point": "build_scratch",
  "audience": "technical",
  "current_phase": "clarify",
  "phases": {
    "intake": "completed",
    "discover": "skipped",
    "clarify": "in_progress",
    "confirm": "pending",
    "design": "pending",
    "estimate": "pending",
    "generate": "pending",
    "migration_plan": "pending",
    "poc": "pending"
  }
}
```

Status values: `pending` → `in_progress` → `completed`, plus `skipped`. Use read-merge-write:
read before each update, change only the advancing keys, keep prior phases.

`recommendation_reviewed` (top level, boolean) is set to `true` by generate.md Step 5.5 when
the user explicitly confirms they have seen the recommendation. Gate 1, Gate 2, and the
`migration_plan` / `poc` states all require it — no gate may be asked while it is absent.

`migration_plan` additionally uses `not_applicable` (build_scratch, or no migratable workload
detected). When Stage 2 runs, `migration_plan_ctx` is added at the top level:
`{"repo": "<abs path to target repo>", "migration_dir": "<abs path to .migration/<id>/>"}` —
Stage 3 reads gcp-to-aws artifacts ONLY via this recorded path, never by re-globbing.

## Files

| File                                                   | Purpose                                                                 |
| ------------------------------------------------------ | ----------------------------------------------------------------------- |
| `references/vendored/dsl/INTERPRETER.md`               | Vendored DSL execution contract (interpreter loop + gate protocol)      |
| `references/phases/intake/intake.md`                   | Entry point + technical background + open context                       |
| `references/phases/discover/discover.md`               | Lightweight code detection                                              |
| `references/phases/clarify/clarify.md`                 | Clarify orchestrator + answer mapping to scoring keys                   |
| `references/phases/clarify/clarify-technical.md`       | Technical-background question wording                                   |
| `references/phases/clarify/clarify-business.md`        | Business-background question wording                                    |
| `references/phases/confirm/confirm.md`                 | Winner-specific follow-ups                                              |
| `references/phases/design/design.md`                   | Assemble recommendation; Migrate handoff branch                         |
| `references/phases/estimate/estimate.md`               | Coarse cost magnitude                                                   |
| `references/phases/generate/generate.md`               | Layered recommendation doc + scaffolding                                |
| `references/phases/migration-plan/migration-plan.md`   | Stage 2: full migration plan via the sibling gcp-to-aws engine          |
| `references/phases/temporal-worker/temporal-worker.md` | Temporal Worker migration branch (self-contained)                       |
| `references/phases/temporal-poc/temporal-poc.md`       | Temporal worker POC (Gate T): smoke worker + ECS Terraform              |
| `references/decision-refs/temporal.md`                 | Temporal branch source of truth: Tier 1/2 tables, runbooks, commercials |
| `references/decision-refs/poc-shapes.md`               | Per-runtime POC deploy shapes (ECS/EKS/Lambda/MicroVMs/Temporal)        |
| `references/decision-refs/*.md`                        | Runtime service cards, model defaults, freshness                        |
| `references/runtimes/*.json`                           | Runtime registry (read by scoring.py)                                   |
| `scripts/scoring.py`                                   | Deterministic scoring engine                                            |
| `scripts/test_temporal_decision_refs.py`               | Content lock for the Temporal decision reference                        |
| `scripts/test_poc_shapes.py`                           | Content lock for the POC deploy shapes                                  |
