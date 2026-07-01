---
name: heroku-to-aws
description: "Migrate workloads from Heroku to AWS. Triggers on: migrate from Heroku, Heroku to AWS, move off Heroku, migrate Heroku app, migrate Heroku Postgres to RDS, migrate Heroku Redis to ElastiCache, migrate Heroku Kafka to MSK, migrate dynos to Elastic Beanstalk, migrate dynos to Fargate, Heroku migration, move from Heroku to AWS, migrate Heroku Private Space, Heroku to Elastic Beanstalk, Heroku to ECS, Heroku to Fargate, leave Heroku, migrate off Heroku platform. Runs a 6-phase process: discover Heroku resources from Terraform files, Procfile/app.json, and optional billing exports, clarify migration requirements, design AWS architecture, estimate costs, generate migration artifacts, and collect optional feedback. Clarify must finish before Design, Estimate, or Generate. Uses a flat resource model (no clustering or dependency graphs) with deterministic mapping tables for core services (Dynos → Elastic Beanstalk, Postgres → RDS/Aurora, Redis → ElastiCache, Kafka → MSK) and a fast-path table for 13+ common add-ons. Cedar/Fir generation detection is detect-only in v1. Pipeline/Review Apps are detect-only. Do not use for: GCP or Azure migrations to AWS, AWS-to-Heroku reverse migration, general AWS architecture advice without migration intent, Heroku-to-Heroku refactoring, or multi-cloud deployments that do not involve migrating off Heroku."
---

# Heroku-to-AWS Migration Skill

## Philosophy

- **Full platform exit by default**: Heroku is in sustaining engineering (KTLO) — stability and support only, no new investment. Enterprise contracts are no longer sold to new customers. This skill assumes complete departure from Heroku (compute, data, and add-ons) within a user-defined window. Do not recommend indefinite continued use of Heroku.
- **PaaS-to-PaaS by default**: Elastic Beanstalk (Docker platform, AL2023) is the default compute target — it preserves Heroku's managed platform model (push code, platform handles builds/deploys/scaling/patching). Fargate and EKS are available as overrides for users who want direct container control or Kubernetes orchestration. Do not recommend AWS App Runner (no longer accepting new customers as of April 2026).
- **Interim cutover is bounded**: If a user chooses data-first migration (database on AWS, app temporarily on Heroku), treat this as a bounded phase (weeks, not quarters). Require a target exit date and surface KTLO platform risk warnings.
- **Re-platform by default**: Select AWS services that match Heroku workload types (e.g., Dynos → Elastic Beanstalk, Heroku Postgres → RDS/Aurora, Heroku Redis → ElastiCache, Kafka → MSK).
- **Dev sizing unless specified**: Default to development-tier capacity (e.g., db.t4g.micro, single AZ). Upgrade only on user direction.
- **No human one-time migration costs**: Do not present human labor, professional services, or people-time work as dollar estimates or "one-time migration cost" budget categories. Vendor charges grounded in data (for example Heroku invoice line items in the infra estimate when billing exists) are allowed.
- **Terraform + repo as primary discovery**: Terraform files (`.tf` with `heroku_*` resources) and repo artifacts (Procfile, app.json) are the primary data sources for resource discovery. No Platform API calls in v1.
- **Flat resource model**: Heroku resources are organized per-app without dependency graphs or clustering. No topological sorting, typed edges, or cluster formation logic. Resources are processed as a flat list in input order.
- **Deterministic mappings**: Core services use fixed lookup tables (Dyno Type Table, Postgres Plan Table, Redis Plan Table, Kafka Plan Table). Common add-ons use the Fast-Path Table. Unknown add-ons hit the specialist gate.
- **DMS has Heroku constraints**: AWS DMS cannot perform continuous replication (CDC) with Heroku Postgres because Heroku does not grant the REPLICATION role. DMS is for one-time bulk migration with a cutover window only. The skill must surface this constraint when DMS is selected.

---

## Definitions

- **"Load"** = Read the file using the Read tool and follow its instructions. Do not summarize or skip sections.
- **`$MIGRATION_DIR`** = The run-specific directory under `.migration/` (e.g., `.migration/0315-1030/`). Set during Phase 1 (Discover).

---

## Phase Structure (frontmatter)

A phase orchestrator file (e.g. `references/phases/discover/discover.md`) may carry a small YAML frontmatter block that names how the phase is composed — its inputs, the **fragments** it runs (each with a trigger), the **assembler** that combines their outputs, what it produces, and what it requires/advances-to. `INTERPRETER.md` is the contract: it lists every frontmatter key and how to act on it (including `_init`, which establishes migration state on the first phase).

**Fragment vs assembler:** a **fragment** does one unit of work and writes its own contribution; fragments are independent (none reads another's output). The **assembler** runs last and combines/validates the fragments' outputs into the phase's final artifact. A phase has 1..N fragments and exactly one assembler.

When a phase file has frontmatter, read it (and `INTERPRETER.md`) first, then execute the phase body. Frontmatter is being introduced phase-by-phase; phases without it run from their prose as before.

---

## Context Loading Rules

Each phase loads reference files on demand. To keep per-turn context manageable and prevent instruction-following degradation:

- **Budget:** Each phase should load no more than ~800 lines of instructions (excluding user artifacts like JSON profiles and MCP tool results).
- **Conditional loading:** Reference files with trigger conditions MUST NOT be loaded unless the condition is met. Do not speculatively load files.
- **No duplication:** Mapping tables, pricing data, and shared warnings exist in one canonical file. Other files reference them; they do not copy them inline.
- **Progressive depth:** Phase orchestrators (`design.md`, `generate.md`) contain short routing logic that points to detailed sub-files. Load the sub-file only when its path is selected.

**Conditional reference files (load ONLY when condition is true):**

| File                                       | Condition                                                    |
| ------------------------------------------ | ------------------------------------------------------------ |
| `design-refs/postgres-plan-table.md`       | Inventory contains `addon:*:heroku-postgresql:*` resources   |
| `design-refs/redis-plan-table.md`          | Inventory contains `addon:*:heroku-redis:*` resources        |
| `design-refs/kafka-plan-table.md`          | Inventory contains `addon:*:heroku-kafka:*` resources        |
| `references/phases/clarify/clarify.md` Q11 | `heroku_generation == "fir"` detected in any inventory entry |

When adding new reference files, verify the phase's total loaded instructions remain under budget. If a new file would exceed ~800 lines when combined with other loaded refs, split it or make it conditional.

---

## Prerequisites

User must provide:

- **Terraform IaC** (REQUIRED): `.tf` files containing `heroku_*` resource types (primary and required discovery path)
- **Repo artifacts** (SUPPLEMENTARY): Procfile and/or app.json in the workspace (supplements Terraform with commands, buildpacks, and declared add-ons — cannot stand alone)
- **Billing data** (OPTIONAL): Heroku Dashboard invoices or Enterprise CSV billing exports (for cost comparison)

If no Terraform files with `heroku_*` resources are found, stop and ask user to provide Heroku Terraform files. Procfile and app.json alone are not sufficient for discovery.

**Note:** Platform API discovery is NOT supported in v1. No API token is required or used.

---

## State Machine

This is the execution controller. After completing each phase, consult this table to determine the next action.

| Current State | Condition                                                             | Next Action                                                                            |
| ------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `discover`    | `phases.discover != "completed"`                                      | Load `references/phases/discover/discover.md`                                          |
| `clarify`     | `phases.discover == "completed"` AND `phases.clarify != "completed"`  | Load `references/phases/clarify/clarify.md`                                            |
| `design`      | `phases.clarify == "completed"` AND `phases.design != "completed"`    | Load `references/phases/design/design.md`                                              |
| `estimate`    | `phases.design == "completed"` AND `phases.estimate != "completed"`   | Load `references/phases/estimate/estimate.md`                                          |
| `generate`    | `phases.estimate == "completed"` AND `phases.generate != "completed"` | Load `references/phases/generate/generate.md`                                          |
| `complete`    | `phases.generate == "completed"` AND `phases.feedback == "pending"`   | Set `phases.feedback` to `"completed"` (user had two chances), then migration complete |
| `complete`    | `phases.generate == "completed"` AND `phases.feedback == "completed"` | Migration planning complete                                                            |

**How to determine current state (deterministic):**

1. Read `$MIGRATION_DIR/.phase-status.json`
2. If `current_phase` exists, use it (must match one of: discover, clarify, design, estimate, generate, complete)
3. Otherwise use ordered phase evaluation: `discover` → `clarify` → `design` → `estimate` → `generate`
4. Pick the **first** phase in that order where `phases.<phase> != "completed"`; if none, state is `complete`

**Phase gate checks**: If prior phase incomplete, do not advance (e.g., cannot enter estimate without completed design).

**Clarify is mandatory:** Do not load `references/phases/design/design.md`, `references/phases/estimate/estimate.md`, or `references/phases/generate/generate.md` unless `$MIGRATION_DIR/.phase-status.json` exists and `phases.clarify` is exactly `"completed"`. A `preferences.json` file alone is **not** sufficient proof that Clarify ran. If the user asks to skip Clarify or jump straight to Design, cost estimate, or artifact generation, refuse briefly, then load `references/phases/clarify/clarify.md` and run Phase 2. There is no exception for "quick" or "obvious" migrations.

**Feedback checkpoints**: Feedback is offered once after Estimate (combined with plan sharing). See the **Feedback Checkpoints** section below for details.

### Handoff Gate Orchestration (Fail Closed)

Load `references/shared/handoff-gates.md` when executing any phase completion step.

1. **Single `$MIGRATION_DIR`**: Use one run directory for the entire migration. Do not mix artifacts across `.migration/*/` sessions.
2. **Re-read from disk**: Before each phase (and before each handoff gate), Read required artifacts from `$MIGRATION_DIR/`. Do not rely on chat memory.
3. **Advance only on `HANDOFF_OK`**: A phase is complete only when its orchestrator emits `HANDOFF_OK | phase=<name> | artifacts=...`. Do not load the next phase without it.
4. **On `GATE_FAIL`**: Output the failure line(s) to the user in plain language. **Do NOT modify artifacts** to pass the gate. **Do NOT continue** to the next phase. Tell the user which phase to re-run.
5. **Re-entry**: Re-running an earlier phase after downstream phases completed requires explicit user confirmation; downstream phases must be reset to `"pending"`. See `handoff-gates.md` re-entry table.

Generate phase additionally loads `references/shared/validate-artifacts.md` before writing `migration-report.html`.

---

## State Validation

When reading `$MIGRATION_DIR/.phase-status.json`, validate before proceeding:

1. **Multiple sessions**: If multiple directories exist under `.migration/`, list them with their phase status and ask: [A] Resume latest, [B] Start fresh, [C] Cancel.
2. **Invalid JSON**: If `.phase-status.json` fails to parse, STOP. Output: "State file corrupted (invalid JSON). Delete the file and restart the current phase."
3. **Unrecognized phase**: If `phases` object contains a phase not in {discover, clarify, design, estimate, generate, feedback}, STOP. Output: "Unrecognized phase: [value]. Valid phases: discover, clarify, design, estimate, generate, feedback."
4. **Unrecognized status**: If any `phases.*` value is not in {pending, in_progress, completed}, STOP. Output: "Unrecognized status: [value]. Valid values: pending, in_progress, completed."
5. **Invalid `current_phase`** (if present): If `current_phase` is not in {discover, clarify, design, estimate, generate, complete}, STOP. Output: "Unrecognized current_phase: [value]. Valid values: discover, clarify, design, estimate, generate, complete."
6. **Out-of-order completion**: For ordered phases [discover, clarify, design, estimate, generate], if any later phase is `"completed"` while an earlier phase is not `"completed"`, STOP. Output: "Inconsistent phase ordering detected. Reconcile `.phase-status.json` before resuming."
7. **Multiple active phases**: Across core phases {discover, clarify, design, estimate, generate}, at most one phase may be `"in_progress"`. If >1, STOP. Output: "Multiple phases are in_progress. Keep only one active phase before resuming."

---

## State Management

Migration state lives in `$MIGRATION_DIR` (`.migration/[MMDD-HHMM]/`), created by Phase 1 and persisted across invocations.

**.phase-status.json schema:**

```json
{
  "migration_id": "0315-1030",
  "last_updated": "2026-03-15T10:30:00Z",
  "current_phase": "discover",
  "phases": {
    "discover": "in_progress",
    "clarify": "pending",
    "design": "pending",
    "estimate": "pending",
    "generate": "pending",
    "feedback": "pending"
  }
}
```

**Status values:** `"pending"` → `"in_progress"` → `"completed"`. Never goes backward.
For core phases (discover, clarify, design, estimate, generate), at most one phase may be `"in_progress"` at any time.
`current_phase` is optional but recommended; when present it is authoritative.

The `.migration/` directory is automatically protected by a `.gitignore` file created in Phase 1.

### Phase Status Update Protocol

Use **read-merge-write** updates for `.phase-status.json`:

1. Read the current file before every update.
2. Change only the phase keys being advanced and `last_updated`.
3. Keep prior completed phases unchanged.
4. Set `current_phase` to the next deterministic phase (or `complete` after generate).
5. Write the full file in the same turn as your final phase work message.

---

## Phase Summary Table

| Phase        | Inputs                                                                                           | Outputs                                                                                                                                               | Reference                                |
| ------------ | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| **Discover** | Terraform files with `heroku_*` resources, Procfile, app.json, and/or billing exports            | `heroku-resource-inventory.json`, `.phase-status.json` updated                                                                                        | `references/phases/discover/discover.md` |
| **Clarify**  | `heroku-resource-inventory.json`                                                                 | `preferences.json`, `.phase-status.json` updated                                                                                                      | `references/phases/clarify/clarify.md`   |
| **Design**   | `heroku-resource-inventory.json`, `preferences.json`                                             | `aws-design.json`                                                                                                                                     | `references/phases/design/design.md`     |
| **Estimate** | `aws-design.json`, `preferences.json`, optional billing profile                                  | `estimation-infra.json`, `.phase-status.json` updated                                                                                                 | `references/phases/estimate/estimate.md` |
| **Generate** | `aws-design.json`, `estimation-infra.json`, `preferences.json`, `heroku-resource-inventory.json` | `terraform/`, `MIGRATION_GUIDE.md`, `README.md`, database migration scripts, `generation-warnings.json` (if applicable), `.phase-status.json` updated | `references/phases/generate/generate.md` |
| **Feedback** | `.phase-status.json` (discover completed minimum), all existing migration artifacts              | `feedback.json`, `.phase-status.json` updated                                                                                                         | `references/phases/feedback/feedback.md` |

---

## MCP Servers

**awspricing** (for cost estimation):

- Provides `get_pricing`, `get_pricing_service_codes`, `get_pricing_service_attributes` tools
- Only needed during Estimate phase. Discover and Design do not require it.
- Primary pricing source: `shared/pricing/aws-infra-pricing.json` (cached AWS infrastructure rates, ±5-10% for infrastructure). MCP is secondary — used only for services not found in the pricing file.

---

## Files in This Skill

```
heroku-to-aws/
├── SKILL.md                                    ← You are here (orchestrator + state machine)
│
├── references/
│   ├── phases/
│   │   ├── discover/
│   │   │   ├── discover.md                     # Phase 1: Discover orchestrator
│   │   │   ├── discover-terraform.md           # Terraform discovery (primary)
│   │   │   └── discover-billing.md             # Billing data parsing
│   │   ├── clarify/
│   │   │   └── clarify.md                      # Phase 2: Adaptive questions (12–15, batched ≤5)
│   │   ├── design/
│   │   │   └── design.md                       # Phase 3: Design orchestrator (flat single-pass mapping)
│   │   ├── estimate/
│   │   │   └── estimate.md                     # Phase 4: Cost projection
│   │   ├── generate/
│   │   │   ├── generate.md                     # Phase 5: Generate orchestrator
│   │   │   ├── generate-terraform.md           # Terraform configurations
│   │   │   └── generate-docs.md                # MIGRATION_GUIDE.md + README.md
│   │   └── feedback/
│   │       └── feedback.md                     # Phase 6: Feedback collection (reuses shared)
│   │
│   ├── design-refs/
│   │   ├── fast-path-table.md                  # Add-on → AWS deterministic mappings (13+ entries)
│   │   ├── dyno-type-table.md                  # Dyno type → Fargate CPU/memory (Fargate override path only)
│   │   ├── postgres-plan-table.md              # Postgres plan → RDS/Aurora sizing
│   │   ├── redis-plan-table.md                 # Redis plan → ElastiCache sizing
│   │   └── kafka-plan-table.md                 # Kafka plan → MSK sizing
│   │
│   └── shared/                                 # References shared plugin infrastructure
│       └── (path reference to ../gcp-to-aws/references/shared/)
│           ├── handoff-gates.md                # Fail-closed phase handoff protocol
│           ├── schema-phase-status.md          # .phase-status.json schema
│           ├── migration-complexity.md         # Complexity tier definitions (Small/Medium/Large)
│           ├── schema-estimate-infra.md        # estimation-infra.json schema
│           └── validate-artifacts.md           # Pre-report validation
```

| Condition                                                | Action                                                                                                                                                        |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No Terraform files with `heroku_*` resources found       | Stop. Output: "No Terraform files with heroku_* resources found. Heroku Terraform is required for discovery. Procfile and app.json alone are not sufficient." |
| `.phase-status.json` missing phase gate                  | Stop. Output: "Cannot enter Phase X: Phase Y-1 not completed. Start from Phase Y or resume Phase Y-1."                                                        |
| awspricing unavailable after 3 attempts                  | Display user warning about ±5-10% accuracy. Use `shared/pricing/aws-infra-pricing.json`. Add `pricing_source: "cached_fallback"` to `estimation-infra.json`.  |
| User skips questions or says "use defaults for the rest" | Apply documented defaults for remaining questions. Phase 2 completes either way.                                                                              |
| Dyno type not in sizing table (EB or Fargate path)       | Reject mapping for that formation. Output: "Unsupported dyno type: {type}. Cannot map to target compute service."                                             |
| Add-on not in Fast-Path Table                            | Mark as "Deferred — specialist engagement". No automated mapping produced.                                                                                    |

## Defaults

- **IaC output**: Terraform configurations, migration scripts, and documentation
- **Region**: `us-east-1` (unless user specifies otherwise)
- **Sizing**: Development tier (e.g., `db.t4g.micro` for databases, 0.5 CPU for Fargate)
- **Migration mode**: Adapts based on available inputs (Terraform primary, Procfile/app.json supplementary, billing optional)
- **Cost currency**: USD
- **Timeline assumption**: 2-16 weeks depending on migration complexity — small (2-6 weeks), medium (6-12 weeks), large (12-18 weeks). See `references/shared/migration-complexity.md` for tier definitions.

## Workflow Execution

When invoked, the agent **MUST follow this exact sequence**:

1. **Load phase status**: Read `.phase-status.json` from `.migration/*/`.
   - If missing: Initialize for Phase 1 (Discover)
   - If exists: Determine current phase using deterministic rules in **State Machine**

2. **Determine phase to execute**:
   - If `current_phase` exists: execute that phase.
   - Otherwise execute the first non-completed phase in ordered list: discover → clarify → design → estimate → generate.
   - If all ordered phases are completed: migration is complete (with feedback finalization rule).

3. **Read phase reference**: Load the full reference file for the target phase.

4. **Execute ALL steps in order**: Follow every numbered step in the reference file. **Do not skip, optimize, or deviate.**

5. **Validate outputs**: Confirm all required output files exist with correct schema before proceeding. Phase orchestrators run **Completion Handoff Gate** checks per `shared/handoff-gates.md`.

6. **Handoff gate**: Emit `HANDOFF_OK` or `GATE_FAIL` per `shared/handoff-gates.md`. On `GATE_FAIL`, stop — do not update phase status or load the next phase.

7. **Update phase status**: Only after `HANDOFF_OK`. Use the Phase Status Update Protocol (read-merge-write) in the same turn as the phase's final output message.

8. **Feedback and sharing checkpoints**: After Estimate completes, offer feedback and/or plan sharing. This runs **before** advancing to Generate.

   - **After Discover**: No prompt. Proceed directly to Clarify.

   - **After Estimate** (if `phases.feedback` is `"pending"`): Output to user:

     ```
     ─── Share Your Migration Plan ───

     This link encodes your migration profile for partner matching:
     ✓ Included: Clarify answers, estimated costs, recommendation path,
       detected Heroku services, resource names, and workload types.
     ✗ Excluded: Source code, local file paths, credentials, API tokens,
       config-var values, and environment secrets.

     The link uses a URL fragment (#) — no data is sent to any server
     when you click it. The landing page decodes everything client-side.

     [A] Send feedback & share plan
     [B] Send feedback only
     [C] No thanks, continue to Generate
     ```

     - If user picks **A** → Load `references/phases/feedback/feedback.md`, execute it. Then generate share link. Set `phases.feedback` to `"completed"`. Continue to Generate.
     - If user picks **B** → Load `references/phases/feedback/feedback.md`, execute it. Set `phases.feedback` to `"completed"`. Continue to Generate.
     - If user picks **C** → Set `phases.feedback` to `"completed"`. Continue to Generate.

   - **After Generate**: Share-only prompt (no feedback re-ask):

     ```
     ─── Share Your Completed Plan ───

     This link encodes your migration profile for partner matching:
     ✓ Included: Clarify answers, estimated costs, recommendation path,
       detected Heroku services, resource names, and workload types.
     ✗ Excluded: Source code, local file paths, credentials, API tokens,
       config-var values, and environment secrets.

     The link uses a URL fragment (#) — no data is sent to any server
     when you click it. The landing page decodes everything client-side.

     [A] Share completed plan
     [B] No thanks, finish
     ```

     - If user picks **A** → Generate share link. Mark migration complete.
     - If user picks **B** → Mark migration complete.
     - If `phases.feedback` is still `"pending"`, set it to `"completed"` regardless of choice.

9. **Display summary**: Show user what was accomplished, highlight next phase, or confirm migration completion.

**Critical constraint**: Agent must strictly adhere to the reference file's workflow. If unable to complete a step, stop and report the specific issue. Do not fabricate or infer data.
