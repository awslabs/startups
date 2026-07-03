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
  - terraform/main.tf
  - terraform/variables.tf
  - terraform/outputs.tf
  - terraform/security.tf
  - terraform/.gitignore
  - terraform/terraform.tfvars.example
  - MIGRATION_GUIDE.md
  - README.md
  - generation-warnings.json
_advances_to: complete
_preconditions:
  - _check_phase_completed: estimate
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: [aws-design.json, estimation-infra.json, preferences.json, heroku-resource-inventory.json]
    _on_failure: _unrecoverable
  - _validate_json: [aws-design.json, estimation-infra.json, preferences.json, heroku-resource-inventory.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: [terraform/main.tf, terraform/variables.tf, terraform/outputs.tf, terraform/security.tf, terraform/.gitignore, terraform/terraform.tfvars.example, MIGRATION_GUIDE.md, README.md, generation-warnings.json]
    _on_failure: _halt_and_inform
  - _assert: "terraform/main.tf has valid provider configuration; terraform/variables.tf declares at least an aws_region variable"
    _on_failure: _halt_and_inform
  - _assert: "at least one domain .tf file exists beyond the core files"
    _on_failure: _halt_and_inform
  - _assert: "MIGRATION_GUIDE.md has Prerequisites and Verification sections; README.md lists the artifacts"
    _on_failure: _halt_and_inform
  - _assert: "if Postgres is in the design, scripts/migrate-postgres.sh exists; if Redis is in the design, scripts/migrate-redis.sh exists"
    _on_failure: _halt_and_inform
  - _assert: "if EKS is in the design, terraform/eks.tf exists WITH cluster + node group resources, AND a kubernetes/ directory has namespace + deployment manifests"
    _on_failure: _halt_and_inform
  - _assert: "every designed service is accounted for (generated or listed in generation-warnings.json)"
    _on_failure: _halt_and_inform
  - _assert: "no placeholder {{VARIABLE}} tokens remain in Terraform .tf files (those belong in variables.tf as var.* references)"
    _on_failure: _halt_and_inform
_forbids_files:
  - heroku-resource-inventory.json
  - preferences.json
  - aws-design.json
  - estimation-infra.json
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

The entry gate (estimate completed, single active phase, all four inputs present + valid
JSON) is enforced by this phase's `_preconditions` frontmatter per `INTERPRETER.md`
§ Gate protocol. Once the preconditions pass, set `phases.generate` to `"in_progress"`
and `current_phase` to `"generate"` in `.phase-status.json`, then proceed.

---

## Step 1: Generate Terraform Configurations

Load `references/phases/generate/generate-terraform.md` and execute completely.

This produces:

- `$MIGRATION_DIR/terraform/` directory with all `.tf` files
- `$MIGRATION_DIR/generation-warnings.json` (always written; empty `warnings` array when nothing was skipped)

**Gate check after Step 1:**

- `terraform/main.tf` must exist
- `terraform/variables.tf` must exist
- `terraform/outputs.tf` must exist
- At least one domain file must exist (`compute.tf`, `database.tf`, `cache.tf`, `messaging.tf`, or `vpc.tf`)

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
