---
_assemble: assemble-generation
_of_phase: generate
_reads:
  - terraform (fragment contribution)
  - docs (fragment contribution)
  - eks-generate (fragment contribution, when EKS in design)
_produces:
  - generation-warnings.json
---

# Generate — Validate and Assemble

> **Assembler unit.** Runs after the generation fragments (`generate-terraform.md`,
> `generate-docs.md`, and `generate-eks.md` when EKS is in the design) have written
> their artifacts. It runs the cross-artifact validation (every-service-generated-or-warned,
> reference integrity, no `{{VAR}}` leak), enforces the completion handoff gate,
> and updates `.phase-status.json`. It owns the phase's final artifact-level contract.

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
- If any service has `aws_service: "EKS"` → `terraform/eks.tf` must exist AND `kubernetes/` directory must contain at least one Deployment manifest
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
10. If EKS in design → `terraform/eks.tf` exists with cluster + node group resources
11. If EKS in design → `kubernetes/` directory exists with namespace + deployment manifests
12. No placeholder `{{VARIABLE}}` in Terraform `.tf` files (those belong in `variables.tf` as proper `var.*` references)

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
