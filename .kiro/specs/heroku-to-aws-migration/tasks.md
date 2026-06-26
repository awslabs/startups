# Implementation Plan: heroku-to-aws Migration Skill

## Overview

Build the `heroku-to-aws` migration skill within the existing `migration-to-aws` plugin at `migrate/plugins/migration-to-aws/skills/heroku-to-aws/`. The skill follows the same 6-phase architecture as the sibling `gcp-to-aws` skill (Discover → Clarify → Design → Estimate → Generate → Feedback) using a flat resource model, Terraform-based discovery (primary) with billing data supplementation, deterministic mapping tables, and shared plugin infrastructure. The skill is designed as a full platform exit tool — Heroku is in sustaining engineering (KTLO) and the default intent is complete departure. No Heroku Platform API calls are made. Implementation uses JavaScript (ESM) with fast-check for property-based testing.

## Tasks

-
  1. [x] Skill scaffold and SKILL.md orchestrator
  - [x] 1.1 Create skill directory structure and SKILL.md
    - Create `heroku-to-aws/` directory under `migrate/plugins/migration-to-aws/skills/`
    - Create `SKILL.md` with name, description, trigger phrases, philosophy section (including KTLO platform exit framing), definitions, context loading rules, and 6-phase routing table
    - Philosophy section SHALL declare: default intent is full exit from Heroku; no EB, no App Runner, no indefinite hybrid as recommended outcomes; hybrid is interim cutover only with required exit date
    - Create `references/phases/` subdirectories: `discover/`, `clarify/`, `design/`, `estimate/`, `generate/`, `feedback/`
    - Create `references/design-refs/` directory for mapping tables
    - Create `references/shared/` symlink or path reference to the shared infrastructure in gcp-to-aws
    - _Requirements: 1.1, 1.4, 1.5, 17.1, 17.2, 17.5, 19.1, 19.2_

  - [x] 1.2 Implement phase status state machine and handoff gates
    - Create `references/phases/discover/discover.md` phase orchestrator stub with state transitions
    - Implement phase-status validation logic: predecessor must be `completed` before `in_progress`
    - Implement GATE_FAIL halt behavior (retain `in_progress`, surface diagnostic)
    - Implement unrecoverable error behavior (revert to `pending`, preserve prior phases)
    - Reference `shared/schema-phase-status.md` and `shared/handoff-gates.md` for protocol
    - _Requirements: 1.2, 1.3, 1.5, 1.7, 1.8, 17.1, 17.2_

-
  2. [x] Checkpoint - Ensure scaffold structure is correct
  - Ensure all tests pass, ask the user if questions arise.

-
  3. [x] Discovery phase — Terraform and billing
  - [x] 3.1 Implement Terraform discovery module (`discover-terraform.md`)
    - Create `references/phases/discover/discover-terraform.md`
    - Implement `.tf` file scanning for `heroku_*` resource types: `heroku_app`, `heroku_addon`, `heroku_formation`, `heroku_domain`, `heroku_config_association`, `heroku_pipeline`, `heroku_space`
    - Extract resource type, resource name, and key configuration attributes for each `heroku_*` resource
    - Implement Cedar/Fir generation inference from Terraform resource attributes (space generation field, app stack)
    - Set `heroku_generation` to `unknown` and append `generation_unresolved` when generation cannot be determined
    - Implement pipeline detection from `heroku_pipeline` resources
    - Implement private space detection from `heroku_space` resources including peering configuration
    - Handle parse errors gracefully: set confidence to `reduced`, record which files failed, continue
    - _Requirements: 2.1, 2.2, 2.5, 2.6, 2.7, 10.1, 10.3, 10.4, 12.1, 12.2, 12.4_

  - [x] 3.2 Implement Procfile and app.json parsing
    - Implement Procfile parser extracting all process types (web, worker, release, clock, custom) and start commands
    - Implement app.json parser extracting add-ons, environment variables, formation defaults, and buildpack config
    - Implement parse error handling: record warning per-app, continue processing
    - _Requirements: 2.3, 2.4, 2.8_

  - [x] 3.3 Implement multi-source reconciliation logic
    - Implement conflict resolution: Terraform values win for conflicting fields when Procfile/app.json provide overlapping data
    - Record all discovery sources used in metadata `discovery_sources` array
    - Implement confidence determination: `full` when Terraform-only or all sources consistent, `reduced` when parse errors occur
    - Merge supplementary data from Procfile/app.json into Terraform-discovered resources
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 3.4 Implement billing discovery (`discover-billing.md`)
    - Create `references/phases/discover/discover-billing.md`
    - Implement parsing of Heroku Dashboard invoices and Enterprise CSV billing exports
    - Build billing profile: total monthly cost, billing period, currency, per-resource line items
    - Implement per-app cost breakdown extraction (dyno, add-on, platform charges) when available
    - Implement graceful degradation: if no billing data, proceed with Terraform inventory only; if parse fails, log warning and skip
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [x] 3.5 Implement inventory assembly and `heroku-resource-inventory.json` output
    - Assemble flat resource array with required fields: `resource_id`, `resource_type`, `heroku_app`, `config`
    - Group resources by `heroku_app` field; unassociable resources get `heroku_app: "unassociated"`
    - Include metadata section: discovery_timestamp, total_apps_discovered, per-app status, discovery_sources, confidence
    - Include billing_profile, terraform_secondary, and per-app generation/diagnostic fields
    - Ensure NO clustering fields (`cluster_id`, `creation_order_depth`, `edges`, `dependencies`, `must_migrate_together`)
    - _Requirements: 2.6, 16.1, 16.2, 16.4, 16.5_

  - [x]* 3.6 Write property test for Procfile parsing (Property 2)
    - **Property 2: Procfile parsing extracts all process types**
    - Generate random valid Procfiles with 1+ process type declarations; verify all types and commands extracted; round-trip equivalence
    - **Validates: Requirements 2.3**

  - [x]* 3.7 Write property test for app.json extraction (Property 3)
    - **Property 3: app.json extraction completeness**
    - Generate random valid app.json manifests; verify all declared sections (add-ons, env vars, formation defaults, buildpacks) appear in output
    - **Validates: Requirements 2.4**

  - [x]* 3.8 Write property test for inventory schema conformance (Property 4)
    - **Property 4: Inventory schema conformance**
    - Generate random resource sets from Terraform/Procfile/billing sources; verify metadata section completeness and every resource entry has `resource_id`, `resource_type`, `heroku_app`, `config`
    - **Validates: Requirements 2.6, 16.1, 16.4**

  - [x]* 3.9 Write property test for Terraform conflict resolution (Property 5)
    - **Property 5: Terraform conflict resolution — Terraform values always win**
    - Generate random pairs of Terraform vs Procfile/app.json values for same field; verify Terraform value retained and conflict recorded in metadata
    - **Validates: Requirements 3.1**

  - [x]* 3.10 Write property test for flat resource model invariant (Property 12)
    - **Property 12: Flat resource model invariant**
    - Generate random inventories; verify resources array is flat, no forbidden fields exist, resources processed in input order, same app shares identical `heroku_app` value
    - **Validates: Requirements 16.1, 16.2, 16.3, 16.4**

-
  4. [x] Checkpoint - Discovery phase complete
  - Ensure all tests pass, ask the user if questions arise.

-
  5. [x] Clarify phase — Adaptive questions
  - [x] 5.1 Implement clarify engine (`clarify.md`)
    - Create `references/phases/clarify/clarify.md`
    - Implement 12–15 question set organized into 3 batches (≤5 per batch), presented sequentially
    - Implement question categories: target AWS region, compliance, availability posture, migration approach, environment naming, database HA, database migration method, Redis HA, VPC subnet IDs, DNS strategy, containerization status, Fir intent, maintenance window, log retention, cost optimization
    - Implement migration approach question for ALL stacks with Postgres: `full_cutover` (default) or `interim_cutover_data_first` — not gated to Fir-only
    - Implement database migration method question with options: `pg_dump_restore`, `dms`, `bucardo`, `wal_g` — with size-based recommendation logic (derive estimated size from postgres plan table, allow user override; <10GB → pg_dump_restore, >10GB → dms, zero-downtime → bucardo/wal_g)
    - Implement DMS limitation note: when `dms` is selected, record that CDC/continuous replication is not available with Heroku Postgres (no REPLICATION role)
    - Implement containerization status question with options: `containerized`, `buildpack_only`, `partial`
    - Implement interim cutover handling: when selected, require `target_exit_date` (ISO 8601), emit KTLO platform risk warning in preferences.json
    - Implement fast-path mode: < 5 apps, no Private Spaces, no Kafka → reduce to 3–5 questions, apply defaults for skipped
    - Implement "use defaults for the rest" shortcut with `source: "default"` recording
    - Implement input validation: reject invalid responses with valid options list, re-prompt same question
    - Implement conditional Fir intent question (include only if Fir-generation apps detected) — covers compute destination only: `exit_heroku` or `self_managed_eks_ecs` (interim cutover timing is handled by migration_approach question, not Fir intent)
    - Implement Private Space subnet ID question (format: `subnet-xxxxxxxxxxxxxxxxx`, 1–6 values) with re-prompt on invalid format
    - Implement VPC ID question when peering detected but VPC ID not available in Terraform configuration
    - Produce `preferences.json` artifact conforming to plugin schema (same as gcp-to-aws) with new fields: `migration_approach`, `migration_method`, `containerization_status`, `interim_cutover`, `target_exit_date`, `ktlo_warning`
    - Follow Clarify completion protocol: phase-status update, artifact registration
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 9.2, 9.3, 9.6, 10.2, 19.3, 19.4, 20.1, 20.2, 21.1_

  - [x]* 5.2 Write property test for Clarify question count and batching (Property 15)
    - **Property 15: Clarify question count and batching**
    - Generate random inventories (fast-path and full); verify 12–15 questions in ≤5 per batch for full, 3–5 for fast-path, Fir intent only when Fir detected
    - **Validates: Requirements 11.1, 11.2, 11.6**

-
  6. [x] Design phase — Mapping tables and logic
  - [x] 6.1 Create design reference tables
    - Create `references/design-refs/dyno-type-table.md` with all 7 dyno type mappings to Fargate CPU/memory
    - Create `references/design-refs/fast-path-table.md` with 13 add-on → AWS service deterministic mappings
    - Create `references/design-refs/postgres-plan-table.md` with Heroku Postgres plan → RDS/Aurora instance sizing
    - Create `references/design-refs/redis-plan-table.md` with Heroku Redis plan → ElastiCache node type sizing
    - Create `references/design-refs/kafka-plan-table.md` with Heroku Kafka plan → MSK broker instance/storage sizing
    - _Requirements: 4.2, 5.4, 6.2, 7.2, 8.1, 8.4_

  - [x] 6.2 Implement design engine core logic (`design.md`)
    - Create `references/phases/design/design.md`
    - Implement single-pass flat list processing: for each resource in input order, determine type and apply corresponding lookup table
    - Implement Fargate mapping: dyno type → CPU/memory via table, quantity → desired_count (0–100), web → include ALB, non-web → no ALB
    - Implement unrecognized dyno type rejection with error message
    - Implement empty Procfile rejection (no process types → error)
    - Implement Postgres mapping: plan tier → instance class (RAM/vCPU ≥ source), availability preference → RDS vs Aurora, connection pooling → RDS Proxy, storage ≥ source max
    - Implement unrecognized Postgres plan halt with error
    - Implement default availability preference (unset/unrecognized → `multi-az` + RDS + warning)
    - Implement Redis mapping: plan → node type (memory ≥ source), HA → Multi-AZ + failover, compatible engine version, in-transit encryption preservation
    - Implement Kafka mapping: plan → MSK broker type/storage (≥ source throughput/storage), preserve topology (topics, partitions, replication), minimum 2 brokers across 2 AZs
    - Implement Fast-Path Table matching: case-insensitive exact match → deterministic mapping (including composite multi-AWS mappings); no match → specialist gate ("Deferred — specialist engagement")
    - Implement partial match rejection (not exact case-insensitive → specialist gate)
    - Implement specialist gate record: addon name, plan, provider, reason, recommendation
    - Implement VPC design: peering detected → reference existing VPC/subnets; no peering → generate new VPC (CIDR, 2+ subnets across AZs, route table, IGW)
    - Implement Private Space security groups: inbound restricted to declared dependency CIDRs/ports only
    - Implement Cedar/Fir notation: no Fir-specific Terraform, include notation identifying Fir workloads as deferred
    - Implement Pipeline detect-only warning in design output
    - Produce `aws-design.json` artifact with services, deferred, warnings, vpc_design sections
    - _Requirements: 4.1–4.7, 5.1–5.8, 6.1–6.6, 7.1–7.5, 8.1–8.5, 9.1, 9.4, 9.5, 10.5, 12.3, 16.3, 18.1, 18.2, 18.4_

  - [x]* 6.3 Write property test for Fargate mapping (Property 6)
    - **Property 6: Fargate mapping preserves dyno specifications**
    - Generate random formations with recognized dyno types; verify CPU/memory match table, desired_count = source quantity (0–100), ALB iff web
    - **Validates: Requirements 4.1, 4.2, 4.4, 4.5, 4.6**

  - [x]* 6.4 Write property test for Postgres mapping (Property 7)
    - **Property 7: Postgres mapping selects correct service and sizing**
    - Generate random Postgres add-ons × availability preferences; verify RDS vs Aurora selection, instance class ≥ source, storage ≥ source, RDS Proxy iff connection pooling
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6**

  - [x]* 6.5 Write property test for Redis mapping (Property 8)
    - **Property 8: Redis mapping preserves configuration**
    - Generate random Redis add-ons with config flags; verify node type memory ≥ source, Multi-AZ iff HA, compatible engine version, encryption-in-transit preservation
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5**

  - [x]* 6.6 Write property test for Kafka mapping (Property 9)
    - **Property 9: Kafka mapping preserves topology and meets sizing**
    - Generate random Kafka plans with topology; verify broker type/storage ≥ source, topic/partition/replication preserved, ≥2 brokers across ≥2 AZs
    - **Validates: Requirements 7.2, 7.3, 7.4**

  - [x]* 6.7 Write property test for Fast-Path matching and deferral (Property 10)
    - **Property 10: Fast-path table matching and deferral**
    - Generate random add-on names (exact matches in various cases, partial matches, unknowns); verify exact case-insensitive match → deterministic, partial → specialist gate, composite mappings include all AWS services
    - **Validates: Requirements 8.2, 8.3, 8.5, 18.1, 18.4**

  - [x]* 6.8 Write property test for Specialist gate records (Property 11)
    - **Property 11: Specialist gate records all required fields**
    - Generate random deferred add-ons; verify design artifact includes: addon name, plan, provider, reason, recommendation
    - **Validates: Requirements 18.2**

  - [x]* 6.9 Write property test for VPC design (Property 13)
    - **Property 13: VPC design matches peering state**
    - Generate random peering states × dependencies; verify existing VPC referenced when peering, new VPC has CIDR + 2 subnets + route table + IGW when no peering, security groups restrict to declared CIDRs/ports
    - **Validates: Requirements 9.1, 9.4, 9.5**

  - [x]* 6.10 Write property test for Fir exclusion (Property 14)
    - **Property 14: No Fir-specific Terraform generation**
    - Generate random inventories with Fir workloads; verify no ARM/Graviton targeting or CNB config in output, notation identifies Fir workloads as deferred
    - **Validates: Requirements 10.5**

-
  7. [x] Checkpoint - Design phase complete
  - Ensure all tests pass, ask the user if questions arise.

-
  8. [x] Estimate phase — Cost projection
  - [x] 8.1 Implement estimate engine (`estimate.md`)
    - Create `references/phases/estimate/estimate.md`
    - Implement per-resource monthly cost calculation using shared pricing MCP server
    - Implement pricing MCP fallback: 3 attempts × 10s timeout → fall back to pricing cache with `pricing_source: "cached_fallback"`
    - Implement unpriced resource handling: mark as `"unpriced"`, exclude from total, add to warnings
    - Implement total cost = sum of all individual resource costs (excluding unpriced)
    - Implement Heroku vs AWS side-by-side comparison when billing profile available (breakdown per app)
    - Produce `estimation-infra.json` artifact conforming to `schema-estimate-infra.md`
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 1.6, 17.3_

  - [x]* 8.2 Write property test for Estimate cost consistency (Property 16)
    - **Property 16: Estimate cost consistency**
    - Generate random designs with varying pricing availability; verify total = sum of individual costs, unpriced resources excluded from total and marked correctly
    - **Validates: Requirements 14.1, 14.5**

  - [x]* 8.3 Write property test for Complexity tier classification (Property 18)
    - **Property 18: Complexity tier classification**
    - Generate random complexity inputs (service count, spend, databases, stateful storage, availability, compliance, multi-region); verify Large-first evaluation, correct tier assignment per rules
    - **Validates: Requirements 17.5**

-
  9. [x] Generate phase — Terraform and migration artifacts
  - [x] 9.1 Implement Terraform generation (`generate-terraform.md`)
    - Create `references/phases/generate/generate-terraform.md`
    - Generate Terraform configurations for all designed AWS resources in `terraform/` directory within Migration_Dir
    - Generate Fargate task definitions, services, ALBs for compute resources
    - Generate RDS/Aurora instances, RDS Proxy when applicable
    - Generate ElastiCache clusters with proper HA/encryption configuration
    - Generate MSK clusters with broker counts, instance types, storage
    - Generate VPC resources: reference existing VPC/subnets when peering detected; create new VPC otherwise
    - Generate security groups with restricted inbound rules for Private Space migrations
    - Handle missing Terraform resource mappings: skip resource, log to `generation-warnings.json`
    - Ensure generated configurations pass `terraform validate`
    - _Requirements: 15.1, 15.4, 15.6, 9.1, 9.4_

  - [x] 9.2 Implement documentation and script generation (`generate-docs.md`)
    - Create `references/phases/generate/generate-docs.md`
    - Generate `MIGRATION_GUIDE.md` with:
      - Prerequisites section (including containerization prerequisites when `buildpack_only` or `partial`)
      - Containerization guidance section: Procfile→Dockerfile patterns for Ruby, Node.js, Python, Go, Java (only when containerization_status is `buildpack_only` or `partial`)
      - Data migration procedure section — method-specific based on `data.migration_method`:
        - `pg_dump_restore`: Full Heroku CLI cutover runbook (heroku maintenance:on, pg:backups:capture, pg:backups:download, pg_restore to target, verify, heroku addons:detach, heroku config:set DATABASE_URL, heroku maintenance:off)
        - `dms`: DMS replication instance setup, source/target endpoint config, migration task ("Migrate existing data" + "Full LOB mode"), pre-migration assessment, then same Heroku CLI cutover sequence; MUST include warning that DMS cannot do CDC/continuous replication with Heroku Postgres (no REPLICATION role granted)
        - `bucardo`: Setup requirements, EC2 infrastructure notes, Heroku CLI cutover sequence
        - `wal_g`: Setup requirements, EC2 infrastructure notes, Heroku CLI cutover sequence
      - Redis migration procedure (only when Redis in design)
      - Kafka migration procedure (only when Kafka in design)
      - Deferred add-ons as manual migration items
      - Post-Migration Lockdown section: disable public RDS/Aurora accessibility, verify backup configuration, confirm security group restrictions
      - Interim Database Exposure section (only when `interim_cutover_data_first`): configure RDS as publicly accessible during transition, download/configure RDS CA certificate, set DATABASE_URL with `sslmode=verify-full` + `sslrootcert`, enable `rds.force_ssl` parameter, note that public access MUST be disabled after app migration
      - Config var migration section: export Heroku config vars (`heroku config --json`), import to AWS Secrets Manager or SSM Parameter Store, reference in ECS task definition `secrets` block
      - Platform Risk callout (only when interim cutover selected): KTLO warning, bounded timeline
      - ECS Express Mode note: paragraph describing simplified deployment option, same Fargate + ALB cost model
      - Verification section
    - Omit data migration procedures for data store types not in design
    - Generate `README.md` listing all artifact files, purpose of each, and terraform apply command sequence
    - Generate database migration scripts with connection parameter placeholders for source/target
    - _Requirements: 15.2, 15.3, 15.5, 15.7, 18.3, 19.5, 20.3, 20.4, 20.5, 20.6, 20.7, 21.2, 21.3, 21.4_

  - [x]* 9.3 Write property test for Migration guide content (Property 17)
    - **Property 17: Migration guide content matches design**
    - Generate random designs with varying data stores + deferred add-ons; verify guide includes procedure for each present data store, omits absent ones, includes deferred add-ons as manual items
    - **Validates: Requirements 15.2, 15.7, 18.3**

-
  10. [x] Feedback phase — Reuse shared infrastructure
  - [x] 10.1 Implement feedback phase (`feedback.md`)
    - Create `references/phases/feedback/feedback.md`
    - Reference existing feedback phase orchestrator and payload encoder from shared infrastructure
    - Implement plan sharing with output compatible with feedback consumption pipeline
    - Complete phase-status update and handoff gate protocol
    - _Requirements: 17.4, 1.5_

-
  11. [x] Checkpoint - All phases implemented
  - Ensure all tests pass, ask the user if questions arise.

-
  12. [x] Phase transition and state machine property tests
  - [x]* 12.1 Write property test for phase transition validity (Property 1)
    - **Property 1: Phase transition validity**
    - Generate random phase names and predecessor states; verify `in_progress` only when predecessor `completed`, GATE_FAIL retains `in_progress`, unrecoverable error reverts to `pending` preserving prior completed phases
    - **Validates: Requirements 1.3, 1.7, 1.8, 17.2**

  - [x]* 12.2 Write property test for interim cutover constraints (Property 20)
    - **Property 20: Interim cutover requires target exit date and KTLO warning**
    - Generate random migration_approach values × random preferences; verify `interim_cutover_data_first` requires `target_exit_date` (valid ISO 8601), `interim_cutover: true`, and `ktlo_warning` populated; verify `full_cutover` does not require these fields
    - **Validates: Requirements 19.3, 19.5, 19.6, 20.8**

  - [x]* 12.3 Write property test for guide method/containerization matching (Property 21)
    - **Property 21: MIGRATION_GUIDE.md sections match migration_method and containerization_status**
    - Generate random migration_method × containerization_status combinations; verify pg_dump produces CLI runbook, dms produces DMS setup + CDC warning, bucardo/wal_g produce EC2 notes; verify buildpack_only/partial produce containerization section, containerized omits it
    - **Validates: Requirements 20.3, 20.4, 20.5, 20.6, 21.1, 21.2**

  - [x]* 12.4 Write property test for no EB/App Runner in design (Property 22)
    - **Property 22: No Elastic Beanstalk or App Runner in design output**
    - Generate random inventories with all resource types; verify aws-design.json services array never contains "Elastic Beanstalk", "App Runner", or "ECS Express Mode" as aws_service values
    - **Validates: Requirements 19.2, 19.7, 21.4**

-
  13. [x] Integration tests
  - [x]* 13.1 Write integration test for end-to-end phase flow
    - Test Discover → Clarify → Design flow with mock Terraform files
    - Verify artifact production at each phase, phase-status transitions, HANDOFF_OK signals between phases
    - _Requirements: 1.1, 1.2, 1.5_

  - [x]* 13.2 Write integration test for pricing MCP integration
    - Test pricing MCP server calls with mock MCP
    - Test fallback to pricing cache after 3 failed attempts
    - Verify `estimation-infra.json` output schema conformance
    - _Requirements: 14.3, 14.4, 17.3_

  - [x]* 13.3 Write integration test for Terraform validation
    - Test that generated Terraform configurations pass `terraform validate`
    - Test VPC-peering path produces data source references instead of new resources
    - _Requirements: 15.1, 15.4_

  - [x]* 13.4 Write integration test for handoff gate protocol
    - Test HANDOFF_OK flow between all phase pairs
    - Test GATE_FAIL halt behavior and phase re-entry with downstream reset
    - _Requirements: 1.3, 1.5, 1.7_

  - [x]* 13.5 Write unit tests for error handling edge cases
    - Test no Terraform files found → error message
    - Test Terraform parse errors → confidence `reduced`, continues
    - Test fast-path mode trigger conditions (< 5 apps, no Private Spaces, no Kafka)
    - Test "use defaults for the rest" behavior
    - Test billing data unavailable graceful degradation
    - Test Pipeline detect-only recording
    - Test empty Procfile rejection
    - Test subnet ID format validation (valid and invalid examples)
    - Test interim cutover requires target_exit_date
    - _Requirements: 2.5, 2.7, 11.2, 11.3, 13.3, 12.2, 4.7, 9.3, 19.3_

-
  14. [x] Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 22 universal correctness properties from the design document
- Unit/integration tests validate specific examples and edge cases
- Implementation language: JavaScript (ESM modules, Node.js built-in test runner, fast-check 3.22.0)
- Test files go in `migrate/plugins/migration-to-aws/tests/property/heroku/` and `migrate/plugins/migration-to-aws/tests/integration/heroku/`
- Skill files go in `migrate/plugins/migration-to-aws/skills/heroku-to-aws/`
- All reference file patterns follow the existing gcp-to-aws sibling skill structure

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.4", "6.1"] },
    { "id": 3, "tasks": ["3.3", "3.5", "3.6", "3.7"] },
    { "id": 4, "tasks": ["3.8", "3.9", "3.10", "5.1"] },
    { "id": 5, "tasks": ["5.2", "6.2"] },
    { "id": 6, "tasks": ["6.3", "6.4", "6.5", "6.6", "6.7", "6.8", "6.9", "6.10"] },
    { "id": 7, "tasks": ["8.1"] },
    { "id": 8, "tasks": ["8.2", "8.3", "9.1"] },
    { "id": 9, "tasks": ["9.2", "9.3"] },
    { "id": 10, "tasks": ["10.1"] },
    { "id": 11, "tasks": ["12.1", "12.2", "12.3", "12.4", "13.1", "13.2", "13.3", "13.4", "13.5"] }
  ]
}
```
