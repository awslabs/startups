# Implementation Plan: Vercel-to-AWS Generate Phase Parity

## Overview

This plan upgrades the `vercel-to-aws` skill from assessment-only (optional scaffold checkpoint) to full generate-phase parity with `heroku-to-aws`. It adds a mandatory `estimate` phase, promotes the `scaffold` checkpoint into a mandatory `generate` backbone phase producing production-ready Terraform (including `baseline.tf`), migration scripts, and documentation, and repositions the `report` phase after generation.

The new backbone: `prescan` -> `discover` -> `clarify` -> `recommend` -> `estimate` -> `generate` -> `report` -> `complete`.

All "code" is markdown phase/fragment files carrying DSL frontmatter, JSON knowledge tables, and vendored shared schemas. The skill lives at `migrate/plugins/migration-to-aws/skills/vercel-to-aws/`.

**Effort estimate:** ~3-4 days for a single contributor familiar with the DSL.

## Tasks

-
  1. [ ] Vendor shared estimate/pricing files and register in CI sync
  - [ ] 1.1 Copy `skills/shared/pricing/aws-infra-pricing.json` -> `skills/vercel-to-aws/references/vendored/pricing/aws-infra-pricing.json`
    - Byte-identical copy; no modifications
    - _Requirements: 1.4_

  - [ ] 1.2 Copy `skills/shared/estimate/estimation-infra.schema.json` -> `skills/vercel-to-aws/references/vendored/estimate/estimation-infra.schema.json`
    - Byte-identical copy; no modifications
    - _Requirements: 1.3_

  - [ ] 1.3 Copy `skills/shared/estimate/complexity-tiers.json` -> `skills/vercel-to-aws/references/vendored/estimate/complexity-tiers.json`
    - Byte-identical copy; no modifications
    - _Requirements: 1.7_

  - [ ] 1.4 Update `references/vendored/README.md` to add the three new vendored-path -> canonical-source mappings

  - [ ] 1.5 Register the new vendored paths in `tools/sync-vendored-shared.ts` so `mise run shared:check` enforces byte-identity for all 5 vendored files (2 existing + 3 new)

-
  2. [ ] Extend the Clarify phase with estimate-feeding questions
  - [ ] 2.1 Add `vercel_spend` question to `references/phases/clarify/clarify-ask.md`
    - Question: "What is your approximate monthly Vercel spend?" with options ($0-50, $50-200, $200-1000, $1000+, Skip)
    - Skip logic: skip when `discovery.json.usage_metrics.billing_data` is present
    - `design_consequence`: "Feeds the Vercel baseline in the cost estimate"
    - _Requirements: 8.1_

  - [ ] 2.2 Add `database_size` question to `references/phases/clarify/clarify-ask.md`
    - Question: "Approximately how large is your Vercel Postgres database?"
    - Options: < 1 GB, 1-10 GB, 10-100 GB, > 100 GB
    - Skip logic: skip when no Postgres peripheral detected in `discovery.json.peripherals[]`
    - `design_consequence`: "Drives migration tool selection (pg_dump vs DMS) and RDS instance sizing"
    - _Requirements: 8.2_

  - [ ] 2.3 Add `compliance` question to `references/phases/clarify/clarify-ask.md`
    - Question: "Do you have compliance requirements?" with multi-select (SOC 2, PCI DSS, HIPAA, FedRAMP, None)
    - Skip logic: skip when the question was already covered in another context (unlikely for Vercel-first migrations)
    - `design_consequence`: "Drives the compliance-conditional section in baseline.tf (Config, Security Hub, retention periods)"
    - _Requirements: 8.3_

  - [ ] 2.4 Update `references/phases/clarify/clarify-assemble.md` to include the three new answers in `clarify-answers.json` and `assessment-state.json.clarify_answers`

-
  3. [ ] Checkpoint — Clarify extension review
  - Verify: the three new questions only appear when their skip-logic conditions are NOT met; `clarify-answers.json` schema still valid; the frontmatter validator passes. Ask the user if questions arise.

-
  4. [ ] Implement the `estimate` phase
  - [ ] 4.1 Create `references/phases/estimate/estimate.md` (orchestrator)
    - Frontmatter: `_phase: estimate`, `_requires_phase: recommend`, `_advances_to: generate`, `_interactive: false`, `_exec: { _agent: rw }`
    - `_input`: `[recommendation.json, discovery.json, clarify-answers.json, coupling-score.json]`
    - `_knowledge`: vendored `aws-infra-pricing.json`, `complexity-tiers.json`, `estimation-infra.schema.json`
    - `_produces`: `[estimation-infra.json]`
    - `_preconditions`: `_check_phase_completed: recommend`, `_check_file_exists: [recommendation.json, discovery.json, clarify-answers.json]`, `_validate_json` on all inputs
    - `_postconditions`: `_check_file_exists: estimation-infra.json`, `_validate_json: estimation-infra.json`, Property-16 arithmetic assert, `recommendation.path` enum assert, `projected_costs.aws_monthly_balanced > 0` assert
    - `_forbids_files`: `[terraform/**, scripts/**, MIGRATION_GUIDE.md, README.md]`
    - Prose: Step 0 validate prerequisites, Step 1 run cost-engine fragment, Step 2 assemble
    - Scope boundary: financial analysis only, no Terraform, no architecture changes
    - _Requirements: 1.1, 1.2, 1.3, 1.9_

  - [ ] 4.2 Create `references/phases/estimate/estimate-cost-engine.md` (fragment)
    - Frontmatter: `_fragment: cost-engine`, `_of_phase: estimate`, `_contributes: [estimation-infra.json]`
    - Step 0: Pricing mode selection — same 4-priority hierarchy as Heroku (cached -> live MCP -> cached_fallback -> unavailable)
    - Step 0c: Display pricing mode to user before computation
    - Part 1: Determine current Vercel costs (4-priority source: API metrics, user-provided from Clarify, plan-based estimation, unavailable)
    - Part 2: Compute per-service AWS costs based on `recommendation.json.outcome`:
      - Outcome A: Lambda (server fn), CloudFront, S3, EventBridge (revalidation), peripherals
      - Outcome B: Fargate (tasks + ALB), CloudFront, ECR, NAT Gateway, peripherals
      - Outcome C: Lambda+APIGW or Fargate (per `backend_shape`), peripherals
      - "stay": Peripheral costs only
    - Part 3: Three-tier modeling (Premium/Balanced/Optimized) with per-service multipliers
    - Part 4: Cost comparison, ROI analysis, optimization opportunities
    - Part 5: Complexity tier classification using `complexity-tiers.json`
    - Part 6: Recommendation path computation (migrate_optimized / migrate_phased / stay)
    - _Requirements: 1.4, 1.5, 1.6, 1.7, 1.8, 1.10_

  - [ ] 4.3 Create `references/phases/estimate/estimate-assemble.md` (assembler)
    - Frontmatter: `_assemble: estimate-assemble`, `_of_phase: estimate`, `_reads: [cost-engine]`, `_produces: [estimation-infra.json]`
    - Step 1: Write `estimation-infra.json` conforming to vendored schema
    - Step 2: Validate Property-16 (balanced total = sum of per-service costs)
    - Step 3: Run postcondition checks, emit `HANDOFF_OK | phase=estimate | artifacts=estimation-infra.json`
    - Step 4: Update `.phase-status.json`, present cost summary to user
    - _Requirements: 1.3, 1.9_

-
  5. [ ] Checkpoint — Estimate phase integration
  - Verify: `estimation-infra.json` conforms to the shared schema; Property-16 holds; complexity tier classification is correct for a typical Vercel app (single Next.js app = small tier). Run the frontmatter validator. Ask the user if questions arise.

-
  6. [ ] Implement the `generate` phase — core infrastructure
  - [ ] 6.1 Create `references/phases/generate/generate.md` (orchestrator)
    - Frontmatter: `_phase: generate`, `_requires_phase: estimate`, `_advances_to: report`, `_interactive: false`, `_exec: { _agent: rw }`
    - `_input`: `[recommendation.json, estimation-infra.json, discovery.json, preflight-findings.json, coupling-score.json, clarify-answers.json]`
    - `_knowledge`: `[knowledge/peripheral-mappings.json, references/shared/graviton.md]`
    - `_fragments`: baseline (always), terraform (always), compute-opennext (outcome A), compute-fargate (outcome B or C-B), compute-lambda (outcome C-A), peripherals (always), scripts (always), docs (always)
    - `_produces`: full file list per design.md output table
    - `_preconditions`: `_check_phase_completed: estimate`, `_check_file_exists` on all 6 inputs, `_validate_json` on all JSON inputs
    - `_postconditions`: file-exists checks for mandatory outputs, no-placeholder assert, at-least-one-domain-tf assert, mutual-exclusion assert (at most one compute fragment fired)
    - `_forbids_files`: input artifacts (read-only from this phase)
    - Prose: Step ordering (baseline first, then terraform core, then compute, then peripherals, then scripts, then docs, then assemble)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.9_

  - [ ] 6.2 Create `references/phases/generate/generate-baseline.md` (fragment: baseline)
    - Frontmatter: `_fragment: baseline`, `_of_phase: generate`, `_trigger: { _always: true }`, `_contributes: [terraform/baseline.tf]`
    - Step 1: Compute CloudTrail retention from `clarify-answers.json.compliance` (same mapping as GCP: absent->90, soc2->365, pci->365, hipaa->2190, fedramp->1095, max())
    - Step 2: Compute budget limit: `max(50, ceil(estimation-infra.json.projected_costs.aws_monthly_balanced * 1.2))`
    - Step 3: Emit always-on resources (alternate contacts, password policy, S3 PAB, EBS encryption, Access Analyzer, IMDSv2, CloudTrail + log bucket, budget, GuardDuty)
    - Step 4: Emit remote-state backend infrastructure (S3 tfstate bucket + DynamoDB lock table)
    - Step 5: Conditionally emit compliance section (Config + Security Hub) when compliance answer present
    - Step 6: Attach inline HCL comments (TODO-emails, collision warnings, cost disclosures, `defense-in-depth` tokens)
    - Source tag: `Source = "vercel-to-aws"`
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.8_

  - [ ] 6.3 Create `references/phases/generate/generate-terraform.md` (fragment: terraform)
    - Frontmatter: `_fragment: terraform`, `_of_phase: generate`, `_trigger: { _always: true }`, `_contributes: [terraform/main.tf, terraform/variables.tf, terraform/outputs.tf, terraform/vpc.tf, terraform/security.tf, terraform/.gitignore, terraform/terraform.tfvars.example]`
    - Step 1: Generate `main.tf` — provider config (aws ~> 5.80, required_version >= 1.5.0), `default_tags` (Project/Environment/ManagedBy/MigrationId/Source=vercel-to-aws), data sources, active S3 backend block referencing baseline.tf resources
    - Step 2: Generate `variables.tf` — global vars (aws_region, project_name, environment, migration_id) + per-service vars derived from recommendation/estimation
    - Step 3: Generate `outputs.tf` — migration_summary + per-service connection outputs (sensitive=true for endpoints)
    - Step 4: Generate `vpc.tf` — always new VPC (Vercel has no VPC peering). Public subnets (ALB/CloudFront origin), private subnets (compute/database), IGW, NAT gateway, route tables
    - Step 5: Generate `security.tf` — least-privilege IAM roles/policies per service, security groups scoped to generated resources
    - Step 6: Generate `.gitignore` (terraform.tfstate, .terraform/, *.tfvars)
    - Step 7: Generate `terraform.tfvars.example` — populated with actual defaults from estimation/recommendation, source annotations as comments
    - Header comment in `main.tf`: explains Balanced cost scenario alignment, Premium/Balanced/Optimized are pricing scenarios not separate stacks
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.9, 5.10_

  - [ ] 6.4 Create `references/phases/generate/generate-assemble.md` (assembler)
    - Frontmatter: `_assemble: generate-assemble`, `_of_phase: generate`, all `_reads` and `_produces`
    - Step 1: Confirm at-most-one compute fragment fired (mutual exclusion)
    - Step 2: Confirm Outcome C never gets app-surface hosting artifacts
    - Step 3: Write `generation-warnings.json` (always — empty array when all services mapped)
    - Step 4: Cross-reference check — every service from estimation is either generated or listed in warnings
    - Step 5: No-placeholder-token scan across all `.tf` files
    - Step 6: Run postconditions, emit `HANDOFF_OK | phase=generate | artifacts=...`
    - _Requirements: 2.9, 5.9, 9.5_

-
  7. [ ] Implement the `generate` phase — compute fragments
  - [ ] 7.1 Create `references/phases/generate/generate-opennext.md` (fragment: compute-opennext)
    - Frontmatter: `_fragment: compute-opennext`, `_of_phase: generate`, `_trigger: { _when: "recommendation.outcome == 'A'" }`, `_contributes: [sst.config.ts, terraform/cdn.tf]`
    - Full app-surface mode: emit `sst.config.ts` (SST/OpenNext — server functions, CloudFront, ISR tag cache + revalidation queue together, image optimization)
    - Default server function to Graviton ARM64 (`server: { architecture: "arm64" }`)
    - Wire M1 remediation (external middleware via `open-next.config.ts`) when M1 HIGH severity
    - Wire B1-B4/S1/O1 remediations as applicable from `preflight-findings.json`
    - Emit `terraform/cdn.tf` for CloudFront distribution config that SST references
    - Document SST exception inline (Terraform-first convention; SST is OpenNext's happy path for the app surface)
    - Scope boundary: NEVER fires alongside compute-fargate or compute-lambda; NEVER emits under Outcome C
    - _Requirements: 9.1_

  - [ ] 7.2 Create `references/phases/generate/generate-fargate.md` (fragment: compute-fargate)
    - Frontmatter: `_fragment: compute-fargate`, `_of_phase: generate`, `_trigger: { _when: "recommendation.outcome == 'B' OR (outcome == 'C' AND backend_shape == 'B-shaped')" }`, `_contributes: [terraform/compute.tf, terraform/cdn.tf]`
    - Step 0: Determine mode — full app-surface (Outcome B) vs backend-only (Outcome C, B-shaped)
    - Full app-surface mode: ECS Fargate task definitions (ARM64 default), ALB, CloudFront, ECR, autoscaling, CloudWatch log groups
    - Backend-only mode: same Fargate stack but scoped to separable backend routes only
    - Wire I1 remediation (shared cache or cache-control headers for multi-instance ISR)
    - Wire M1 remediation (CloudFront Functions for header/redirect logic)
    - Emit `terraform/cdn.tf` with CloudFront distribution, cache behaviors, origin config
    - Instance sizing derived from `estimation-infra.json.projected_costs.breakdown` (Balanced tier)
    - _Requirements: 9.2, 9.3_

  - [ ] 7.3 Create `references/phases/generate/generate-lambda.md` (fragment: compute-lambda)
    - Frontmatter: `_fragment: compute-lambda`, `_of_phase: generate`, `_trigger: { _when: "recommendation.outcome == 'C' AND backend_shape == 'A-shaped'" }`, `_contributes: [terraform/compute.tf]`
    - Emit API Gateway (HTTP API) + Lambda functions for separable backend routes
    - Default Lambda to Graviton ARM64 (`architectures = ["arm64"]`)
    - Wire M1 remediation if applicable
    - Document inline: "This backend-only scaffold serves Outcome C (Hybrid) — your Next.js app remains on Vercel"
    - _Requirements: 9.3_

-
  8. [ ] Implement the `generate` phase — peripherals and scripts
  - [ ] 8.1 Create `references/phases/generate/generate-peripherals.md` (fragment: peripherals)
    - Frontmatter: `_fragment: peripherals`, `_of_phase: generate`, `_trigger: { _always: true }`, `_contributes: [terraform/database.tf, terraform/cache.tf, terraform/storage.tf, terraform/scheduling.tf]` (conditional per peripheral)
    - Load `knowledge/peripheral-mappings.json`, map each detected peripheral to AWS Terraform resources:
      - Blob -> `terraform/storage.tf` (S3 bucket with versioning, lifecycle, PAB)
      - Cron -> `terraform/scheduling.tf` (EventBridge Scheduler + Lambda invoker, ARM64)
      - KV -> `terraform/cache.tf` (ElastiCache Redis, subnet group, security group) with "Upstash often correct to keep" advisory
      - Postgres -> `terraform/database.tf` (RDS PostgreSQL or Aurora, parameter group, subnet group) with "Neon often correct to keep" advisory
      - Edge Config -> no Terraform (maps to SSM Parameter Store which baseline.tf already covers); document in README
      - Env vars -> covered by secrets migration script
    - Wire M2 remediation (CloudFront header mapping) when M2 detected
    - Outcome C cross-check: flag peripherals whose associated route is not in the separable surface
    - Sizing derived from `estimation-infra.json` Balanced tier
    - _Requirements: 2.5, 9.1, 9.2, 9.3_

  - [ ] 8.2 Create `references/phases/generate/generate-scripts.md` (fragment: scripts)
    - Frontmatter: `_fragment: scripts`, `_of_phase: generate`, `_trigger: { _always: true }`, `_contributes: [scripts/01-validate-prerequisites.sh, scripts/02-migrate-secrets.sh, scripts/06-validate-migration.sh]` + conditional scripts
    - `scripts/01-validate-prerequisites.sh`: Check AWS CLI, Terraform >= 1.5, target region accessible, IAM permissions (sts get-caller-identity + required service permissions), Docker installed (if Outcome B)
    - `scripts/02-migrate-secrets.sh`: Iterate `discovery.json.env_var_names[]`, create in Secrets Manager or SSM Parameter Store, dry-run default, requires user to provide values (names only from discovery)
    - `scripts/03-migrate-database.sh` (conditional: Postgres detected): pg_dump for < 10 GB, DMS for >= 10 GB (from `clarify-answers.json.database_size`), connection string templating, dry-run default
    - `scripts/04-build-and-push.sh` (conditional: Outcome B): Multi-stage Docker build for Next.js, ECR login, push, ARM64 build note per graviton.md
    - `scripts/05-dns-cutover.sh` (conditional: Outcome A or B): DNS migration from Vercel to CloudFront/ALB, TTL lowering procedure, rollback commands, dry-run default
    - `scripts/06-validate-migration.sh`: HTTP health checks against new endpoints, response comparison (status + key headers), SSL certificate validation
    - All scripts: header comment (purpose, prerequisites, dry-run behavior, rollback), `set -euo pipefail`, `--execute` flag required for destructive actions
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [ ] 8.3 Create `references/phases/generate/generate-docs.md` (fragment: docs)
    - Frontmatter: `_fragment: docs`, `_of_phase: generate`, `_trigger: { _always: true }`, `_contributes: [MIGRATION_GUIDE.md, README.md, terraform/README.md]`
    - `terraform/README.md`: What this directory implements, cost-tier explanation (Balanced alignment), bootstrap procedure for remote state (2-step init), file inventory, Graviton/ARM64 advisory, OpenNext v3 interface note (Outcome A only)
    - `MIGRATION_GUIDE.md`: Prerequisites, phased migration timeline (aligned with complexity tier from estimation), step-by-step procedures for each script, verification checklist, rollback procedures, Go/No-Go gates
    - `README.md` (top-level in $MIGRATION_DIR): All artifacts listed, cost-tier reference to `estimation-infra.json`, assessment reference to `assessment-report.html`, complexity tier note, recommendation outcome summary
    - Dollar-figure labeling rule: every $ figure adjacent to "estimated monthly"
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

-
  9. [ ] Checkpoint — Generate phase structural validation
  - Run the frontmatter validator across all new generate phase files. Verify: mutual exclusion triggers on compute fragments are correct, `_produces` lists match `_contributes` across fragments, `_forbids_files` prevents input artifact modification. Ask the user if questions arise.

-
  10. [ ] Update the `report` phase for post-generate positioning
  - [ ] 10.1 Update `references/phases/report/report.md` frontmatter
    - Change `_requires_phase` from `recommend` to `generate`
    - Add `estimation-infra.json` and `generation-warnings.json` to `_input`
    - Remove the "Optional: Generate IaC Scaffold" prompt from `SKILL.md` (scaffold no longer exists)
    - _Requirements: 7.1, 7.5_

  - [ ] 10.2 Update `references/phases/report/report-render.md`
    - Add a "Cost Comparison" section rendering Vercel current vs. AWS projected (three tiers) from `estimation-infra.json`
    - Add an "Artifacts Generated" section listing the contents of `terraform/` and `scripts/` with one-line descriptions
    - Change the "Next Steps" section from "optionally generate scaffold" to "apply the generated Terraform" with a reference to `MIGRATION_GUIDE.md`
    - _Requirements: 7.2, 7.3_

  - [ ] 10.3 Update `scripts/validate-assessment-report.py`
    - Add a new check: when `estimation-infra.json` exists alongside the report, the report MUST contain a cost-comparison section (section ID `cost-comparison`)
    - Add section ID `cost-comparison` and `artifacts-generated` to `REQUIRED_SECTION_IDS` (conditional on `estimation-infra.json` presence)
    - _Requirements: 7.4_

  - [ ] 10.4 Update `tests/test_validate_assessment_report.py`
    - Add test cases for the new conditional section checks (cost-comparison present/absent with/without estimation-infra.json)
    - Update the reference fixture (`fixtures/assessment-report-reference.html`) to include the new sections
    - Update the stub fixture if needed for new failure modes
    - _Requirements: 7.4_

-
  11. [ ] Update `SKILL.md` and retire the scaffold checkpoint
  - [ ] 11.1 Update `SKILL.md` backbone declaration
    - New backbone: `prescan` -> `discover` -> `clarify` -> `recommend` -> `estimate` -> `generate` -> `report` -> `complete`
    - Remove the entire "Scaffold Checkpoint" section (§ Scaffold Checkpoint, the A/B prompt, the tiebreak persistence logic)
    - Remove the Philosophy bullet "Assessment is the durable value, not scaffolding"
    - Add a note: "Generation is a first-class deliverable. The generate phase produces production-ready Terraform, a security baseline, migration scripts, and documentation."
    - Update the File Structure tree to reflect: new `references/phases/estimate/` directory, renamed `references/phases/generate/` (was scaffold), removed scaffold files, new vendored estimate/pricing files
    - Add a "Breaking Change" note: assessments started before this version (with `scaffold` as a checkpoint in `.phase-status.json`) must be re-run from `prescan`
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ] 11.2 Delete the scaffold phase files
    - Delete `references/phases/scaffold/scaffold.md`
    - Delete `references/phases/scaffold/scaffold-opennext.md`
    - Delete `references/phases/scaffold/scaffold-fargate.md`
    - Delete `references/phases/scaffold/scaffold-peripherals.md`
    - Delete `references/phases/scaffold/scaffold-assemble.md`
    - (Logic from these files is absorbed into the generate fragments — not lost, but promoted and expanded)

  - [ ] 11.3 Update `references/phases/recommend/recommend.md` and `recommend-assemble.md`
    - No change needed to recommend itself — it still advances to the NEXT phase. However, since the backbone now has `estimate` after `recommend` (not `report`), verify that `recommend.md`'s frontmatter does NOT have an explicit `_advances_to` that points to `report`. If it does, change it to `estimate`. If it uses the backbone chain implicitly, no change needed.
    - _Requirements: 1.1_

-
  12. [ ] Plugin-level integration
  - [ ] 12.1 Update `migrate/plugins/migration-to-aws/README.md`
    - Update the Vercel section to mention full Terraform generation (not just "assessment only")
    - Update the Vercel row in the "What It Detects" and "What You Get" tables
    - Update Requirements section to note that Vercel migrations now produce Terraform + scripts (same output class as GCP/Heroku)
    - _Requirements: Introduction_

  - [ ] 12.2 Update `migrate/README.md`
    - Update the top-level description of the Vercel skill from "honest assessment" to "assessment + full migration artifacts"
    - _Requirements: Introduction_

  - [ ] 12.3 Register `estimate` phase files in the frontmatter validator scope
    - Ensure `mise run lint:frontmatter` covers `skills/vercel-to-aws/references/phases/estimate/*.md` (same glob pattern as heroku — verify it already catches skill subdirectories, or add explicitly)

-
  13. [ ] Final checkpoint — Full integration validation
  - Run `mise run build` (lint:md + lint:types + lint:frontmatter + shared:check + test + fmt:check + security)
  - Run the frontmatter validator specifically against the vercel-to-aws skill (all phases)
  - Run `tests/test_validate_assessment_report.py` (pytest suite — should pass with updated fixtures)
  - Verify vendored file byte-identity (`mise run shared:check`)
  - Verify the backbone chain: `prescan._advances_to == discover`, `discover._advances_to == clarify`, `clarify._advances_to == recommend`, `recommend._advances_to == estimate`, `estimate._advances_to == generate`, `generate._advances_to == report`, `report._advances_to == complete` — no broken links
  - Verify no orphaned files remain from the scaffold phase (the `references/phases/scaffold/` directory should not exist)

## Notes

- This is a prompt-based AI agent skill plugin — "implementation" means creating/modifying markdown reference files and JSON schemas, not traditional code. The only Python changes are to the report validator script and its test suite.
- The generate phase fragments absorb and EXPAND the logic from the retired scaffold fragments. Key expansions: baseline.tf (new), VPC (new — scaffold had no VPC), security.tf (new — scaffold had no IAM), migration scripts (new), MIGRATION_GUIDE.md (new), production-ready sizing from estimation (scaffold used "thin skeleton" philosophy).
- The estimate phase is entirely new — no scaffold equivalent existed. It follows the Heroku estimate pattern exactly (same schema, same pricing hierarchy, same MCP fallback) with Vercel-specific inputs for the current-cost baseline.
- `gcp-to-aws` and `heroku-to-aws` are NOT modified by this plan.
- Existing assessment-state.json schema is unchanged — the recompute-on-new-input mechanism continues working for prescan/discover/clarify/recommend.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3", "2.4"] },
    { "id": 2, "tasks": ["4.1", "4.2", "4.3"] },
    { "id": 3, "tasks": ["6.1", "6.2", "6.3", "6.4"] },
    { "id": 4, "tasks": ["7.1", "7.2", "7.3"] },
    { "id": 5, "tasks": ["8.1", "8.2", "8.3"] },
    { "id": 6, "tasks": ["10.1", "10.2", "10.3", "10.4"] },
    { "id": 7, "tasks": ["11.1", "11.2", "11.3"] },
    { "id": 8, "tasks": ["12.1", "12.2", "12.3"] }
  ]
}
```

Checkpoints (3, 5, 9, 13) are sequencing gates — each runs after its preceding wave completes and before the next wave begins.
