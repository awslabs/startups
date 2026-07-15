# Requirements: Vercel-to-AWS Generate Phase Parity

## Introduction

This feature upgrades the `vercel-to-aws` skill from its current architecture (assessment-only backbone with an optional scaffold checkpoint) to full generate-phase parity with the `heroku-to-aws` skill. The upgrade adds a mandatory `estimate` backbone phase and promotes the current optional `scaffold` checkpoint into a mandatory `generate` backbone phase that produces production-ready Terraform, a security baseline, migration scripts, and documentation.

The current backbone is: `prescan` -> `discover` -> `clarify` -> `recommend` -> `report` -> `complete` (with `scaffold` as an off-backbone checkpoint).

The new backbone will be: `prescan` -> `discover` -> `clarify` -> `recommend` -> `estimate` -> `generate` -> `report` -> `complete`.

Key changes:

- `estimate` phase inserted between `recommend` and `generate` (uses shared `estimation-infra.schema.json` and `aws-infra-pricing.json`)
- `scaffold` checkpoint promoted to mandatory `generate` backbone phase
- `generate` output expanded from "thin working skeleton" to production-ready Terraform
- `baseline.tf` always emitted (security baseline: GuardDuty, CloudTrail, IMDSv2, EBS encryption, budget alerts, Access Analyzer)
- Migration scripts emitted (DNS cutover, secrets migration, container migration where applicable)
- `MIGRATION_GUIDE.md` and full `terraform/README.md` emitted
- `report` phase moves AFTER `generate` (it incorporates cost data and references generated artifacts)

This does NOT change: the Vercel-specific assessment philosophy (derive-don't-discover), the Coupling Score, Pre-Flight Checks, the Recommendation Engine, or the report's honest assessment nature. The report still carries the assessment; the generate phase now also delivers actionable artifacts.

## Requirements

### Requirement 1: Estimate Phase

**User Story:** As a startup founder migrating from Vercel, I want to see projected AWS costs compared to my current Vercel spend, so that I can make an informed financial decision.

#### Acceptance Criteria

1. THE estimate phase SHALL be a mandatory backbone phase positioned after `recommend` and before `generate`, with `_requires_phase: recommend` and `_advances_to: generate`
2. THE estimate phase SHALL consume `recommendation.json`, `discovery.json`, `clarify-answers.json`, and `coupling-score.json` as inputs
3. THE estimate phase SHALL produce `estimation-infra.json` conforming to `skills/shared/estimate/estimation-infra.schema.json`
4. THE estimate phase SHALL compute projected AWS costs across three tiers (Premium/Balanced/Optimized) using the same pricing hierarchy as the Heroku skill: cached pricing from `skills/shared/pricing/aws-infra-pricing.json` (priority 1), live MCP `awspricing` (priority 2 when cache stale/missing), cached fallback (priority 3), unavailable (priority 4)
5. THE estimate phase SHALL derive Vercel current costs from available inputs: Vercel API usage metrics (priority 1), user-provided monthly spend from Clarify (priority 2), Vercel plan-based estimation from discovered tier/seat count (priority 3), unavailable (priority 4)
6. THE estimate phase SHALL compute costs for each AWS service in the designed architecture: Fargate (Outcome B), Lambda + API Gateway (Outcome A/C serverless), CloudFront, S3, ElastiCache, RDS/Aurora, EventBridge Scheduler, Secrets Manager, NAT Gateway, ALB — based on what `recommendation.json` and `discovery.json` indicate
7. THE estimate phase SHALL classify migration complexity using `skills/shared/estimate/complexity-tiers.json`
8. THE estimate phase SHALL produce a `recommendation.path` of `migrate_optimized`, `migrate_phased`, or `stay` with accompanying `migrate_if` and `stay_if` arrays
9. THE estimate phase SHALL validate the Property-16 invariant: the balanced total must equal the arithmetic sum of per-service costs
10. THE estimate phase SHALL surface the pricing mode to the user before computation (same pattern as Heroku's Step 0c)

### Requirement 2: Generate Phase (Promoted from Scaffold)

**User Story:** As a startup founder who has decided to migrate off Vercel, I want production-ready Terraform that I can apply to stand up my AWS infrastructure, not just a thin skeleton.

#### Acceptance Criteria

1. THE generate phase SHALL be a mandatory backbone phase with `_requires_phase: estimate` and `_advances_to: report`
2. THE generate phase SHALL consume `recommendation.json`, `estimation-infra.json`, `discovery.json`, `preflight-findings.json`, `coupling-score.json`, and `clarify-answers.json`
3. THE generate phase SHALL produce a `terraform/` directory containing production-ready HCL that passes `terraform validate`
4. THE generate phase SHALL always emit: `terraform/main.tf`, `terraform/variables.tf`, `terraform/outputs.tf`, `terraform/security.tf`, `terraform/baseline.tf`, `terraform/.gitignore`, `terraform/terraform.tfvars.example`, `terraform/README.md`
5. THE generate phase SHALL conditionally emit domain files: `terraform/compute.tf` (Fargate or Lambda), `terraform/cdn.tf` (CloudFront), `terraform/database.tf` (RDS/Aurora when Postgres peripheral detected), `terraform/cache.tf` (ElastiCache when KV peripheral detected), `terraform/storage.tf` (S3 when Blob peripheral detected), `terraform/scheduling.tf` (EventBridge when Cron peripheral detected)
6. THE generate phase SHALL emit `terraform/vpc.tf` always (new VPC for every Vercel migration — Vercel has no VPC peering equivalent)
7. THE generate phase SHALL emit a complete `MIGRATION_GUIDE.md` with Prerequisites, Step-by-step Migration, Verification, and Rollback sections
8. THE generate phase SHALL emit a top-level `README.md` listing all artifacts, their purpose, and the cost-tier alignment note
9. THE generate phase SHALL emit `generation-warnings.json` (always written, empty `warnings` array when clean)
10. THE generate phase SHALL respect the recommendation outcome: Outcome A emits SST/OpenNext for the app surface + Terraform for peripherals/baseline, Outcome B emits Terraform only (Fargate + ALB + CloudFront + peripherals/baseline), Outcome C emits Terraform only for the separable backend + peripherals/baseline (no app-surface hosting)
11. WHEN the recommendation outcome is "stay", THE generate phase SHALL emit baseline.tf + peripheral Terraform only (no compute scaffold for the app itself) and document this in README.md as "partial migration: peripherals only"

### Requirement 3: Security Baseline (`baseline.tf`)

**User Story:** As a startup migrating to AWS for the first time, I want account-level security controls provisioned automatically, so that I start with a secure posture from day one.

#### Acceptance Criteria

1. THE generate phase SHALL always emit `terraform/baseline.tf` regardless of recommendation outcome
2. `baseline.tf` SHALL contain: `aws_account_alternate_contact` (operations, billing, security with TODO-email placeholders), `aws_iam_account_password_policy`, `aws_s3_account_public_access_block`, `aws_ebs_encryption_by_default`, `aws_accessanalyzer_analyzer` (ACCOUNT type), `aws_ec2_instance_metadata_defaults` (IMDSv2 required), `aws_cloudtrail` (multi-region, log file validation), CloudTrail log S3 bucket with PAB/SSE/versioning/lifecycle, `aws_budgets_budget` (limit from `estimation-infra.json`), `aws_guardduty_detector`
3. `baseline.tf` SHALL contain remote-state backend infrastructure: `aws_s3_bucket` for tfstate with versioning/SSE/PAB, `aws_dynamodb_table` for state locking
4. `main.tf` SHALL contain an active S3 backend block (not commented out) referencing the tfstate bucket and lock table from `baseline.tf`
5. WHEN `clarify-answers.json` contains a compliance answer (soc2/pci/hipaa/fedramp), `baseline.tf` SHALL append a compliance-conditional section with AWS Config recorder + delivery channel, Security Hub + standards subscriptions, and a Config S3 log bucket
6. THE CloudTrail retention days SHALL be computed from compliance requirements using the same mapping as the GCP skill: absent/empty -> 90, soc2 -> 365, pci -> 365, hipaa -> 2190, fedramp -> 1095, max() across all declared values
7. THE budget limit SHALL be computed as `max(50, ceil(estimation-infra.json.projected_costs.aws_monthly_balanced * 1.2))`
8. Each resource SHALL carry inline HCL comments: TODO-email warnings on contacts, collision warnings on CloudTrail, cost disclosures on GuardDuty/Config/Security Hub, `defense-in-depth` tokens on all defense-in-depth resources

### Requirement 4: Migration Scripts

**User Story:** As a startup migrating from Vercel, I want runnable migration scripts that handle the cutover steps I'd otherwise have to figure out manually.

#### Acceptance Criteria

1. THE generate phase SHALL emit `scripts/01-validate-prerequisites.sh` checking: AWS CLI configured, Terraform installed, target region accessible, required IAM permissions present
2. THE generate phase SHALL emit `scripts/02-migrate-secrets.sh` that migrates Vercel environment variables (discovered via API as names only) to AWS Secrets Manager or SSM Parameter Store, with dry-run as default mode
3. WHEN a Postgres peripheral is detected, THE generate phase SHALL emit `scripts/03-migrate-database.sh` selecting the appropriate tool (pg_dump for small databases, DMS for zero-downtime) based on the database size if known from Clarify, with dry-run as default
4. WHEN an Outcome A or B migration includes container builds, THE generate phase SHALL emit `scripts/04-build-and-push.sh` for building and pushing container images to ECR
5. THE generate phase SHALL emit `scripts/05-dns-cutover.sh` with the DNS migration procedure (from Vercel's DNS to Route 53 or the user's DNS provider pointing at CloudFront/ALB), with dry-run as default and explicit rollback commands
6. THE generate phase SHALL emit `scripts/06-validate-migration.sh` performing post-migration health checks (HTTP probes against the new endpoints, response comparison)
7. ALL scripts SHALL default to dry-run mode (no destructive actions without explicit `--execute` flag)
8. ALL scripts SHALL include a header comment documenting: what the script does, prerequisites, dry-run behavior, and how to roll back

### Requirement 5: Terraform Quality Standards

**User Story:** As a startup engineer, I want the generated Terraform to be production-quality, not a skeleton I have to rewrite.

#### Acceptance Criteria

1. THE generated Terraform SHALL use the same provider configuration pattern as Heroku: `required_version >= 1.5.0`, `hashicorp/aws ~> 5.80`, `default_tags` block with Project/Environment/ManagedBy/MigrationId/Source
2. THE generated Terraform SHALL include data sources: `aws_caller_identity`, `aws_region`, `aws_availability_zones`
3. `variables.tf` SHALL declare all configurable values with types, descriptions, and defaults derived from the design/estimation artifacts
4. `terraform.tfvars.example` SHALL be populated with actual values (not empty placeholders) and include source annotations as comments
5. `outputs.tf` SHALL expose connection information for all provisioned services, marking connection strings as `sensitive = true`
6. `security.tf` SHALL contain least-privilege IAM roles/policies and security groups scoped to the specific services generated
7. `vpc.tf` SHALL provision a complete VPC with public subnets (ALB/CloudFront origin), private subnets (compute/database), internet gateway, NAT gateway, and route tables
8. ALL Fargate task definitions and Lambda functions SHALL default to Graviton (ARM64) per the existing `references/shared/graviton.md` pattern
9. THE generate phase SHALL emit no `{{PLACEHOLDER}}` tokens in `.tf` files — all configurable values use `var.*` references declared in `variables.tf`
10. THE Terraform SHALL be aligned with the Balanced cost scenario from `estimation-infra.json` (default sizing/HA posture), with a header comment in `main.tf` explaining Premium/Balanced/Optimized are pricing scenarios, not separate stacks

### Requirement 6: Documentation Output

**User Story:** As a startup engineer receiving migration artifacts, I want clear documentation that explains what was generated, why, and how to proceed.

#### Acceptance Criteria

1. `terraform/README.md` SHALL document: what the directory implements, which cost scenario it aligns to (Balanced), how to bootstrap remote state, all emitted files and their purpose, and Graviton/ARM64 advisory notes
2. `MIGRATION_GUIDE.md` SHALL contain: Prerequisites (AWS CLI, Terraform, permissions, DNS access), a phased migration timeline aligned with complexity tier, step-by-step procedures for each script, verification checklist, rollback procedures, and Go/No-Go gate criteria
3. `README.md` (top-level in `$MIGRATION_DIR`) SHALL list: all produced artifacts, reference to `estimation-infra.json` for cost tiers, reference to `assessment-report.html` for the full assessment, and the migration complexity tier
4. EVERY dollar figure in documentation SHALL be adjacent to "estimated monthly" (same labeling rule as the report validator enforces)

### Requirement 7: Report Phase Repositioning

**User Story:** As a founder, I want the final report to reference my cost estimates and generated artifacts, so the assessment is complete in one document.

#### Acceptance Criteria

1. THE report phase SHALL now require `estimate` phase completion (via `_requires_phase` or sequencing from `generate`)
2. THE report SHALL incorporate cost comparison data from `estimation-infra.json` (Vercel current vs. AWS projected, three-tier breakdown)
3. THE report SHALL reference generated artifacts (terraform/, scripts/, MIGRATION_GUIDE.md) as "ready to apply" deliverables rather than the current "optional scaffold" framing
4. THE report validator (`scripts/validate-assessment-report.py`) SHALL be updated to check for cost-section presence when `estimation-infra.json` exists
5. THE Scaffold Checkpoint prompt (SKILL.md) SHALL be removed — generation is no longer optional

### Requirement 8: Clarify Phase Extension

**User Story:** As a founder, I want the clarify phase to ask about cost-relevant details (current Vercel spend, database size) so that the estimate is accurate.

#### Acceptance Criteria

1. THE clarify phase SHALL add a Vercel spend question: "What is your approximate monthly Vercel spend?" (used when Vercel API usage metrics are unavailable or incomplete)
2. THE clarify phase SHALL add a database size question when a Postgres peripheral is detected: "Approximately how large is your Vercel Postgres database?" with options (< 1 GB, 1-10 GB, 10-100 GB, > 100 GB) — drives migration tool selection
3. THE clarify phase SHALL add a compliance question: "Do you have compliance requirements?" with multi-select options (SOC 2, PCI DSS, HIPAA, FedRAMP, None) — drives `baseline.tf` compliance-conditional section
4. These questions SHALL follow the existing skip-logic pattern: if the answer can be derived from Discover (e.g. Vercel API returns billing data), skip the question

### Requirement 9: Outcome-Specific Generate Behavior

**User Story:** As a founder whose recommendation was Outcome C (Hybrid), I want the generate phase to emit only what applies to my backend migration, not a full-app migration I didn't choose.

#### Acceptance Criteria

1. WHEN recommendation is Outcome A (OpenNext/SST): generate SHALL emit `sst.config.ts` for the app surface + Terraform for peripherals/baseline/VPC/scripts/docs — same SST exception as today, now with full Terraform quality for everything else
2. WHEN recommendation is Outcome B (Fargate): generate SHALL emit Terraform only — ECS Fargate task definitions, ALB, CloudFront, ECR, autoscaling, peripherals/baseline/VPC/scripts/docs
3. WHEN recommendation is Outcome C (Hybrid): generate SHALL emit Terraform only for the separable backend (API Gateway + Lambda OR Fargate, per `backend_shape`) + peripherals/baseline — NEVER emit SST or app-surface hosting; the Next.js app remains on Vercel
4. WHEN recommendation is "stay": generate SHALL emit `baseline.tf` + peripheral Terraform only + docs explaining the partial migration; scripts limited to `01-validate-prerequisites.sh` and secrets migration
5. AT MOST ONE of the SST/OpenNext path or the Fargate path SHALL fire — same mutual-exclusion constraint as the current scaffold, now enforced as a postcondition assertion

### Requirement 10: Backward Compatibility

**User Story:** As a user with an existing Vercel assessment (prescan through report already completed), I want a clear migration path to the new phase structure.

#### Acceptance Criteria

1. THE new phase backbone SHALL be documented as a breaking change — existing `.phase-status.json` files from the old backbone (with `scaffold` as a checkpoint) are NOT compatible
2. `SKILL.md` SHALL note that assessments started before this version must be re-run from `prescan` to benefit from the estimate/generate phases
3. THE existing `assessment-state.json` schema SHALL NOT change — the recompute-on-new-input mechanism continues to work for prescan/discover/clarify/recommend phases
