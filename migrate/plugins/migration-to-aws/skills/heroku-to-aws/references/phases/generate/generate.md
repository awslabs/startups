---
_phase: generate
_title: "Generate Migration Artifacts"
_requires_phase: estimate
_input:
  - aws-design.json
  - estimation-infra.json
  - preferences.json
  - heroku-resource-inventory.json
_fragments:
  - _id: terraform
    _trigger: { _always: true }
    _file: phases/generate/generate-terraform.md
  - _id: docs
    _trigger: { _always: true }
    _file: phases/generate/generate-docs.md
  - _id: eks-generate
    _trigger: { _when: "aws-design.json has an eks_cluster entry OR a service with aws_service == 'EKS'" }
    _file: phases/generate/generate-eks.md
_assemble:
  _file: phases/generate/generate-assemble.md
_produces:
  - generation-warnings.json
_advances_to: complete
---

# Phase 5: Generate Migration Artifacts

> Loaded by SKILL.md when `phases.estimate == "completed"` AND `phases.generate != "completed"`.

**Execute ALL steps in order. Do not skip or optimize.**

## Sub-Files

- **generate-terraform.md** → routes the design into Terraform: writes the `terraform/` directory and `generation-warnings.json`.
- **generate-docs.md** → fills the docs + script templates: writes `MIGRATION_GUIDE.md`, `README.md`, and database migration scripts in `scripts/`.
- **generate-eks.md** → the EKS branch: fires (via its `_when` trigger) only when the design contains `aws_service: "EKS"`; writes `terraform/eks.tf` + the `kubernetes/` manifests.
- **generate-assemble.md** → the assembler: cross-artifact validation, completion handoff gate, and `.phase-status.json` update.

---

## Step 0: Validate Prerequisites

1. Read `$MIGRATION_DIR/.phase-status.json`. Validate per SKILL.md State Validation rules.
2. Confirm `phases.estimate == "completed"`. If not:

   ```
   GATE_FAIL | phase=generate | field=phases.estimate | reason=missing
   ```

3. Confirm no other core phase is `in_progress`. If violated → GATE_FAIL.
4. Set `phases.generate` to `"in_progress"` and `current_phase` to `"generate"`. Write `.phase-status.json`.
5. Read all required artifacts from `$MIGRATION_DIR/`:
   - `aws-design.json` (REQUIRED)
   - `estimation-infra.json` (REQUIRED)
   - `preferences.json` (REQUIRED)
   - `heroku-resource-inventory.json` (REQUIRED)
6. Confirm all four files exist and parse as valid JSON. If any missing:

   ```
   GATE_FAIL | phase=generate | field=<filename> | reason=missing
   ```

---

## Step 1: Generate Terraform Configurations

Load `references/phases/generate/generate-terraform.md` and execute completely.

This produces:

- `$MIGRATION_DIR/terraform/` directory with all `.tf` files
- `$MIGRATION_DIR/generation-warnings.json` (if any services were skipped)

**Gate check after Step 1:**

- `terraform/main.tf` must exist
- `terraform/variables.tf` must exist
- `terraform/outputs.tf` must exist
- At least one domain file must exist (`beanstalk.tf`, `pipeline.tf`, `compute.tf`, `database.tf`, `cache.tf`, `messaging.tf`, or `vpc.tf`)

If gate fails: STOP. Output: "Terraform generation failed. Check generation-warnings.json for details."

**EKS Generation (conditional):**

If `aws-design.json` contains any service with `aws_service: "EKS"`:

- Load `references/phases/generate/generate-eks.md`
- Follow its instructions to produce `terraform/eks.tf` and `kubernetes/` directory
- Add Helm provider to `terraform/main.tf`
- Add EKS sections to MIGRATION_GUIDE.md

If NO services have `aws_service: "EKS"`, skip EKS generation entirely.

---

## Step 2: Generate Documentation and Scripts

Load `references/phases/generate/generate-docs.md` and execute completely.

This produces:

- `$MIGRATION_DIR/MIGRATION_GUIDE.md`
- `$MIGRATION_DIR/README.md`
- `$MIGRATION_DIR/scripts/migrate-postgres.sh` (if Postgres in design)
- `$MIGRATION_DIR/scripts/migrate-redis.sh` (if Redis in design)

**Gate check after Step 2:**

- `MIGRATION_GUIDE.md` must exist
- `README.md` must exist

If gate fails: STOP. Output: "Documentation generation incomplete. MIGRATION_GUIDE.md or README.md missing."

---

## Step 3: Assemble and Validate

Load `references/phases/generate/generate-assemble.md` (the phase's assembler) and
follow it to validate the complete artifact set (cross-reference checks), run the
completion handoff gate, and update `.phase-status.json`. It owns the phase's final
artifact-level contract.

---

## Scope Boundary

**This phase covers artifact generation ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Re-designing or changing AWS service selections (Phase 3 decisions are final)
- Re-estimating costs (Phase 4 estimates are final)
- Asking the user additional clarification questions (Phase 2 is done)
- Discovering new Heroku resources (Phase 1 is done)
- Feedback collection (Phase 6 handles this)

**Your ONLY job: Transform the design into deployable artifacts. Nothing else.**
