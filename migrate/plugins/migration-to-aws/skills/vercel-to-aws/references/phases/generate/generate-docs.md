---
_fragment: docs
_of_phase: generate
_contributes:
  - terraform/README.md
  - MIGRATION_GUIDE.md
  - README.md
---

# Generate Phase: Documentation

> Self-contained fragment. Always runs. Produces `terraform/README.md`,
> `MIGRATION_GUIDE.md`, and `README.md` (top-level in `$MIGRATION_DIR`).

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Emit `terraform/README.md`

Required sections:

### 1.1 What This Directory Implements

One paragraph: this Terraform implements the AWS architecture recommended for
the Vercel-to-AWS migration, based on `recommendation.json` (Outcome {A|B|C|stay}).

### 1.2 Cost Tier Alignment

> This Terraform is aligned with the **Balanced** cost scenario from
> `estimation-infra.json` (~${balanced}/mo estimated). Premium and Optimized
> are alternative pricing postures for the same architecture — not separate
> stacks. To realize Premium (higher HA) or Optimized (cost-minimized):
> adjust instance classes, Multi-AZ settings, and capacity reservations in
> `variables.tf`.

### 1.3 Bootstrap: Remote State

```
# 1. First apply (local state, targets only the state backend):
terraform init -backend=false
terraform apply \
  -target=aws_s3_bucket.tfstate \
  -target=aws_s3_bucket_versioning.tfstate \
  -target=aws_s3_bucket_server_side_encryption_configuration.tfstate \
  -target=aws_s3_bucket_public_access_block.tfstate \
  -target=aws_dynamodb_table.tfstate_lock

# 2. Then migrate to remote state:
terraform init
# (Terraform detects the new backend and offers to migrate)
```

### 1.4 File Inventory

Table listing every `.tf` file, its domain, and what it contains. Include
conditional files with a note about when they're emitted.

### 1.5 Graviton (ARM64) Advisory

All compute resources (Fargate tasks, Lambda functions) default to ARM64
(Graviton). For Fargate (Outcome B): container builds must target
`linux/arm64` via `docker buildx build --platform linux/arm64`. `sharp`
(the primary native dependency in Next.js apps) ships ARM64 prebuilt
binaries — no action needed. If other native compiled dependencies are
present, verify they have ARM64 support.

### 1.6 SST/OpenNext Note (Outcome A Only)

If Outcome A: explain the SST exception — the app surface uses SST/OpenNext
rather than Terraform because it's OpenNext's happy path. Everything else
(baseline, VPC, peripherals, security) is Terraform. Reference
`sst.config.ts` and `open-next.config.ts` (if M1 remediation was wired).

### 1.7 Peripheral Advisories

For each peripheral with a "keep alternative" in the mapping table (KV ->
Upstash, Postgres -> Neon), note the alternative explicitly so the founder
can make an informed choice.

---

## Step 2: Emit `MIGRATION_GUIDE.md`

Required sections:

### 2.1 Prerequisites

- AWS CLI installed and configured
- Terraform >= 1.5.0
- Docker (if Outcome B)
- DNS access (for cutover)
- Current Vercel database credentials (if Postgres migration)
- 30-60 min estimated time for small-tier migrations

### 2.2 Migration Timeline

Based on `estimation-infra.json.complexity_tier`:

| Tier   | Timeline                                                       |
| ------ | -------------------------------------------------------------- |
| small  | 1-2 days (provision + validate + cutover)                      |
| medium | 3-5 days (add database migration + parallel-run period)        |
| large  | 1-2 weeks (add compliance setup + multi-service orchestration) |

### 2.3 Step-by-Step Procedures

For each script in `scripts/`:

```
### Step N: <Script Purpose>
Script: `scripts/0M-<name>.sh`
Dry-run: `./scripts/0M-<name>.sh`
Execute: `./scripts/0M-<name>.sh --execute`
Verify: <how to confirm success>
Rollback: <how to undo>
```

Guide step numbers (`N`) count the scripts that actually exist, in order —
they do NOT have to match the script file numbers (`M`): the script set is
conditional (03 only with a Postgres peripheral, 04 only under Outcome B, 05
only under A/B), so gaps in the file numbering are normal. Note any gap
explicitly (e.g. "there is no 04 — that step is Outcome B only") so the founder
doesn't hunt for a missing file.

**Provisioning slot (not a script):** between the prerequisites step (01) and
the first mutating script (02), insert an unnumbered "Provision Infrastructure"
section covering `terraform apply` (per `terraform/README.md`'s bootstrap) and,
under Outcome A, `npx sst deploy` — the infrastructure must exist before
secrets/data migrate into it. Give it Verify and Rollback lines like any step.

### 2.4 Verification Checklist

- [ ] Terraform plan shows no unexpected changes
- [ ] All scripts pass in dry-run mode
- [ ] Health check endpoints respond (script 06)
- [ ] DNS resolves to new infrastructure
- [ ] SSL certificate valid
- [ ] Response times acceptable
- [ ] Error rates at or below Vercel baseline

### 2.5 Rollback Procedures

For each migration step, document the specific undo command:

- Terraform: `terraform destroy` (nuclear) or targeted resource removal
- DNS: revert CNAME to `cname.vercel-dns.com`
- Database: restore from RDS final snapshot
- Secrets: `aws secretsmanager delete-secret --force-delete-without-recovery`

### 2.6 Go/No-Go Gates

Define decision points:

- **Pre-cutover gate:** All scripts pass dry-run, terraform plan clean,
  health endpoints reachable, database migrated and validated
- **Cutover gate:** DNS TTL lowered 24h ago, monitoring in place, rollback
  procedure tested
- **Post-cutover gate:** 30-min monitoring window clean, error rates <=
  Vercel baseline, all health checks passing

---

## Step 3: Emit `README.md` (Top-Level in $MIGRATION_DIR)

```markdown
# Vercel-to-AWS Migration — {project_name}

**Recommendation:** Outcome {A|B|C|stay}
**Complexity:** {small|medium|large}
**Estimated AWS cost:** ~${balanced}/mo (Balanced tier)

## Artifacts

| Directory/File          | Purpose                                                              |
| ----------------------- | -------------------------------------------------------------------- |
| `terraform/`            | Production-ready Terraform (apply to provision AWS resources)        |
| `scripts/`              | Numbered migration scripts (run in order)                            |
| `MIGRATION_GUIDE.md`    | Step-by-step migration procedures with rollback                      |
| `estimation-infra.json` | Full cost breakdown (three tiers)                                    |
| `migration-report.html` | Complete assessment with Coupling Score and findings                 |
| `scenarios/`            | Optional what-if workshop snapshots (included in the report when ≥2) |
| `recommendation.json`   | Decision traceability (which rule fired and why)                     |

## Quick Start

1. Review `MIGRATION_GUIDE.md` prerequisites
2. Run `scripts/01-validate-prerequisites.sh`
3. `cd terraform && terraform init && terraform plan`
4. Follow the numbered scripts in `MIGRATION_GUIDE.md`

## Cost Tiers (estimated monthly)

| Tier         | Monthly          | Notes                               |
| ------------ | ---------------- | ----------------------------------- |
| Premium      | ~${premium}      | Multi-AZ, higher HA                 |
| **Balanced** | **~${balanced}** | What this Terraform generates       |
| Optimized    | ~${optimized}    | Graviton + Spot + reserved capacity |

All dollar figures are estimated monthly costs from `estimation-infra.json`.
```

**Dollar-figure labeling rule:** Every `$` figure must be adjacent to
"estimated monthly" (or carry the qualifier in context). Never present a raw
number without the "estimated" qualifier.

---

## Output Contribution for Parent Orchestrator

`terraform/README.md`, `MIGRATION_GUIDE.md`, `README.md`.

---

## Scope Boundary

**This fragment covers documentation generation ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Terraform resources or HCL code (those are other fragments' jobs)
- Migration script content (that's `generate-scripts.md`'s job)
- Assessment or recommendation logic

**Your ONLY job: emit documentation. Nothing else.**
