# Phase 5: Generate Migration Artifacts

> Loaded by SKILL.md when `phases.estimate == "completed"` AND `phases.generate != "completed"`.

**Execute ALL steps in order. Do not skip or optimize.**

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

## Step 3: Validate Complete Artifact Set

Load `shared/validate-artifacts.md`. Verify the complete set of generated artifacts:

1. `terraform/main.tf` — provider configuration
2. `terraform/variables.tf` — input variables
3. `terraform/outputs.tf` — resource outputs
4. `terraform/vpc.tf` — VPC configuration (new or existing reference)
5. `terraform/security.tf` — security groups and IAM
6. Domain-specific `.tf` files (per design content)
7. `MIGRATION_GUIDE.md` — step-by-step migration procedure
8. `README.md` — artifact listing and quick start
9. Database migration scripts (conditional on design content)
10. `generation-warnings.json` (if any services were skipped)

**Cross-reference checks:**

- Every service in `aws-design.json.services[]` is either generated in Terraform OR listed in `generation-warnings.json`
- `README.md` references all files that actually exist
- `MIGRATION_GUIDE.md` data migration sections match design content (no empty sections)

---

## Completion Handoff Gate (Fail Closed)

Load `shared/handoff-gates.md`. **Re-read from disk** before checking.

**Checks (all must PASS):**

1. `terraform/main.tf` exists with valid provider configuration
2. `terraform/variables.tf` exists with at least `aws_region` variable
3. `terraform/outputs.tf` exists
4. At least one domain `.tf` file exists beyond core files
5. `MIGRATION_GUIDE.md` exists with Prerequisites and Verification sections
6. `README.md` exists with artifact listing
7. If Postgres in design → `scripts/migrate-postgres.sh` exists
8. If Redis in design → `scripts/migrate-redis.sh` exists
9. Every designed service accounted for (generated or in warnings)
10. No placeholder `{{VARIABLE}}` in Terraform `.tf` files (those belong in `variables.tf` as proper `var.*` references)

**On any FAIL:** Emit `GATE_FAIL | phase=generate | field=<path> | reason=<missing|invalid>`. STOP.

**On PASS:** Emit `HANDOFF_OK | phase=generate | artifacts=terraform/,MIGRATION_GUIDE.md,README.md`.

---

## Step 4: Update Phase Status

Only after `HANDOFF_OK`. Use the Phase Status Update Protocol (read-merge-write):

1. Read current `.phase-status.json` from disk.
2. Set `phases.generate` to `"completed"`.
3. Set `current_phase` to `"complete"`.
4. Update `last_updated` to current ISO 8601 timestamp.
5. Write the full file.

Output to user:

```
Generate phase complete.

Artifacts produced:
• terraform/ — [N] Terraform files for AWS infrastructure
• MIGRATION_GUIDE.md — Step-by-step migration procedure
• README.md — Artifact listing and quick start
• scripts/ — Database migration scripts
[• generation-warnings.json — N service(s) require manual setup]

Migration planning is complete. All artifacts are in $MIGRATION_DIR/.
```

After this output, SKILL.md handles the post-Generate share prompt and feedback finalization.

---

## Output Files

**Generate phase writes to `$MIGRATION_DIR/`. Required outputs:**

1. `.phase-status.json` — updated per Step 4
2. `terraform/` — complete Terraform configuration directory
3. `MIGRATION_GUIDE.md` — migration procedure
4. `README.md` — artifact overview

**Conditional outputs:**

- `scripts/migrate-postgres.sh` — when Postgres in design
- `scripts/migrate-redis.sh` — when Redis in design
- `generation-warnings.json` — when any services skipped

---

## Error Handling

| Error Category                       | Behavior                                  | Status Transition      |
| ------------------------------------ | ----------------------------------------- | ---------------------- |
| Predecessor phase incomplete         | GATE_FAIL, halt                           | Remain `pending`       |
| Input artifact missing/invalid       | GATE_FAIL, halt                           | Retain `in_progress`   |
| Terraform generation partial failure | Log to generation-warnings.json, continue | Continue `in_progress` |
| Documentation generation failure     | GATE_FAIL at Step 2 gate                  | Retain `in_progress`   |
| Handoff gate check fails             | Halt pipeline, surface diagnostic         | Retain `in_progress`   |

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
