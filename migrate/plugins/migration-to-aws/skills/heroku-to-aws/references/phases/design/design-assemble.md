---
_assemble: assemble-design
_of_phase: design
_reads:
  - mapping-engine (fragment contribution)
  - eks-mapping (fragment contribution, when EKS selected)
_produces:
  - aws-design.json
---

# Design — Assemble and Validate aws-design.json

> **Assembler unit.** Runs after the mapping fragments (`design-mapping.md`, and
> `design-eks.md` when EKS is selected) have populated the in-memory design object.
> It writes the final `aws-design.json`, runs the output route gates + completion
> handoff gate, and updates `.phase-status.json`. It owns the artifact-level
> contract for this phase (its postconditions ARE the handoff gate).

---

## Step 6: Write `aws-design.json`

Write the completed design object to `$MIGRATION_DIR/aws-design.json`.

Verify the written file:

1. Parses as valid JSON.
2. Has at least one entry in `services[]` OR at least one entry in `deferred[]`.
3. `vpc_design` section is present and non-empty.
4. All entries in `services[]` have: `service_id`, `source_resource_id`, `heroku_app`, `aws_service`, `confidence`, `aws_config`.
5. All entries in `deferred[]` have: `addon_name`, `addon_plan`, `provider`, `reason`, `recommendation`.

---

## Step 7: Check Outputs

Verify required artifacts exist in `$MIGRATION_DIR/`:

1. `aws-design.json` — MUST exist with valid structure per Step 6 checks.
2. `.phase-status.json` — MUST exist and be valid JSON.

**Route output gates (fail closed):**

- If inventory had formation resources → `services[]` MUST contain at least one Fargate OR EKS entry (unless all dyno types were unrecognized).
- If inventory had `heroku-postgresql` add-ons with recognized plans → `services[]` MUST contain RDS or Aurora entries.
- If inventory had `heroku-redis` add-ons with recognized plans → `services[]` MUST contain ElastiCache entries.
- If inventory had `heroku-kafka` add-ons with recognized plans → `services[]` MUST contain MSK entries.
- If inventory had pipelines → `warnings[]` MUST contain pipeline detect-only warnings.

---

## Completion Handoff Gate (Fail Closed)

The completion checks are declared in this phase's `_postconditions` frontmatter and
enforced per `INTERPRETER.md` § Gate protocol: re-read `aws-design.json` from disk, run
the mechanical checks (`_check_file_exists` / `_validate_json`) and the `_assert`
judgment checks (phase/timestamp/services shape, per-entry required fields, vpc_design
mode, total_services match, no Fir-specific Terraform), plus the route output gates from
Step 7, then emit `GATE_FAIL` (STOP; do not patch artifacts) or
`HANDOFF_OK | phase=design | artifacts=aws-design.json` and advance.

---

## Step 8: Update Phase Status

Only after `HANDOFF_OK`. In the **same turn** as the output message below, use the read-merge-write update protocol (`INTERPRETER.md` § The interpreter loop) to update `.phase-status.json`:

1. Read current `.phase-status.json` from disk.
2. Set `phases.design` to `"completed"`.
3. Set `current_phase` to `"estimate"`.
4. Update `last_updated` to current ISO 8601 timestamp.
5. Keep all other phase values unchanged.
6. Write the full file.

Output to user — build message from design contents:

- "Designed X AWS services across Y apps."
- If deferred add-ons: "Deferred N add-on(s) to specialist engagement."
- If Fir detected: "Fir-generation workloads noted as deferred (detect-only)."
- If pipeline warnings: "N pipeline(s) detected (CI/CD requires manual config)."
- VPC mode: "VPC design: [existing VPC referenced | new VPC generated with N subnets]."

Format: "Design phase complete. [artifact summaries] Next required step: Phase 4 — Estimate. Load `references/phases/estimate/estimate.md` now."

---

## Output Files

**Design phase writes files to `$MIGRATION_DIR/`. Required outputs:**

1. `.phase-status.json` — updated per Step 8
2. `aws-design.json` — complete AWS architecture design

**No other files must be created:**

- No README.md
- No design-summary.md
- No EXECUTION_REPORT.txt
- No documentation or report files

All user communication via output messages only.

---

## Error Handling

| Error Category                               | Behavior                                        | Status Transition             |
| -------------------------------------------- | ----------------------------------------------- | ----------------------------- |
| Predecessor phase incomplete                 | GATE_FAIL, halt                                 | Remain `pending`              |
| Input artifact missing/invalid               | GATE_FAIL, halt                                 | Retain `in_progress`          |
| Unrecognized dyno type                       | Reject formation, add warning, continue         | Continue `in_progress`        |
| Empty Procfile (no process types)            | Reject app formations, add warning, continue    | Continue `in_progress`        |
| Unrecognized Postgres/Redis/Kafka plan       | Defer to specialist gate, add warning, continue | Continue `in_progress`        |
| Unrecognized availability preference         | Default to `multi-az` + RDS + warning, continue | Continue `in_progress`        |
| Add-on not in Fast-Path Table                | Specialist gate (deferred), continue            | Continue `in_progress`        |
| Partial match on Fast-Path Table             | Specialist gate (NOT a match), continue         | Continue `in_progress`        |
| No services AND no deferred entries produced | Unrecoverable error                             | Revert to `pending` (Rule 4)  |
| Handoff gate check fails (GATE_FAIL)         | Halt pipeline, surface diagnostic               | Retain `in_progress` (Rule 3) |
