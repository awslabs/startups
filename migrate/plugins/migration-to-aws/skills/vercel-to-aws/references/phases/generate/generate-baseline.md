---
_fragment: baseline
_of_phase: generate
_contributes:
  - terraform/baseline.tf
---

# Generate Phase: Security Baseline (`baseline.tf`)

> Self-contained fragment. Always runs regardless of recommendation outcome —
> the security baseline is workload-independent and valuable even for a
> "stay" recommendation (the founder gets a secure AWS account posture for
> any peripheral services or future migrations).

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Compute Retention Days

Read `clarify-answers.json.Q8_compliance.answer`. Compute
`cloudtrail_retention_days` using this mapping, taking `max()` across all
declared values (use 90 if the answer is `"none"` or absent):

| Compliance        | Retention Days |
| ----------------- | -------------- |
| absent / `"none"` | 90             |
| `soc2`            | 365            |
| `pci`             | 365            |
| `hipaa`           | 2190           |
| `fedramp`         | 1095           |

---

## Step 2: Compute Budget Limit

Read `estimation-infra.json.projected_costs.aws_monthly_balanced`. Compute:

```
budget_limit = max(50, ceil(aws_monthly_balanced * 1.2))
```

If `estimation-infra.json` is missing or the balanced cost is unreadable, use
`50` and emit an inline comment noting that the projection was unavailable.

---

## Step 3: Emit `terraform/baseline.tf`

Write `$MIGRATION_DIR/terraform/baseline.tf` with the following structure:

### File Header

```hcl
# Security Baseline — Vercel-to-AWS Migration
#
# Account-wide security controls applied unconditionally. These resources are
# workload-independent — they secure the AWS account regardless of what else
# is deployed. Users who want to skip the baseline can delete this file
# before `terraform apply`.
#
# CloudTrail retention: <N> days (derived from compliance requirements).
# Budget alert: $<budget_limit>/month (120% of projected Balanced cost; $50 floor).

locals {
  cloudtrail_retention_days = <N>
  baseline_tags = {
    Component = "security-baseline"
  }
}
```

### Always-On Resources (emit in this order)

1. **`aws_account_alternate_contact.operations`** — TODO-email placeholder

   ```hcl
   # TODO: Replace with your operations contact email before applying.
   ```

2. **`aws_account_alternate_contact.billing`** — TODO-email placeholder

3. **`aws_account_alternate_contact.security`** — TODO-email placeholder

4. **`aws_iam_account_password_policy.baseline`**
   - `minimum_password_length = 14`
   - `password_reuse_prevention = 24`
   - `max_password_age = 90`
   - All four character-class requirements `true`
   - `hard_expiry = false`

5. **`aws_s3_account_public_access_block.baseline`** — all four flags `true`

6. **`aws_ebs_encryption_by_default.baseline`** — `enabled = true`

   ```hcl
   # defense-in-depth: encrypts all new EBS volumes by default.
   ```

7. **`aws_accessanalyzer_analyzer.baseline`** — `type = "ACCOUNT"`

8. **`aws_ec2_instance_metadata_defaults.baseline`**
   - `http_tokens = "required"` (IMDSv2 enforcement)
   - `http_put_response_hop_limit = 2`

   ```hcl
   # defense-in-depth: enforces IMDSv2 as the account-level default.
   ```

9. **`aws_cloudtrail.baseline`**
   - Multi-region, management events only
   - `enable_log_file_validation = true`

   ```hcl
   # WARNING: If you already have a CloudTrail trail in this region, this
   # resource will create a second trail. Review existing trails before applying.
   ```

10. **CloudTrail log S3 bucket** — `aws_s3_bucket.cloudtrail_logs` plus:
    - `aws_s3_bucket_public_access_block` (all four flags `true`)
    - `aws_s3_bucket_server_side_encryption_configuration` (AES256)
    - `aws_s3_bucket_versioning` (Enabled)
    - `aws_s3_bucket_lifecycle_configuration`:
      - STANDARD_IA transition: only if retention >= 90 days (at day 30)
      - GLACIER transition: only if retention >= 365 days (at day 90)
      - Expiration: at `local.cloudtrail_retention_days`
    - `aws_s3_bucket_policy`: restrict to CloudTrail service principal by
      `aws:SourceArn`

11. **`aws_budgets_budget.monthly_spend`**
    - `limit_amount = "<budget_limit>"`
    - Three `notification` blocks: 50%, 80%, 100% of `ACTUAL`
    - TODO-email placeholders on subscriber addresses

    ```hcl
    # Budget limit: max(50, ceil(projected_balanced * 1.2)) = $<N>.
    # $50 floor prevents alert noise on small deployments.
    # Edit limit_amount directly after apply if your spend expectations change.
    ```

12. **`aws_guardduty_detector.baseline`**
    - `enable = true`
    - `finding_publishing_frequency = "FIFTEEN_MINUTES"`

    ```hcl
    # defense-in-depth: 30-day free trial, then ~$2-25/mo depending on
    # event volume. Disable with `enabled = false` if cost is a concern.
    ```

---

## Step 4: Emit Remote-State Backend Infrastructure

Append to `baseline.tf`:

```hcl
# Remote state backend infrastructure
resource "aws_s3_bucket" "tfstate" {
  bucket = "${var.project_name}-${var.environment}-tfstate-${data.aws_caller_identity.current.account_id}"
  tags   = merge(local.baseline_tags, { Component = "terraform-state" })
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "tfstate_lock" {
  name         = "${var.project_name}-${var.environment}-tfstate-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"
  attribute {
    name = "LockID"
    type = "S"
  }
  tags = merge(local.baseline_tags, { Component = "terraform-state" })
}
```

---

## Step 5: Compliance-Conditional Section (If Applicable)

ONLY if `clarify-answers.json.Q8_compliance.answer` contains any of `soc2`,
`pci`, `hipaa`, `fedramp` (i.e. NOT `"none"`), append:

```hcl
########## Compliance-Conditional ##########
```

Then emit:

1. **`aws_iam_role.config`** + `aws_iam_role_policy_attachment` for
   `AWSConfigRole` managed policy

2. **`aws_config_configuration_recorder.baseline`**
   - `recording_group { all_supported = true, include_global_resource_types = true }`

   ```hcl
   # defense-in-depth: AWS Config continuous recording.
   # Cost: ~$0.003/configuration item (continuous); ~$0.012/CI for daily.
   ```

3. **`aws_config_delivery_channel.baseline`** — pointing at the Config S3 bucket

4. **`aws_config_configuration_recorder_status.baseline`** — `is_enabled = true`

5. **Config S3 log bucket** — same PAB/SSE/versioning/lifecycle pattern as
   CloudTrail log bucket (using same `local.cloudtrail_retention_days`)

6. **`aws_securityhub_account.baseline`**

   ```hcl
   # defense-in-depth: 30-day free trial, then ~$1-15/mo post-trial.
   ```

7. **`aws_securityhub_standards_subscription.fsbp`** — always emitted in this
   section (Foundational Security Best Practices)

8. **`aws_securityhub_standards_subscription.pci_dss`** — ONLY if `compliance`
   contains `pci`

Close with:

```hcl
########## End Compliance-Conditional ##########
```

Do NOT emit NIST 800-53 standards subscription even for `hipaa` or `fedramp`.

---

## Step 6: Lifecycle Rule Adjustment

- Omit the `STANDARD_IA` transition block when retention < 90 days.
- Omit the `GLACIER` transition block when retention < 365 days.
- Apply to both CloudTrail log bucket and (when emitted) Config log bucket.

---

## Output Contribution for Parent Orchestrator

`terraform/baseline.tf` — always contributed. This fragment also contributes a
partial dependency to `terraform/main.tf` (the S3 backend block references the
tfstate bucket created here — `generate-terraform.md` emits the backend block,
this fragment emits the bucket).

---

## Error Handling

| Error Category                                | Behavior                                                                        |
| --------------------------------------------- | ------------------------------------------------------------------------------- |
| `estimation-infra.json` missing or unreadable | Use $50 budget limit; add inline comment noting projection unavailable          |
| `clarify-answers.json.Q8_compliance` absent   | Treat as `"none"` — emit always-on resources only, no compliance section        |
| Compliance array contains unknown values      | Ignore unknown values; process only recognized ones (soc2, pci, hipaa, fedramp) |

---

## Scope Boundary

**This fragment covers `baseline.tf` generation ONLY.**

FORBIDDEN — Do NOT include ANY of:

- VPC, compute, or application-level resources (those are other fragments' jobs)
- Probing for existing account resources (collision risk is surfaced via comments)
- Modifying any input artifacts

**Your ONLY job: emit `terraform/baseline.tf` with the security baseline.
Nothing else.**
