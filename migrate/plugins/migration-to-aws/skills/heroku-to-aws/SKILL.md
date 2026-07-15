---
name: heroku-to-aws
description: "Migrate workloads from Heroku to AWS. Triggers on: migrate from Heroku, Heroku to AWS, move off Heroku, migrate Heroku app, migrate Heroku Postgres to RDS, migrate Heroku Redis to ElastiCache, migrate Heroku Kafka to MSK, migrate dynos to Elastic Beanstalk, migrate dynos to Fargate, Heroku migration, move from Heroku to AWS, migrate Heroku Private Space, Heroku to Elastic Beanstalk, Heroku to ECS, Heroku to Fargate, leave Heroku, migrate off Heroku platform. Runs a 6-phase process: discover Heroku resources from Terraform files, Procfile/app.json, and optional billing exports, clarify migration requirements, design AWS architecture, estimate costs, generate migration artifacts, and collect optional feedback. Clarify must finish before Design, Estimate, or Generate. Uses a flat resource model (no clustering or dependency graphs) with deterministic mapping tables for core services (Dynos → Elastic Beanstalk by default, Postgres → RDS/Aurora, Redis → ElastiCache, Kafka → MSK) and a fast-path table for 13+ common add-ons. Cedar/Fir generation detection is detect-only in v1. Pipeline/Review Apps are detect-only. Do not use for: GCP or Azure migrations to AWS, AWS-to-Heroku reverse migration, general AWS architecture advice without migration intent, Heroku-to-Heroku refactoring, or multi-cloud deployments that do not involve migrating off Heroku."
---

# Heroku-to-AWS Migration Skill

## Philosophy

- **Full platform exit by default**: Heroku is in sustaining engineering (KTLO) — stability and support only, no new investment. Enterprise contracts are no longer sold to new customers. This skill assumes complete departure from Heroku (compute, data, and add-ons) within a user-defined window. Do not recommend indefinite continued use of Heroku.
- **PaaS-to-PaaS by default, recommendation-shaped**: Elastic Beanstalk (Docker platform, AL2023) is the default compute target because it preserves Heroku's managed platform model (source deployment, platform-managed environments, and lower operational burden than direct container orchestration). Clarify presents a per-formation compute recommendation before asking for confirmation. Fargate remains the override for direct container control and is used automatically for horizontally scaled non-web processes that EB SingleInstance cannot preserve; EKS remains the override for teams with Kubernetes expertise. ECS Express Mode may be mentioned only as a forward-look for the Fargate override path, not as a replacement for the EB default. Do not recommend AWS App Runner (no longer accepting new customers as of April 2026).
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

Phase and unit files carry a YAML frontmatter block that declares how the phase is
composed — its inputs, the fragments it runs, the assembler that combines them,
what it produces, its gates, and what it requires/advances-to. The DSL interpreter
contract is the vendored `references/vendored/dsl/INTERPRETER.md`: it defines every
frontmatter key, the fragment/assembler model, and the interpreter loop. **Load it
first** (once, at the start of a migration), then execute a phase file's prose
body. Elsewhere in this skill, `INTERPRETER.md` (without a path) refers to this
same loaded contract.

Frontmatter is being introduced phase-by-phase; a phase file without it runs from
its prose as before.

---

## Context Loading Rules

Each phase loads reference files on demand. To keep per-turn context manageable and prevent instruction-following degradation:

- **Budget:** Each phase should load no more than ~800 lines of instructions (excluding user artifacts like JSON profiles and MCP tool results).
- **Conditional loading:** Reference files with trigger conditions MUST NOT be loaded unless the condition is met. Do not speculatively load files.
- **No duplication:** Mapping tables, pricing data, and shared warnings exist in one canonical file. Other files reference them; they do not copy them inline.
- **Progressive depth:** Phase orchestrators (`design.md`, `generate.md`) contain short routing logic that points to detailed sub-files. Load the sub-file only when its path is selected.

Each phase declares its own conditional reference/knowledge loads in frontmatter (a fragment `_trigger` or a `_knowledge` entry's `_when`); do not maintain a separate load-condition table here.

When adding new reference files, verify the phase's total loaded instructions remain under budget. If a new file would exceed ~800 lines when combined with other loaded refs, split it or make it conditional.

---

## Execution

This skill is driven by the interpreter loop in `INTERPRETER.md` (§ The interpreter
loop): it reads `.phase-status.json`, determines the current phase, runs each
phase's `_preconditions` / fragments / `_assemble` / `_postconditions`, advances on
`HANDOFF_OK` via `_advances_to`, and validates state. The phase set, ordering, and
gates are all derived from the phase files' frontmatter and `INTERPRETER.md` — they
are not restated here.

**Cold start (entry phase).** On a cold start — no `.migration/` run with a
`.phase-status.json` yet — begin at `references/phases/discover/discover.md`, this
skill's entry phase (the one carrying `_init: true`). The interpreter loads THIS
phase directly; it does not scan every phase's frontmatter to discover the root.
All subsequent phases are reached by following each phase's `_advances_to`. On a
warm start, `current_phase` in `.phase-status.json` is authoritative (see
`INTERPRETER.md` § The interpreter loop).

**Clarify is mandatory (heroku policy).** Do not skip Clarify or jump straight to
Design, Estimate, or Generate even if the user asks — there is no exception for
"quick" or "obvious" migrations. A `preferences.json` that was not produced by an
actual Clarify run does not count. If asked to skip, refuse briefly and run
Clarify.

---

## State Management

Migration state lives in `$MIGRATION_DIR` (`.migration/[MMDD-HHMM]/`), created on
the first phase and persisted across invocations. The state file is
`.phase-status.json`; its shape is defined by
`references/vendored/state/phase-status.schema.json`, and how it is created, validated, and
updated across the lifecycle is defined in `INTERPRETER.md` § The interpreter loop.
The `.migration/` directory is protected by a `.gitignore` created at init.

---

## MCP Servers

**awspricing** (for cost estimation):

- Provides `get_pricing`, `get_pricing_service_codes`, `get_pricing_service_attributes` tools
- Only needed during Estimate phase. Discover and Design do not require it.
- Primary pricing source: `references/vendored/pricing/aws-infra-pricing.json` (cached AWS infrastructure rates, ±5-10% for infrastructure). MCP is secondary — used only for services not found in the pricing file.

---

## Files in This Skill

```
heroku-to-aws/
├── SKILL.md                                    ← You are here (skill entry point)
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
│   └── shared/                                 # heroku-to-aws's own shared references
│           ├── README.md                       # what lives here + pointers to plugin-neutral shared data
│           ├── heroku-pricing-cache.md          # Heroku plan pricing (source-side baseline)
│           └── schema-discover-heroku.md        # heroku-resource-inventory.json schema
│
├── knowledge/design/                          # design lookup DATA (pure data, referenced by
│   │                                           #  design.md _knowledge, gated per _when)
│   ├── dyno-eb-sizing.json                     # Dyno type → Elastic Beanstalk EC2 instance type
│   ├── dyno-fargate-sizing.json                # Dyno type → Fargate CPU/memory
│   ├── eks-pod-sizing.json                     # Dyno type → EKS pod sizing + node selection
│   ├── postgres-rds-sizing.json                # Postgres plan → RDS/Aurora sizing
│   ├── redis-elasticache-sizing.json           # Redis plan → ElastiCache sizing
│   ├── kafka-msk-sizing.json                   # Kafka plan → MSK sizing
│   └── fast-path-addons.json                   # Add-on → AWS deterministic mappings (13+ entries)
```

| Condition                                                | Action                                                                                                                                                                    |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.phase-status.json` missing phase gate                  | Stop. Output: "Cannot enter Phase X: Phase Y-1 not completed. Start from Phase Y or resume Phase Y-1."                                                                    |
| awspricing unavailable after 3 attempts                  | Display user warning about ±5-10% accuracy. Use `references/vendored/pricing/aws-infra-pricing.json`. Add `pricing_source: "cached_fallback"` to `estimation-infra.json`. |
| User skips questions or says "use defaults for the rest" | Apply documented defaults for remaining questions. Phase 2 completes either way.                                                                                          |
| Dyno type not in selected compute sizing table           | Reject mapping for that formation. Output: "Unsupported dyno type: {type}. Cannot map to target compute service."                                                         |
| Add-on not in Fast-Path Table                            | Mark as "Deferred — specialist engagement". No automated mapping produced.                                                                                                |

## Defaults

- **IaC output**: Terraform configurations, migration scripts, and documentation
- **Region**: `us-east-1` (unless user specifies otherwise)
- **Sizing**: Development tier (e.g., `db.t4g.micro` for databases, 0.5 CPU for Fargate)
- **Migration mode**: Adapts based on available inputs (Terraform primary, Procfile/app.json supplementary, billing optional)
- **Cost currency**: USD
- **Timeline assumption**: 2-16 weeks depending on migration complexity — small (2-6 weeks), medium (6-12 weeks), large (12-18 weeks). Complexity tiers are classified per `references/vendored/estimate/complexity-tiers.json`.

## Feedback & Sharing Checkpoints

The interpreter loop (`INTERPRETER.md` § The interpreter loop) drives phase
sequencing, gates, and state. This section defines only the heroku-specific
checkpoint orchestration: WHERE the optional `feedback` checkpoint and plan-share
are offered (a checkpoint's placement is orchestration prose, not part of the
phase contract).

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

**Critical constraint**: Follow each phase reference file's workflow exactly. If unable to complete a step, stop and report the specific issue. Do not fabricate or infer data.
