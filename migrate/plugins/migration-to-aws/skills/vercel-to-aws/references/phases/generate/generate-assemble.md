---
_assemble: generate-assemble
_of_phase: generate
_reads:
  - baseline (terraform/baseline.tf)
  - terraform (terraform/main.tf, terraform/variables.tf, terraform/outputs.tf, terraform/vpc.tf, terraform/security.tf, terraform/.gitignore, terraform/terraform.tfvars.example)
  - compute-opennext (sst.config.ts, terraform/cdn.tf) - when fired
  - compute-fargate (terraform/compute.tf, terraform/cdn.tf) - when fired
  - compute-lambda (terraform/compute.tf) - when fired
  - peripherals (terraform/database.tf, terraform/cache.tf, terraform/storage.tf, terraform/scheduling.tf) - conditional per peripheral
  - scripts (scripts/01-06*.sh)
  - docs (MIGRATION_GUIDE.md, README.md, terraform/README.md)
_produces:
  - generation-warnings.json
---

# Generate Phase: Assembler

> Validates the complete artifact set from all fragments, confirms mutual
> exclusion of compute fragments, writes `generation-warnings.json`, runs
> the completion gate, and emits `HANDOFF_OK`. This is the SINGLE creator
> of `generation-warnings.json`.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Confirm At-Most-One Compute Fragment Fired

Verify that at most ONE of `compute-opennext`, `compute-fargate`,
`compute-lambda` produced output. This should be structurally impossible
given the mutually exclusive `_when` triggers in `generate.md`'s frontmatter,
but this assembler double-checks as defense in depth.

If somehow two or more produced output, this is a BUG — halt and surface a
diagnostic rather than merging (combining SST with a from-scratch Fargate
stack, or two compute.tf files, is explicitly forbidden).

Exception: if `recommendation.json.outcome == "stay"`, ZERO compute fragments
fire — this is correct and expected.

---

## Step 2: Confirm Outcome C Never Gets App-Surface Hosting

If `recommendation.json.outcome == "C"`: confirm that NO `sst.config.ts` was
produced AND no `terraform/compute.tf` contains full-app Fargate hosting
(only backend-scoped compute). The Next.js app itself remains on Vercel under
Outcome C.

If this check fails (an app-surface artifact appeared under Outcome C), this
is a BUG — halt and surface a diagnostic.

---

## Step 3: Write `generation-warnings.json`

This file is ALWAYS written (even when empty):

```json
{
  "phase": "generate",
  "timestamp": "<ISO 8601>",
  "warnings": []
}
```

Populate `warnings` with entries for any service from
`estimation-infra.json.projected_costs.breakdown` that does NOT have a
corresponding Terraform resource or script:

```json
{
  "service": "<service_name>",
  "reason": "No Terraform resource mapping available for this service",
  "action": "Manual provisioning required — see MIGRATION_GUIDE.md"
}
```

Common cases that legitimately land here:

- **Under Outcome "stay":** compute services are NOT generated (expected —
  the app stays on Vercel); list them as "not generated — app remains on
  Vercel per recommendation"
- **Edge Config -> SSM Parameter Store:** no standalone Terraform resource
  needed (configuration values are managed via the AWS console or CLI);
  note this as "managed via CLI/console, not Terraform"
- **Env vars -> Secrets Manager:** handled by `scripts/02-migrate-secrets.sh`,
  not Terraform; note as "handled by migration script"

---

## Step 4: Cross-Reference Check

For every service in `estimation-infra.json.projected_costs.breakdown`:

1. Check if a Terraform resource exists for it in the generated `terraform/`
   directory, OR
2. Check if it's listed in `generation-warnings.json.warnings[]`, OR
3. Check if it's handled by a script in `scripts/`

If a service is in NONE of these three places, this is a gap — add it to
`generation-warnings.json.warnings[]` with an appropriate reason before
proceeding.

---

## Step 5: No-Placeholder-Token Scan

Scan all `.tf` files in `$MIGRATION_DIR/terraform/` for `{{VARIABLE}}`
patterns. Every configurable value MUST use `var.*` references declared in
`variables.tf` — not placeholder tokens.

The S3 backend block in `main.tf` is an exception (backend blocks cannot
reference variables) — those use TODO-style comments with actual values in
`terraform.tfvars.example`, which is the documented pattern.

If any `{{...}}` token is found outside the backend block, halt and fix it
before proceeding.

---

## Step 6: Validate the Terraform (best-effort, never blocks)

Static checks first (no tooling required — perform them by reading the files):

1. **Syntax**: every `.tf` file is syntactically valid HCL
2. **Reference integrity**: every `resource`/`module` reference resolves to a
   declaration within the generated configuration
3. **Variable completeness**: every `var.*` reference has a corresponding
   `variable` block in `variables.tf`
4. **Output references**: every `output` references a declared resource
   attribute

Then, if a `terraform` binary is available, run in `$MIGRATION_DIR/terraform/`:

```
terraform init -backend=false && terraform validate
```

(`-backend=false` skips S3 backend configuration — validation does not need
state access, only provider schemas.)

- **Validate passes** → record nothing (a pass is not a warning) and move on.
- **Validate FAILS** → append the error to
  `generation-warnings.json.warnings[]` as
  `{ "service": "terraform_validate", "reason": "<first error line(s)>", "action": "Fix before terraform plan — see terraform validate output" }`
  and continue to the Completion Gate. A validate failure is a warning the
  founder must see, not a generation halt.
- **Cannot run** (no Terraform binary, or `init` fails for network/registry
  reasons) → append
  `{ "service": "terraform_validate", "reason": "validation skipped: <binary missing | provider download failed>", "action": "From a network-connected shell: cd terraform/ && terraform init && terraform validate" }`
  and continue. Same degraded-offline convention as the heroku/gcp generate
  phases: the configuration SHOULD pass `terraform validate` with network
  access; absence of tooling must never block generation.

---

## Completion Gate

Run the checks declared in `generate.md`'s `_postconditions`:

1. All mandatory files exist: `terraform/main.tf`, `terraform/variables.tf`,
   `terraform/outputs.tf`, `terraform/baseline.tf`, `terraform/vpc.tf`,
   `terraform/security.tf`, `terraform/.gitignore`,
   `terraform/terraform.tfvars.example`, `terraform/README.md`,
   `MIGRATION_GUIDE.md`, `README.md`, `generation-warnings.json`.
2. `terraform/main.tf` has valid provider configuration with
   `hashicorp/aws ~> 5.80`; `terraform/variables.tf` declares at least
   `aws_region`, `project_name`, `environment`, `migration_id`.
3. At least one compute domain file exists (`terraform/compute.tf` or
   `terraform/cdn.tf`) beyond the core files — OR
   `recommendation.json.outcome` is `"stay"` (in which case no compute is
   expected).
4. Mutual exclusion confirmed (Step 1).
5. `MIGRATION_GUIDE.md` has Prerequisites and Verification sections;
   `README.md` lists the artifacts.
6. No `{{PLACEHOLDER}}` tokens in `.tf` files (Step 5).
7. Every estimated service is accounted for (Step 4).

**On any failure:** emit exactly:

```
GATE_FAIL | phase=generate | check=<failing check number> | reason=<details>
```

Do NOT modify artifacts to force a pass. Do NOT update `.phase-status.json`.

**On all-pass:** emit exactly:

```
HANDOFF_OK | phase=generate | artifacts=terraform/,scripts/,MIGRATION_GUIDE.md,README.md,generation-warnings.json
```

Then update `.phase-status.json`: mark `phases.generate` `"completed"`, set
`current_phase` to `report`, update `last_updated`.

---

## Scope Boundary

**This assembler covers validation, `generation-warnings.json`, and the
completion gate ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Generating any Terraform, scripts, or documentation (those are the
  fragments' jobs)
- Re-running the recommendation or estimate logic
- Silently merging conflicting compute fragment outputs

**Your ONLY job: validate, warn, gate, hand off.**
