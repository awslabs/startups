---
_phase: estimate
_title: "Estimate AWS Costs"
_requires_phase: design
_input:
  - aws-design.json
  - preferences.json
  - heroku-resource-inventory.json
_fragments:
  - _id: cost-engine
    _trigger: { _always: true }
    _file: phases/estimate/estimate-cost-engine.md
_assemble:
  _file: phases/estimate/estimate-assemble.md
_produces:
  - estimation-infra.json
_advances_to: generate
_re_entry_guard:
  _stale_if_completed: generate
  _stale_artifact: generation-warnings.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
---

# Phase 4: Estimate AWS Costs

> Loaded by SKILL.md when `phases.design == "completed"` AND `phases.estimate != "completed"`.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Overview

Calculate projected monthly AWS costs for the designed Heroku-to-AWS architecture. Produce `estimation-infra.json` conforming to `shared/schema-estimate-infra.md`. Classify migration complexity using `shared/migration-complexity.md`.

**Inputs:**

- `$MIGRATION_DIR/aws-design.json` (from Phase 3)
- `$MIGRATION_DIR/preferences.json` (from Phase 2)
- `$MIGRATION_DIR/heroku-resource-inventory.json` (from Phase 1 — for billing profile)

**Outputs:**

- `$MIGRATION_DIR/estimation-infra.json`
- `.phase-status.json` updated (estimate → completed)

---

## Sub-Files

- **estimate-cost-engine.md** → the cost engine: pricing-mode selection, prerequisites, and the full calculation (current Heroku costs, projected AWS costs + tiers, observability, comparison, ROI, optimization opportunities, complexity tier, recommendation) plus the MCP pricing recipes.
- **estimate-assemble.md** → the assembler: assembles + writes `estimation-infra.json`, runs the completion handoff gate (incl. the Property-16 total invariant), updates `.phase-status.json`, and presents the summary.

---

## Step 1: Compute the Estimate

Load `references/phases/estimate/estimate-cost-engine.md` and follow it. It selects the
pricing mode, validates the design inputs, and computes the entire financial picture.

---

## Step 2: Assemble and Validate

Load `references/phases/estimate/estimate-assemble.md` (the phase's assembler) and
follow it to write the final `estimation-infra.json`, run the completion handoff gate,
update `.phase-status.json`, and present the summary. It owns the artifact-level
contract for this phase.

---

## Scope Boundary

**This phase covers financial analysis ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Changes to architecture mappings from Phase 3 (Design)
- Execution timelines or migration schedules (beyond tier classification)
- Terraform or IaC code generation
- Detailed migration procedures or runbooks
- Team staffing, human labor costs, or professional services fees
- AI workload estimation (not applicable to Heroku migrations)

**Your ONLY job: Show the financial picture of moving from Heroku to AWS. Nothing else.**
