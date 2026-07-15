# Requirements Document

## Introduction

This feature adds optional organization structure awareness and lightweight Service Control Policy (SCP) support to the migration-to-aws plugin. The goal is to help startups understand their account strategy options and, when appropriate, generate minimal guardrail SCPs — without mandating multi-account structure or heavy enterprise control frameworks. For single-account startups, lightweight alternatives (IAM permission boundaries) are offered instead.

The plugin computes a tailored organization recommendation from existing discover and clarify signals (compliance, spend, workload shape, availability, migration complexity) and presents it with plain-language reasons. The user confirms or overrides the recommendation. Artifact generation follows the final profile, not a raw menu selection. Three profiles exist: single-account (default ~70%), prod/dev split (actively recommended when signals warrant), and defer multi-account (education only, no Terraform).

The feature integrates into the existing 6-phase migration flow by adding a small set of clarify questions (Category G — Organization & Guardrails) and conditionally generating Terraform in the generate phase.

## Glossary

- **Clarify_Phase**: The existing Phase 2 of the migration assessment that asks adaptive questions to determine migration preferences
- **Generate_Phase**: The existing Phase 5 of the migration assessment that produces Terraform and migration artifacts
- **Organization_Module**: The new optional Terraform module containing AWS Organizations and SCP resources
- **Guardrail_Generator**: The component that selects and emits SCP or permission boundary Terraform based on clarify answers
- **Recommendation_Engine**: The logic that computes `org_recommendation` from discover + clarify signals before presenting Q7.5 to the user
- **Preferences_JSON**: The JSON file (`preferences.json`) written during Clarify that carries user decisions to downstream phases
- **SCP**: Service Control Policy — an AWS Organizations policy that sets permission guardrails for member accounts
- **Permission_Boundary**: An IAM policy that sets the maximum permissions for IAM entities within a single account
- **Profile_1_Single_Account**: Organization recommendation profile for ~70% of startups — single account, no org structure, permission boundaries only
- **Profile_2_Prod_Dev_Split**: Organization recommendation profile for startups needing account isolation — generates two OUs (Production/Development) with lightweight SCPs
- **Profile_3_Defer**: Organization recommendation profile for complex cases requiring a platform team — education-only report section, no Terraform generated

## Requirements

### Requirement 1: Organization Structure Clarify Questions

**User Story:** As a startup migrating to AWS, I want the migration tool to recommend an organization structure based on my existing signals, so that I get a tailored suggestion I can confirm or override without making a cold decision from scratch.

#### Acceptance Criteria

1. WHEN the Clarify_Phase reaches Category A (Global/Strategic) questions, THE Clarify_Phase SHALL present an organization structure question after Q7 (maintenance window) as question Q7.5
2. THE Clarify_Phase SHALL first compute an `org_recommendation` per Requirement 9, then present the question with the recommended profile pre-selected and plain-language reasons displayed, offering the following options: (A) Use recommendation (default) — pre-selected to the computed profile, (B) Separate prod and dev accounts — choose prod/dev split regardless of recommendation, (C) Not sure — stick with single account
3. WHEN the user selects option A (use recommendation), THE Clarify_Phase SHALL record the recommended profile's `org_structure` value in Preferences_JSON and set `user_override` to `false`
4. WHEN the user selects option B (separate prod/dev), THE Clarify_Phase SHALL record `org_structure: "multi-account"` in Preferences_JSON and set `user_override` to `true`
5. WHEN the user selects option C (not sure), THE Clarify_Phase SHALL default to `org_structure: "single-account"`, record `chosen_by: "default"`, and set `user_override` to `true` in Preferences_JSON
6. WHEN the user selects option B (separate prod/dev), THE Clarify_Phase SHALL present a follow-up question asking which guardrail SCPs the user wants (multi-select allowed): (A) Deny leaving the organization, (B) Restrict to specific AWS regions, (C) Deny root user access in member accounts, (D) All of the above — recommended minimal set, (E) None — just the account structure
7. THE Clarify_Phase SHALL record selected SCP preferences in the `org_guardrails.guardrail_scps` array of Preferences_JSON

### Requirement 2: Adaptive Question Behavior

**User Story:** As a startup founder who runs everything in one AWS account, I want the migration tool to respect my choice and not push multi-account complexity, so that I get a migration plan appropriate for my stage.

#### Acceptance Criteria

1. THE Clarify_Phase SHALL present the organization structure question as optional and display a note adjacent to the question stating that most early-stage startups use a single account
2. WHEN the user skips the organization structure question by providing no selection and advancing to the next step, THE Clarify_Phase SHALL apply the default of `org_structure: "single-account"` without presenting organization-related follow-up questions including account separation, cross-account networking, or OU structure questions
3. WHEN the fast-path gate (Step 1.5) determines `eligible_for_clarify_fast_path == true`, THE Clarify_Phase SHALL skip the organization structure question entirely and apply the single-account default
4. WHILE the migration flow is classified as AI-only (containing exclusively AI/ML workloads with no infrastructure migration components), THE Clarify_Phase SHALL NOT present the organization structure question
5. WHEN the Clarify_Phase applies the single-account default through any path (skip, fast-path, or AI-only flow), THE Clarify_Phase SHALL exclude multi-account patterns including AWS Organizations setup, cross-account IAM roles, and account-level isolation from the resulting migration plan

### Requirement 3: Single-Account Guardrail Generation

**User Story:** As a startup running in a single AWS account, I want lightweight permission boundaries as guardrails, so that I get basic protection without needing AWS Organizations.

#### Acceptance Criteria

1. WHEN `org_structure` equals "single-account" AND the user has not opted out of security baseline generation, THE Guardrail_Generator SHALL generate an `aws_iam_policy` resource in `baseline.tf` that contains a Deny statement covering the following IAM actions: `cloudtrail:StopLogging`, `cloudtrail:DeleteTrail`, `guardduty:DeleteDetector`, `guardduty:UpdateDetector` (where `enable` is set to `false`), `iam:DeletePolicy`, `iam:CreatePolicyVersion`, and `iam:DeletePolicyVersion` scoped to the permission boundary policy's own ARN
2. WHEN `org_structure` equals "single-account", THE Guardrail_Generator SHALL NOT generate any resources of type `aws_organizations_organization`, `aws_organizations_organizational_unit`, `aws_organizations_account`, or `aws_organizations_policy`
3. WHEN the Guardrail_Generator generates a permission boundary resource in `baseline.tf`, THE Guardrail_Generator SHALL include a comment block immediately above the resource indicating that the permission boundary is optional and can be removed before `terraform apply`
4. WHEN the user opts out of the security baseline during clarify (existing behavior), THE Guardrail_Generator SHALL NOT generate any permission boundary resources
5. WHEN the Guardrail_Generator generates the permission boundary policy, THE Guardrail_Generator SHALL name the resource using the pattern `${var.project_name}-permission-boundary` and SHALL output the policy ARN as a Terraform output so that it can be referenced when attaching the boundary to IAM roles

### Requirement 4: Multi-Account Organization Generation

**User Story:** As a startup that wants separate prod/dev accounts, I want the migration tool to generate the AWS Organizations setup and minimal SCPs, so that I get a working multi-account structure without manual configuration.

#### Acceptance Criteria

1. WHEN `org_structure` equals "multi-account", THE Organization_Module SHALL generate an `organizations.tf` file in the Terraform output directory
2. WHEN `org_structure` equals "multi-account", THE Organization_Module SHALL generate an `aws_organizations_organization` resource with `feature_set = "ALL"` and enabled policy types including `SERVICE_CONTROL_POLICY`
3. WHEN `org_structure` equals "multi-account", THE Organization_Module SHALL generate exactly two organizational units: "Production" and "Development"
4. THE Organization_Module SHALL NOT generate OU-per-workload-cluster structures; the "defer multi-account" profile (Profile 3 per Requirement 9) SHALL produce a report section only and no Terraform organization resources
5. THE Organization_Module SHALL generate exactly one `aws_organizations_account` resource per organizational unit, using the format `<ou-name-lowercase>@example.com` as the placeholder email address and including a TODO comment instructing the user to replace the email with a valid unique address before running `terraform apply`

### Requirement 5: Lightweight SCP Generation

**User Story:** As a startup with multiple accounts, I want minimal, startup-friendly SCPs applied to my organization, so that I get meaningful guardrails without the overhead of a full Control Tower deployment.

#### Acceptance Criteria

1. WHEN the user selected guardrail option A (deny leaving org), THE Guardrail_Generator SHALL generate an SCP containing a Deny statement for the `organizations:LeaveOrganization` action
2. WHEN the user selected guardrail option B (region restriction), THE Guardrail_Generator SHALL generate an SCP containing a Deny statement for all actions in regions outside the target region determined in Q1, with exceptions for global services (IAM, Route 53, CloudFront, Organizations, STS)
3. WHEN the user selected guardrail option C (deny root usage), THE Guardrail_Generator SHALL generate an SCP containing a Deny statement for all actions when the principal is the root user, excluding the following root-required actions: password recovery, account closure, support plan changes, and enabling/disabling MFA on the root account
4. WHEN the user selected guardrail option D (all of the above), THE Guardrail_Generator SHALL generate all three SCPs from criteria 1, 2, and 3 as separate `aws_organizations_policy` resources
5. WHEN the user selected guardrail option E (none), THE Guardrail_Generator SHALL NOT generate any SCP resources but SHALL still generate the Organizations structure from Requirement 4
6. THE Guardrail_Generator SHALL attach each generated SCP to the root organizational unit using `aws_organizations_policy_attachment` resources
7. THE Guardrail_Generator SHALL include a comment block in each SCP Terraform resource describing the policy's purpose and listing which values can be modified by the user
8. THE Guardrail_Generator SHALL produce each SCP policy document as valid JSON that does not exceed 5,120 bytes and SHALL output each SCP as a syntactically valid `aws_organizations_policy` Terraform resource
9. THE Guardrail_Generator SHALL generate a maximum of three SCPs total per organization; no additional SCPs SHALL be generated beyond the three defined guardrail options

### Requirement 6: Terraform Output Structure

**User Story:** As a developer reviewing generated migration artifacts, I want organization and SCP Terraform to be in a dedicated file separate from the security baseline, so that I can easily review and optionally remove it.

#### Acceptance Criteria

1. WHEN any organization or SCP resources are generated, THE Generate_Phase SHALL place them in a file named `organizations.tf` in the Terraform output directory, and SHALL NOT include any resource references from other generated `.tf` files to resources defined in `organizations.tf`
2. WHEN only a permission boundary is generated (single-account path), THE Generate_Phase SHALL append the permission boundary resource block at the end of the `baseline.tf` file, after all other resource blocks in that file
3. WHEN both organization/SCP resources and a permission boundary are generated (multi-account path), THE Generate_Phase SHALL place the permission boundary resource block in `organizations.tf` alongside the organization and SCP resources
4. THE Generate_Phase SHALL include a comment on the first line of `organizations.tf` stating that the file is optional and can be deleted before running `terraform apply` without affecting other generated resources
5. THE Generate_Phase SHALL add an `## Organizations` section to the Terraform `README.md` that contains: a summary of which organization and SCP resources were generated, the reason they were included, and instructions for customizing or removing `organizations.tf`

### Requirement 7: Cost Estimation Integration

**User Story:** As a startup evaluating the migration plan, I want to understand that AWS Organizations and SCPs are free, so that I can make an informed decision about adopting multi-account structure.

#### Acceptance Criteria

1. WHEN `org_structure` equals "multi-account", THE Generate_Phase SHALL include a note in the cost estimation section of the migration report output stating that AWS Organizations and Service Control Policies incur no additional AWS charges
2. WHEN `org_structure` equals "multi-account", THE Generate_Phase SHALL include a note in the cost estimation section of the migration report output stating that each additional AWS account will incur independent resource costs and that per-account baseline services (GuardDuty, CloudTrail) must be budgeted as separate line items per account
3. WHEN `org_structure` equals "single-account", THE Generate_Phase SHALL NOT include any organization cost notes in the cost estimation output

### Requirement 8: Preferences JSON Schema Extension

**User Story:** As a downstream phase consuming clarify outputs, I want organization preferences stored in a consistent schema within preferences.json, so that Design and Generate phases can deterministically produce the correct artifacts.

#### Acceptance Criteria

1. THE Clarify_Phase SHALL write a top-level `org_guardrails` object in Preferences_JSON containing exactly the fields `org_structure`, `guardrail_scps`, `chosen_by`, `recommendation`, and `user_override`
2. THE Clarify_Phase SHALL record `org_structure` as a string drawn from the set {"single-account", "multi-account"}, `guardrail_scps` as an array of zero or more strings each drawn from the set {"deny-leave-org", "region-restrict", "deny-root"} with no duplicate values, and `chosen_by` as a string drawn from the set {"user", "default"}
3. THE Clarify_Phase SHALL record a `recommendation` object containing exactly three fields: `value` (a string drawn from the set {"single-account", "prod-dev-split", "defer-multi-account"}), `confidence` (a string drawn from the set {"high", "medium", "low"}), and `reasons` (an array of one or more human-readable explanation strings describing the signals that drove the recommendation)
4. THE Clarify_Phase SHALL record `user_override` as a boolean set to `true` when the user chose an option other than the computed recommendation, and `false` when the user accepted the recommendation
5. WHEN `org_structure` equals "single-account", THE Clarify_Phase SHALL set `guardrail_scps` to an empty array regardless of any prior guardrail selections
6. WHEN `org_structure` equals "multi-account" and the user selects one or more guardrail options from the set {"deny-leave-org", "region-restrict", "deny-root"}, THE Clarify_Phase SHALL record only the selected values in the `guardrail_scps` array
7. IF the user does not explicitly choose an `org_structure` value, THEN THE Clarify_Phase SHALL set `org_structure` to "single-account", `guardrail_scps` to an empty array, `chosen_by` to "default", and `user_override` to `true`
8. IF any field in the `org_guardrails` object contains a value outside its defined valid set at write time, THEN THE Clarify_Phase SHALL reject the write, surface an error indicating the invalid field and value, and SHALL leave any prior Preferences_JSON file unchanged

### Requirement 9: Tailored Organization Recommendations

**User Story:** As a startup migrating to AWS, I want the migration tool to compute an organization structure recommendation from my existing discover and clarify signals, so that I receive a tailored suggestion with plain-language reasoning rather than making a cold architectural decision.

#### Acceptance Criteria

1. WHEN the Clarify_Phase reaches Q7.5 (organization structure), THE Clarify_Phase SHALL compute an `org_recommendation` from existing discover and clarify signals BEFORE presenting the question to the user
2. THE Clarify_Phase SHALL derive the recommendation by evaluating the following signal table:

   | Signal                                 | Source                                         | Profile 1 (single-account) | Profile 2 (prod/dev split)                                    | Profile 3 (defer multi-account)                                    |
   | -------------------------------------- | ---------------------------------------------- | -------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------ |
   | Compliance (Q2)                        | `preferences.compliance`                       | None or GDPR-only          | SOC2, PCI, or HIPAA                                           | FedRAMP                                                            |
   | Spend (Q3 + billing + complexity tier) | `gcp_monthly_spend`, `migration-complexity.md` | <$5K/mo AND Small tier     | $5K–$20K with distinct prod/nonprod OR Medium+ tier           | N/A (does not independently trigger)                               |
   | Workload shape                         | Discover clusters, AI-only flag                | AI-only workloads          | Multiple distinct clusters with clear prod/nonprod separation | Many clusters (would imply full multi-account beyond plugin scope) |
   | Availability (Q6)                      | `preferences.availability`                     | single-az or multi-az      | multi-az-ha (mission-critical — supports isolation narrative) | N/A (does not independently trigger)                               |
   | Migration complexity                   | `migration-complexity.md`                      | Small                      | Medium or Large + compliance                                  | Large + FedRAMP (needs platform team)                              |

3. THE Clarify_Phase SHALL assign Profile 1 (single-account) as the default recommendation applying to approximately 70% of startups, matching when: complexity is Small, no compliance requirements (or GDPR-only), spend is below $5K/month, workloads are AI-only, fast-path eligible, or user has indicated uncertainty
4. THE Clarify_Phase SHALL assign Profile 2 (prod/dev split) as the recommendation when ANY of: complexity is Medium or above, compliance includes SOC2 or PCI or HIPAA, user explicitly requests account separation, or spend is $5K–$20K with distinct production and non-production workloads
5. THE Clarify_Phase SHALL assign Profile 3 (defer multi-account) when signals indicate the startup needs a platform team they do not have — specifically when: migration complexity is Large AND compliance includes FedRAMP, OR discover clusters suggest a full multi-account structure beyond plugin scope
6. WHEN Profile 3 (defer multi-account) is assigned, THE Clarify_Phase SHALL NOT generate any Terraform organization resources; THE Generate_Phase SHALL produce an education-only report section explaining multi-account benefits, prerequisites, and when to revisit
7. THE Clarify_Phase SHALL present the computed recommendation with one or more plain-language reasons (e.g., "Your SOC2 compliance and $8K/mo spend suggest separating prod and dev accounts for audit clarity")
8. THE Clarify_Phase SHALL default the Q7.5 question selection to the computed recommendation so the user can accept it with a single confirmation
9. THE Clarify_Phase SHALL record the full recommendation (value, confidence, reasons) and the user_override flag in Preferences_JSON per Requirement 8
10. THE Generate_Phase SHALL generate artifacts according to the final profile (recommendation if accepted, override if changed), not solely from the raw user selection letter

### Requirement 10: Coherent Migration Plan Integration

**User Story:** As a startup that chose the prod/dev split, I want the migration guide to explain how workloads map to accounts and what infrastructure duplicates per account, so that I have a clear deployment picture without guessing.

#### Acceptance Criteria

1. WHEN `org_structure` equals "multi-account", THE Generate_Phase SHALL include a "Workload Deployment Map" section in the migration guide explaining which workloads deploy to the Production account and which deploy to the Development account
2. WHEN `org_structure` equals "multi-account", THE Generate_Phase SHALL list per-account baseline services that duplicate in each account (GuardDuty, CloudTrail, AWS Budgets) and explain why duplication is necessary for isolation
3. WHEN `org_structure` equals "multi-account", THE Generate_Phase SHALL identify which services remain centralized in the management account (Organizations, consolidated billing, SCPs) and explain the centralization rationale
4. WHEN `org_structure` equals "multi-account", THE Generate_Phase SHALL include a "When to Revisit" section listing growth triggers that indicate the startup should re-evaluate their account strategy: Series A funding, first formal compliance audit, or monthly spend exceeding $10K
5. WHEN `org_structure` equals "single-account", THE Generate_Phase SHALL NOT include multi-account deployment mapping or duplication guidance in the migration guide

### Requirement 11: Migration Report Organization Section

**User Story:** As a startup reviewing the migration report, I want a dedicated "Organization & Guardrails" section summarizing the recommended and chosen profiles, so that stakeholders can understand the decision and its implications.

#### Acceptance Criteria

1. THE Generate_Phase SHALL include an "Organization & Guardrails" section in the migration report output regardless of which `org_structure` value was selected
2. THE Generate_Phase SHALL display in the Organization & Guardrails section: the recommended profile name and confidence level, the chosen profile name, and whether the user overrode the recommendation
3. WHEN the user overrode the recommendation (user_override equals true), THE Generate_Phase SHALL include a brief explanation of why the recommendation and chosen profile differ, derived from the recommendation reasons and the user's selection
4. THE Generate_Phase SHALL include a "Cost Impact" subsection within Organization & Guardrails that states: for single-account — no additional cost from org structure; for multi-account — per-account baseline service costs (GuardDuty, CloudTrail, Budgets) estimated as additional line items
5. THE Generate_Phase SHALL include a "Next Steps" subsection within Organization & Guardrails listing actionable items: for single-account — "revisit when you hit Series A / first audit / $10K/mo"; for multi-account — "replace placeholder emails in organizations.tf, run terraform apply for org setup before workload deployment"; for defer — "engage AWS Solutions Architect or platform engineering consultant"
