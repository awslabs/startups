# Implementation Plan: Organization & SCP Support

## Overview

This plan implements organization structure awareness and lightweight SCP support for the migration-to-aws plugin. The implementation creates markdown reference files that instruct the AI agent during clarify and generate phases, extends the preferences JSON schema, and adds conditional Terraform generation for AWS Organizations, SCPs, and IAM permission boundaries.

All "code" is markdown steering documents and Terraform HCL templates. The plugin lives at `migrate/plugins/migration-to-aws/`.

## Tasks

-
  1. [x] Create shared recommendation engine reference
  - [x] 1.1 Create `skills/shared/org-recommendation-engine.md`
    - Define the signal sources table (compliance, spend, complexity, workload shape, availability, fast-path eligibility)
    - Implement the profile assignment algorithm as a decision table the agent follows
    - Document the three profiles: single-account, prod-dev-split, defer-multi-account
    - Define confidence levels (high, medium, low) and when each applies
    - Include fallback behavior when signals are unavailable (default to single-account, confidence low)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

-
  1. [x] Create clarify-org reference files
  - [x] 2.1 Create `skills/gcp-to-aws/references/phases/clarify/clarify-org.md`
    - Define Category G firing rules (full migration, not fast-path, not AI-only)
    - Implement Q7.5 (Organization Structure) question format with pre-computed recommendation display
    - Include agent instructions to run recommendation engine BEFORE presenting question
    - Define answer → preferences mapping (A=recommendation, B=multi-account override, C=single-account default, Skip=single-account default)
    - Implement conditional Q7.6 (Guardrail SCP Selection) — fires only when Q7.5 resolves to multi-account
    - Define multi-select SCP options (A-E) and mapping to `guardrail_scps` array values
    - Include the "optional" note for Q7.5 stating most early-stage startups use single account
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 9.7, 9.8_

  - [x] 2.2 Create `skills/heroku-to-aws/references/phases/clarify/clarify-org.md`
    - Mirror the GCP skill's clarify-org.md content (identical question logic)
    - Adjust any skill-specific references (Heroku uses single clarify.md, not category files)
    - Ensure recommendation engine is loaded from shared location
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 9.7, 9.8_

-
  1. [ ] Modify clarify orchestrators for Category G integration
  - [ ] 3.1 Modify `skills/gcp-to-aws/references/phases/clarify/clarify.md`
    - Add Category G (Organization & Guardrails) to the firing rules table
    - Position Category G after Category A (Global/Strategic), before B/C/D/F
    - Add Q7.5 and Q7.6 to Batch 1 (Strategic Requirements) in batch planning
    - Add routing logic: load `clarify-org.md` when Category G fires
    - Add skip logic: when fast-path chosen OR AI-only, write single-account default to preferences and skip Category G
    - _Requirements: 2.3, 2.4, 2.5, 8.1, 8.7_

  - [ ] 3.2 Modify `skills/heroku-to-aws/references/phases/clarify/clarify.md`
    - Add Category G org questions inline (Heroku uses single clarify.md)
    - Position org questions after strategic questions (region/compliance/spend), before infrastructure
    - Add routing to load `clarify-org.md` reference
    - Add skip logic for fast-path and simple migrations
    - _Requirements: 2.3, 2.4, 2.5, 8.1, 8.7_

-
  1. [ ] Checkpoint — Clarify phase integration
  - Ensure all tests pass, ask the user if questions arise.

-
  1. [ ] Create generate-artifacts-org reference
  - [ ] 5.1 Create `skills/gcp-to-aws/references/phases/generate/generate-artifacts-org.md`
    - Define Branch 1: Single-account path — permission boundary in `baseline.tf`
      - IAM policy resource with Deny statement for security baseline disruption actions
      - Resource naming pattern: `${var.project_name}-permission-boundary`
      - Output the policy ARN as `permission_boundary_arn`
      - Include optional/removable comment block above resource
      - Condition: only when security baseline not opted out
    - Define Branch 2: Multi-account path — `organizations.tf` generation
      - `aws_organizations_organization` with `feature_set = "ALL"` and SCP enabled
      - Two OUs: Production and Development under root
      - One account per OU with placeholder email `<ou-name>@example.com` and TODO comment
      - Conditional SCP generation based on `guardrail_scps` array (0–3 SCPs)
      - SCP attachments to root OU
      - Permission boundary co-located in `organizations.tf`
      - First-line comment: file is optional and deletable
    - Define Branch 3: Defer path — no Terraform generated, education-only
    - Include SCP policy document templates (deny-leave-org, region-restrict, deny-root)
    - Include validation rules: no cross-file references, SCP ≤ 5120 bytes, max 3 SCPs
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 6.1, 6.2, 6.3, 6.4_

  - [ ] 5.2 Create `skills/heroku-to-aws/references/phases/generate/generate-artifacts-org.md`
    - Mirror the GCP skill's generate-artifacts-org.md (identical generation logic)
    - Adjust any skill-specific file path references if needed
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 6.1, 6.2, 6.3, 6.4_

-
  1. [ ] Modify generate orchestrators and artifact references
  - [ ] 6.1 Modify `skills/gcp-to-aws/references/phases/generate/generate.md`
    - Add conditional load of `generate-artifacts-org.md` when `org_guardrails` exists in preferences
    - Define branching: if `org_structure == "multi-account"` → load org generation, if single-account + security baseline → load for permission boundary only
    - _Requirements: 6.1, 9.10_

  - [ ] 6.2 Modify `skills/heroku-to-aws/references/phases/generate/generate.md`
    - Add conditional load of `generate-artifacts-org.md` when `org_guardrails` exists in preferences
    - Same branching logic as GCP skill
    - _Requirements: 6.1, 9.10_

  - [ ] 6.3 Modify `skills/gcp-to-aws/references/phases/generate/generate-artifacts-infra.md`
    - Add `organizations.tf` to the output structure table
    - Note conditional generation (only when multi-account)
    - _Requirements: 6.1, 6.4_

  - [ ] 6.4 Modify `skills/gcp-to-aws/references/phases/generate/generate-artifacts-docs.md`
    - Add "Organization & Guardrails" section to migration report template
    - Include recommendation summary, chosen profile, override explanation, cost impact, next steps
    - Add Organizations section to Terraform README.md template
    - Add multi-account additions to MIGRATION_GUIDE.md template (workload deployment map, per-account baseline, centralized services, when to revisit)
    - Define conditional inclusion rules per org_structure value
    - _Requirements: 7.1, 7.2, 7.3, 10.1, 10.2, 10.3, 10.4, 10.5, 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ] 6.5 Modify `skills/heroku-to-aws/references/phases/generate/generate-docs.md`
    - Add equivalent Organization & Guardrails documentation generation instructions
    - Include migration report section, README section, and guide additions
    - _Requirements: 7.1, 7.2, 7.3, 10.1, 10.2, 10.3, 10.4, 10.5, 11.1, 11.2, 11.3, 11.4, 11.5_

-
  1. [ ] Checkpoint — Generate phase integration
  - Ensure all tests pass, ask the user if questions arise.

-
  1. [x] Preferences JSON schema and validation
  - [x] 8.1 Document `org_guardrails` schema in the recommendation engine reference
    - Define the complete schema: `org_structure`, `guardrail_scps`, `chosen_by`, `recommendation`, `user_override`
    - Document valid value sets for each field
    - Document invariants: single-account → empty guardrail_scps, recommendation always present, no invalid values
    - Include validation rules the agent must enforce at write time
    - Include error handling: reject invalid writes, surface error, leave prior file unchanged
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

-
  1. [ ] Integration testing and validation
  - [ ]* 9.1 Create Terraform validation test fixtures
    - Create a test `organizations.tf` with all 3 SCPs for `terraform validate`
    - Create a test `organizations.tf` with no SCPs (option E)
    - Create a test `baseline.tf` with permission boundary appended
    - Verify each fixture passes `terraform validate`
    - _Requirements: 5.8, 6.1, 6.4_

  - [ ]* 9.2 Create JSON schema validation test
    - Define a JSON Schema for the `org_guardrails` object
    - Validate that all field constraints are enforceable (enums, array membership, no duplicates)
    - Test schema against valid examples (single-account, multi-account with SCPs, defer)
    - Test schema rejects invalid examples (unknown org_structure, duplicate SCPs, non-empty SCPs with single-account)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.8_

  - [ ]* 9.3 Create cross-file isolation test script
    - Write a bash script that greps generated Terraform for cross-references to `organizations.tf` resources
    - Verify no other `.tf` file references resources defined in `organizations.tf`
    - _Requirements: 6.1_

  - [ ]* 9.4 Create recommendation engine logic verification matrix
    - Document test cases for each signal combination → expected profile
    - Small/no-compliance/<$5K → single-account (high)
    - SOC2/Medium/$8K → prod-dev-split (high)
    - HIPAA/<$1K/Small → prod-dev-split (high)
    - FedRAMP/Large → defer-multi-account (high)
    - No compliance/$12K/distinct clusters → prod-dev-split (medium)
    - AI-only → single-account (high)
    - Fast-path eligible → single-account (high)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 9.5 Create SCP size validation check
    - Verify each SCP JSON document is ≤ 5,120 bytes
    - Include deny-leave-org (~150 bytes), region-restrict (~600 bytes), deny-root (~200 bytes)
    - _Requirements: 5.8_

-
  1. [ ] Final checkpoint — Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- This is a prompt-based AI agent skill plugin — "implementation" means creating/modifying markdown reference files that instruct the agent
- The plugin lives at `migrate/plugins/migration-to-aws/`
- New files: `skills/shared/org-recommendation-engine.md`, `skills/gcp-to-aws/references/phases/clarify/clarify-org.md`, `skills/heroku-to-aws/references/phases/clarify/clarify-org.md`, `skills/gcp-to-aws/references/phases/generate/generate-artifacts-org.md`, `skills/heroku-to-aws/references/phases/generate/generate-artifacts-org.md`
- Modified files: both skills' `clarify.md`, `generate.md`, `generate-artifacts-infra.md`, `generate-artifacts-docs.md`/`generate-docs.md`
- Terraform validation tests should use `terraform validate` (requires `terraform init` with no backend)
- The recommendation engine pseudocode in the design becomes a structured decision table in markdown that the AI agent evaluates at runtime

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "2.2", "8.1"] },
    { "id": 2, "tasks": ["3.1", "3.2", "5.1"] },
    { "id": 3, "tasks": ["5.2", "6.1", "6.2"] },
    { "id": 4, "tasks": ["6.3", "6.4", "6.5"] },
    { "id": 5, "tasks": ["9.1", "9.2", "9.3", "9.4", "9.5"] }
  ]
}
```
