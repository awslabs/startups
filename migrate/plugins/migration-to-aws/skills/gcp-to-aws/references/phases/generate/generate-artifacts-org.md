# Generate Phase: Organization & Guardrail Artifact Generation

> Loaded by generate.md when `preferences.json` contains `org_guardrails` AND (`generation-infra.json` exists OR `org_guardrails.org_structure == "multi-account"`).

**Execute ALL steps in order. Do not skip or optimize.**

## Overview

Generate organization structure and guardrail Terraform artifacts based on the user's clarify decisions stored in `preferences.json → org_guardrails`. This file branches on `org_guardrails.org_structure` to produce the correct artifacts for each profile.

## Prerequisites

Read from `$MIGRATION_DIR/`:

- `preferences.json` (REQUIRED) — Must contain `org_guardrails` object with `org_structure`, `guardrail_scps`, `chosen_by`, `recommendation`, and `user_override` fields

If `org_guardrails` is missing from `preferences.json`: **STOP**. Skip organization artifact generation entirely and proceed with other generate steps.

## Branch Selection

Read `preferences.json → org_guardrails.org_structure` and `org_guardrails.recommendation.value`:

| Priority | Condition                                                                                            | Branch   | Action                                                                  |
| -------- | ---------------------------------------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------- |
| 1        | `recommendation.value == "defer-multi-account"` AND `user_override == false`                         | Branch 3 | Generate NO org Terraform; docs handled by `generate-artifacts-docs.md` |
| 2        | `org_structure == "single-account"` AND `baseline.tf` does not exist (AI-only / billing-only routes) | —        | Generate nothing, skip entirely                                         |
| 3        | `org_structure == "single-account"` AND `baseline.tf` exists                                         | Branch 1 | Append permission boundary to `baseline.tf`                             |
| 4        | `org_structure == "multi-account"`                                                                   | Branch 2 | Generate standalone `organizations.tf`                                  |

**CRITICAL:** Evaluate in priority order (1 → 4). Branch 3 (defer) MUST be checked BEFORE Branch 1 (single-account), because both have `org_structure == "single-account"` — the defer path takes precedence when `recommendation.value == "defer-multi-account"` AND the user accepted it.

---

## Branch 1: Single-Account Path — Permission Boundary in `baseline.tf`

**Condition:** `org_structure == "single-account"` AND `$MIGRATION_DIR/terraform/baseline.tf` exists.

**When `baseline.tf` does not exist** (AI-only or billing-only routes): Skip this branch entirely. No permission boundary is generated — these routes don't produce infrastructure Terraform.

### Step 1.1: Append Permission Boundary to `baseline.tf`

Append the following resource block at the **end** of `baseline.tf`, after all existing resource blocks. Do not modify any existing resources in the file.

```hcl
# =============================================================================
# Optional — remove this resource and the output below before terraform apply
# if a permission boundary is not desired. This boundary prevents accidental
# disruption of security baseline services (CloudTrail, GuardDuty) and
# self-modification of the boundary policy itself.
# =============================================================================

resource "aws_iam_policy" "permission_boundary" {
  name        = "${var.project_name}-permission-boundary"
  description = "Permission boundary preventing disruption of security baseline services"
  path        = "/"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyCloudTrailDisruption"
        Effect = "Deny"
        Action = [
          "cloudtrail:StopLogging",
          "cloudtrail:DeleteTrail"
        ]
        Resource = "*"
      },
      {
        Sid    = "DenyGuardDutyDeletion"
        Effect = "Deny"
        Action = [
          "guardduty:DeleteDetector"
        ]
        Resource = "*"
      },
      {
        Sid    = "DenyGuardDutyDisable"
        Effect = "Deny"
        Action = [
          "guardduty:UpdateDetector"
        ]
        Resource = "*"
        Condition = {
          Bool = {
            "guardduty:Enable" = "false"
          }
        }
      },
      {
        Sid    = "DenySelfModification"
        Effect = "Deny"
        Action = [
          "iam:DeletePolicy",
          "iam:CreatePolicyVersion",
          "iam:DeletePolicyVersion"
        ]
        Resource = aws_iam_policy.permission_boundary.arn
      }
    ]
  })

  tags = {
    Component = "security-baseline"
    Purpose   = "permission-boundary"
  }
}

output "permission_boundary_arn" {
  description = "ARN of the permission boundary policy — attach to IAM roles to enforce baseline protections"
  value       = aws_iam_policy.permission_boundary.arn
}
```

### Step 1.2: Validation

- Confirm the permission boundary is the LAST resource in `baseline.tf`
- Confirm no other `.tf` file references `aws_iam_policy.permission_boundary`
- Confirm the output `permission_boundary_arn` is defined in `baseline.tf` (not `outputs.tf`)

---

## Branch 2: Multi-Account Path — `organizations.tf`

**Condition:** `org_structure == "multi-account"`

### Step 2.1: Generate `organizations.tf`

Create `$MIGRATION_DIR/terraform/organizations.tf` as a standalone, self-contained file. **No other generated `.tf` file may reference any resource defined in this file.**

Read `org_guardrails.guardrail_scps` to determine which SCP resources to include.

### Step 2.2: File Structure

Generate the complete file with the following structure:

```hcl
# This file is OPTIONAL. Delete before terraform apply if you don't want AWS
# Organizations. No other .tf files reference resources here.
#
# What this file creates:
#   - AWS Organizations with SERVICE_CONTROL_POLICY enabled
#   - Two OUs: Production and Development
#   - Two member accounts (placeholder emails — replace before apply)
#   - 0–3 Service Control Policies (based on your clarify selections)
#   - A permission boundary policy for IAM role attachment
#
# To remove: delete this file, run terraform plan — no errors will appear.

# =============================================================================
# AWS Organizations
# =============================================================================

resource "aws_organizations_organization" "main" {
  feature_set = "ALL"

  enabled_policy_types = [
    "SERVICE_CONTROL_POLICY"
  ]
}

# =============================================================================
# Organizational Units
# =============================================================================

resource "aws_organizations_organizational_unit" "production" {
  name      = "Production"
  parent_id = aws_organizations_organization.main.roots[0].id
}

resource "aws_organizations_organizational_unit" "development" {
  name      = "Development"
  parent_id = aws_organizations_organization.main.roots[0].id
}

# =============================================================================
# Member Accounts
#
# NOTE: Creating AWS accounts via Terraform is slow and email-bound.
# Many teams create the org manually first and use this HCL as a reference template.
# See MIGRATION_GUIDE.md for step-by-step instructions.
# =============================================================================

resource "aws_organizations_account" "production" {
  name      = "${var.project_name}-production"
  email     = "production@example.com" # TODO: Replace with a valid, unique email before terraform apply
  parent_id = aws_organizations_organizational_unit.production.id

  # Prevent Terraform from closing the account on resource destruction
  close_on_deletion = false

  tags = {
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

resource "aws_organizations_account" "development" {
  name      = "${var.project_name}-development"
  email     = "development@example.com" # TODO: Replace with a valid, unique email before terraform apply
  parent_id = aws_organizations_organizational_unit.development.id

  # Prevent Terraform from closing the account on resource destruction
  close_on_deletion = false

  tags = {
    Environment = "development"
    ManagedBy   = "terraform"
  }
}
```

### Step 2.3: Conditional SCP Generation

Read `org_guardrails.guardrail_scps` array. For each entry in the array, generate the corresponding SCP resource. Generate **only** the SCPs that appear in the array. Maximum 3 SCPs total.

#### SCP: "deny-leave-org"

If `"deny-leave-org"` is in `guardrail_scps`:

```hcl
# =============================================================================
# SCP: Deny Leave Organization
#
# Purpose: Prevents member accounts from removing themselves from the org.
# Customizable values: None — this SCP is a simple deny with no parameters.
# Impact: Member accounts cannot call organizations:LeaveOrganization.
# =============================================================================

resource "aws_organizations_policy" "deny_leave_org" {
  name        = "${var.project_name}-deny-leave-org"
  description = "Prevents member accounts from leaving the organization"
  type        = "SERVICE_CONTROL_POLICY"

  content = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyLeaveOrg"
        Effect    = "Deny"
        Action    = "organizations:LeaveOrganization"
        Resource  = "*"
      }
    ]
  })
}
```

#### SCP: "region-restrict"

If `"region-restrict"` is in `guardrail_scps`:

```hcl
# =============================================================================
# SCP: Region Restriction
#
# Purpose: Denies API calls in regions outside your target region, except for
#          services that are inherently global (IAM, Route 53, CloudFront, etc.).
# Customizable values:
#   - aws:RequestedRegion: change to allow additional regions (e.g., add a DR region)
#   - NotAction list: add global services your team uses that are not region-scoped
# Impact: Any API call to a regional service outside the allowed list is denied.
# =============================================================================

resource "aws_organizations_policy" "region_restrict" {
  name        = "${var.project_name}-region-restrict"
  description = "Restricts API calls to the target region, excluding global services"
  type        = "SERVICE_CONTROL_POLICY"

  content = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyOutsideTargetRegion"
        Effect    = "Deny"
        NotAction = [
          "iam:*",
          "route53:*",
          "cloudfront:*",
          "organizations:*",
          "sts:*",
          "support:*",
          "budgets:*",
          "wafv2:*",
          "shield:*",
          "health:*"
        ]
        Resource = "*"
        Condition = {
          StringNotEquals = {
            "aws:RequestedRegion" = [var.aws_region]
          }
        }
      }
    ]
  })
}
```

#### SCP: "deny-root"

If `"deny-root"` is in `guardrail_scps`:

```hcl
# =============================================================================
# SCP: Deny Root User Access
#
# Purpose: Blocks the root user in member accounts from performing most actions.
#          Root-required operations are excluded via NotAction so the root user
#          can still perform essential account recovery tasks.
# Customizable values:
#   - NotAction list: add or remove root-required operations as needed
#   - Current exclusions: MFA management, session tokens, account settings, support
# Impact: Root user in member accounts is denied all actions except those in NotAction.
# =============================================================================

resource "aws_organizations_policy" "deny_root" {
  name        = "${var.project_name}-deny-root"
  description = "Denies root user access in member accounts except essential recovery actions"
  type        = "SERVICE_CONTROL_POLICY"

  content = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyRootUserActions"
        Effect = "Deny"
        NotAction = [
          "iam:CreateVirtualMFADevice",
          "iam:EnableMFADevice",
          "iam:DeactivateMFADevice",
          "iam:DeleteVirtualMFADevice",
          "sts:GetSessionToken",
          "aws-portal:ModifyAccount",
          "support:*"
        ]
        Resource = "*"
        Condition = {
          StringLike = {
            "aws:PrincipalArn" = "arn:aws:iam::*:root"
          }
        }
      }
    ]
  })
}
```

### Step 2.4: SCP Attachments

For **each** SCP resource generated in Step 2.3, generate a corresponding policy attachment to the organization root:

```hcl
# =============================================================================
# SCP Attachments — applied to the organization root (affects all member accounts)
# =============================================================================
```

For "deny-leave-org":

```hcl
resource "aws_organizations_policy_attachment" "deny_leave_org" {
  policy_id = aws_organizations_policy.deny_leave_org.id
  target_id = aws_organizations_organization.main.roots[0].id
}
```

For "region-restrict":

```hcl
resource "aws_organizations_policy_attachment" "region_restrict" {
  policy_id = aws_organizations_policy.region_restrict.id
  target_id = aws_organizations_organization.main.roots[0].id
}
```

For "deny-root":

```hcl
resource "aws_organizations_policy_attachment" "deny_root" {
  policy_id = aws_organizations_policy.deny_root.id
  target_id = aws_organizations_organization.main.roots[0].id
}
```

### Step 2.5: Permission Boundary (Co-located)

Always append the permission boundary resource at the end of `organizations.tf` — regardless of whether the user opted out of the security baseline. Rationale: the `organizations.tf` file is independently deletable, so multi-account users who don't want the boundary can remove it from this file. The baseline opt-out only affects `baseline.tf` content; `organizations.tf` has its own lifecycle.

```hcl
# =============================================================================
# Permission Boundary
#
# Optional — remove this resource and the output below before terraform apply
# if a permission boundary is not desired. This boundary prevents accidental
# disruption of security baseline services (CloudTrail, GuardDuty) and
# self-modification of the boundary policy itself.
# =============================================================================

resource "aws_iam_policy" "permission_boundary" {
  name        = "${var.project_name}-permission-boundary"
  description = "Permission boundary preventing disruption of security baseline services"
  path        = "/"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyCloudTrailDisruption"
        Effect = "Deny"
        Action = [
          "cloudtrail:StopLogging",
          "cloudtrail:DeleteTrail"
        ]
        Resource = "*"
      },
      {
        Sid    = "DenyGuardDutyDeletion"
        Effect = "Deny"
        Action = [
          "guardduty:DeleteDetector"
        ]
        Resource = "*"
      },
      {
        Sid    = "DenyGuardDutyDisable"
        Effect = "Deny"
        Action = [
          "guardduty:UpdateDetector"
        ]
        Resource = "*"
        Condition = {
          Bool = {
            "guardduty:Enable" = "false"
          }
        }
      },
      {
        Sid    = "DenySelfModification"
        Effect = "Deny"
        Action = [
          "iam:DeletePolicy",
          "iam:CreatePolicyVersion",
          "iam:DeletePolicyVersion"
        ]
        Resource = aws_iam_policy.permission_boundary.arn
      }
    ]
  })

  tags = {
    Component = "security-baseline"
    Purpose   = "permission-boundary"
  }
}

output "permission_boundary_arn" {
  description = "ARN of the permission boundary policy — attach to IAM roles to enforce baseline protections"
  value       = aws_iam_policy.permission_boundary.arn
}
```

### Step 2.6: Validation

After generating `organizations.tf`, validate:

1. **No cross-file references:** Run a mental check — no other `.tf` file references `aws_organizations_organization.main`, `aws_organizations_organizational_unit.*`, `aws_organizations_account.*`, `aws_organizations_policy.*`, or `aws_organizations_policy_attachment.*`. The file is fully self-contained.
2. **SCP count:** Maximum 3 `aws_organizations_policy` resources. If `guardrail_scps` has more than 3 entries (should not be possible per schema), truncate to first 3 and emit a warning comment.
3. **SCP size:** Each SCP policy JSON document MUST be valid JSON ≤ 5,120 bytes. The SCPs defined above are well within this limit (~150–600 bytes each). If customization causes any to approach 5,120 bytes, emit a warning comment.
4. **Placeholder emails:** Both `aws_organizations_account` resources use `production@example.com` / `development@example.com` with TODO comments. Never use real email addresses.
5. **File deletability:** Deleting `organizations.tf` must not cause `terraform plan` to report errors on remaining files.

---

## Branch 3: Defer Path (Profile 3 — No Terraform)

**Condition:** `recommendation.value == "defer-multi-account"` AND `user_override == false` (user accepted the defer recommendation).

### Action

- Generate **NO** organization, SCP, or permission boundary Terraform resources
- Do NOT create `organizations.tf`
- Do NOT append anything to `baseline.tf` for organization purposes
- The education-only report section is handled by `generate-artifacts-docs.md` — this file takes no action for Profile 3

---

## Validation Rules (All Branches)

These rules apply globally and must be checked after generation regardless of branch:

| Rule                               | Check                                                                                                                                                                           |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `organizations.tf` isolation       | MUST NOT be referenced by any other generated `.tf` file. No `data` sources, no resource attribute references, no `terraform_remote_state` pointing at organizations resources. |
| SCP JSON validity                  | Each `aws_organizations_policy.content` value MUST be valid JSON ≤ 5,120 bytes                                                                                                  |
| SCP count limit                    | Maximum 3 `aws_organizations_policy` resources across the entire Terraform output                                                                                               |
| Placeholder emails                 | All `aws_organizations_account` resources MUST use `@example.com` placeholder emails with TODO comments                                                                         |
| Safe deletion                      | `organizations.tf` MUST be deletable without breaking `terraform plan` on remaining files                                                                                       |
| No permission boundary duplication | Permission boundary appears in EITHER `baseline.tf` (Branch 1) OR `organizations.tf` (Branch 2), never both                                                                     |
| Output consistency                 | `permission_boundary_arn` output is defined in whichever file contains the permission boundary resource                                                                         |

## Operational Notes

**Edge case — reused preferences on non-infra routes:** If `org_structure == "multi-account"` appears in preferences from a previous run but the current generate run has no `generation-infra.json` (AI-only or billing-only), `generate.md` still loads this file because the gate condition `org_structure == "multi-account"` is true. In this case, `organizations.tf` will be created without the rest of the infrastructure stack. This is acceptable — `organizations.tf` is self-contained — but unusual. The migration report should note that org setup runs independently from workload deployment.

When generating `organizations.tf`, the file MUST include this comment block near the account resources (already included in the template above in Step 2.2):

```
# NOTE: Creating AWS accounts via Terraform is slow and email-bound.
# Many teams create the org manually first and use this HCL as a reference template.
# See MIGRATION_GUIDE.md for step-by-step instructions.
```

This sets realistic expectations — many startups will use the generated HCL as documentation rather than running it directly through `terraform apply`.
