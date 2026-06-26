# Requirements Document

## Introduction

This document specifies the requirements for a new `heroku-to-aws` migration skill within the existing migration-to-aws plugin. The skill follows the same 6-phase architecture as the sibling `gcp-to-aws` skill (Discover → Clarify → Design → Estimate → Generate → Feedback) but handles Heroku-specific discovery, resource mappings, and migration patterns. The v1 scope covers the core Heroku services (Dynos, Postgres, Key-Value Store, Kafka) and top 15-20 add-on mappings, targeting startups and small teams migrating off Heroku to AWS.

**Platform Context (2026):** Salesforce has moved Heroku into sustaining engineering — stability and support only, no new investment. Enterprise contracts are no longer sold to new customers. This skill is designed as a **full platform exit tool**, not a neutral platform-swap utility. The default intent is complete departure from Heroku (compute, data, and add-ons) within a defined window. Hybrid patterns (DB on AWS, app on Heroku) are supported only as bounded interim cutover tactics, not as recommended end states.

## Glossary

- **Skill**: A self-contained migration workflow module within the migration-to-aws plugin that handles a specific source platform
- **Discovery_Engine**: The component responsible for inventorying Heroku resources via Terraform file scanning, billing data parsing, and optional Procfile/app.json extraction
- **Clarify_Engine**: The component that presents adaptive questions to gather migration preferences before design begins
- **Design_Engine**: The component that maps Heroku resources to AWS services and produces the architecture design artifact
- **Estimate_Engine**: The component that calculates projected AWS costs for the designed architecture
- **Generate_Engine**: The component that produces Terraform configurations, migration scripts, and documentation
- **Feedback_Engine**: The component that collects user feedback and encodes a shareable migration plan
- **Platform_API**: The Heroku Platform API (not used by this skill — discovery is Terraform-based; referenced here for context only as the API that exposes apps, formations, add-ons, and config-vars)
- **Procfile**: A Heroku-specific file declaring process types (web, worker, etc.) and their start commands
- **app_json**: The `app.json` manifest describing app metadata, add-ons, environment, and formation for Heroku Review Apps and Buttons
- **Formation**: A Heroku resource representing the set of dynos (process types, quantities, and sizes) running an app
- **Dyno**: A lightweight Linux container that runs a single process type in a Heroku app
- **Add_On**: A third-party service attached to a Heroku app (e.g., Papertrail, SendGrid, Heroku Postgres)
- **Private_Space**: A Heroku network-isolated environment with dedicated runtime and optional VPC peering to external networks
- **Cedar**: The current-generation Heroku platform runtime (Linux containers on shared infrastructure)
- **Fir**: The next-generation Heroku platform runtime (Kubernetes-based, ARM/Graviton, Cloud Native Buildpacks, running on AWS)
- **Fast_Path_Table**: A deterministic lookup table mapping Heroku resources to AWS services without rubric evaluation
- **Specialist_Gate**: A deferral mechanism for resources requiring expert engagement rather than automated mapping
- **Phase_Status**: The JSON state file tracking completion of each migration phase
- **Migration_Dir**: The run-specific directory under `.migration/` storing all artifacts for a single migration session
- **Dyno_Type_Table**: A lookup table mapping Heroku dyno types (standard-1x, standard-2x, performance-m, etc.) to CPU/memory specifications for Fargate task sizing
- **VPC_Peering**: A network connection between a Heroku Private Space and an external VPC (e.g., customer's existing AWS VPC)
- **KTLO**: Keep The Lights On — a sustaining engineering posture where a platform receives stability patches and support but no new feature investment. Salesforce moved Heroku to KTLO status, halting enterprise sales to new customers.
- **Interim_Cutover**: A bounded migration phase where the database has been migrated to AWS but the application temporarily remains on Heroku, with a hard exit date. Not a recommended end state.
- **ECS_Express_Mode**: AWS's simplified ECS deployment experience (successor to App Runner) that provides Heroku-like deploy simplicity with Fargate + ALB underneath. Documented as an optional deployment path, not a separate design target.

## Requirements

### Requirement 1: Skill Scaffold and Phase Architecture

**User Story:** As a plugin developer, I want the heroku-to-aws skill to follow the same 6-phase architecture as gcp-to-aws, so that it integrates seamlessly with the existing plugin infrastructure.

#### Acceptance Criteria

1. THE Skill SHALL implement the six phases in order: Discover, Clarify, Design, Estimate, Generate, Feedback
2. THE Skill SHALL reuse the existing Phase_Status schema (pending → in_progress → completed) and state machine logic from the migration-to-aws plugin
3. IF a phase's predecessor has not reached `completed` status, THEN THE Skill SHALL prevent that phase from transitioning to `in_progress` and SHALL signal GATE_FAIL to the user
4. THE Skill SHALL store all artifacts in the Migration_Dir using the same `.migration/[MMDD-HHMM]/` convention as the gcp-to-aws skill
5. THE Skill SHALL use the existing handoff gate protocol (HANDOFF_OK / GATE_FAIL) between phases
6. THE Skill SHALL invoke the same pricing MCP server endpoints as the gcp-to-aws skill and SHALL produce cost estimates in the same output format used by the existing Estimate framework
7. IF a phase encounters a GATE_FAIL signal, THEN THE Skill SHALL halt the pipeline, retain the failing phase's status as `in_progress`, and SHALL surface a diagnostic to the user identifying the phase and the gate condition that failed
8. IF a phase fails during execution due to an unrecoverable error, THEN THE Skill SHALL revert that phase's status to `pending`, SHALL preserve any artifacts written by prior completed phases, and SHALL surface a diagnostic identifying the failed phase and the error category

### Requirement 2: Heroku Terraform-Based Discovery

**User Story:** As a migration user who manages Heroku via Terraform, I want the skill to discover my resources from Terraform files, so that I get a complete inventory without needing to provide a Heroku API token.

#### Acceptance Criteria

1. WHEN `.tf` files containing `heroku_*` resource types are found in the workspace directory tree, THE Discovery_Engine SHALL extract all apps, formations (dyno types, quantities, sizes), add-ons (name, plan, provider), domains, config associations, pipelines, and spaces from the Terraform resource definitions
2. THE Discovery_Engine SHALL extract at minimum the following Terraform resource types when present: `heroku_app`, `heroku_addon`, `heroku_formation`, `heroku_domain`, `heroku_config_association`, `heroku_pipeline`, `heroku_space`
3. WHEN a Procfile is present in the workspace, THE Discovery_Engine SHALL parse it to identify all declared process types (web, worker, release, clock, or any custom type) and their start commands
4. WHEN an app.json manifest is present, THE Discovery_Engine SHALL extract declared add-ons, environment variables, formation defaults, and buildpack configuration
5. IF no `.tf` files containing `heroku_*` resource types are found in the workspace, THEN THE Discovery_Engine SHALL stop discovery and present an error message indicating that Heroku Terraform files are required for discovery
6. THE Discovery_Engine SHALL produce a `heroku-resource-inventory.json` artifact in the Migration_Dir containing all discovered apps, formations, add-ons, and config associations, with a metadata section that includes the discovery timestamp, total apps discovered, discovery sources used, and confidence level
7. IF Terraform files contain parse errors that prevent extraction of some resources, THEN THE Discovery_Engine SHALL set confidence to `reduced`, record which files failed to parse, and continue discovery for the remaining parseable files
8. IF a Procfile or app.json contains syntax errors that prevent parsing, THEN THE Discovery_Engine SHALL record a warning for that app in the inventory indicating which file failed to parse and continue processing the remaining app resources

### Requirement 3: Multi-Source Discovery Reconciliation

**User Story:** As a migration user with multiple data sources (Terraform, Procfile, app.json, billing), I want the skill to reconcile information across sources, so that the inventory is complete and consistent.

#### Acceptance Criteria

1. WHEN both Terraform resource definitions and Procfile/app.json describe the same logical resource (matched by app name and resource type), THE Discovery_Engine SHALL retain the Terraform attribute values for any conflicting fields and note the conflict in the inventory metadata
2. THE Discovery_Engine SHALL record all discovery sources used in the inventory metadata `discovery_sources` array, drawn from the set: `terraform`, `procfile`, `app_json`, `billing`
3. IF only Terraform files are available (no Procfile, no app.json, no billing), THEN THE Discovery_Engine SHALL proceed with Terraform-only discovery and set confidence to `full`
4. IF Terraform files plus supplementary sources (Procfile, app.json, billing) are all available, THEN THE Discovery_Engine SHALL merge information from all sources with Terraform values taking precedence for conflicting fields

### Requirement 4: Core Service Mapping — Dynos to Fargate

**User Story:** As a migration user, I want my Heroku dynos mapped to appropriately-sized AWS Fargate tasks, so that my compute workloads run on equivalent capacity.

#### Acceptance Criteria

1. THE Design_Engine SHALL map each Heroku Formation (dyno process type) to exactly one AWS Fargate task definition, producing a task definition that specifies CPU units, memory allocation, and container image reference for each process type
2. WHEN mapping dyno sizing, THE Design_Engine SHALL use the Dyno_Type_Table to translate Heroku dyno types (standard-1x, standard-2x, performance-m, performance-l, private-s, private-m, private-l) to Fargate CPU and memory allocations
3. IF a dyno type is not present in the Dyno_Type_Table, THEN THE Design_Engine SHALL reject the mapping and report an error message indicating the unsupported dyno type name
4. THE Design_Engine SHALL preserve the dyno quantity as the Fargate service desired count, accepting values from 0 to 100 inclusive
5. WHEN a Procfile declares a `web` process type, THE Design_Engine SHALL include an Application Load Balancer in the design for that service
6. WHEN a Procfile declares a process type whose name is not `web`, THE Design_Engine SHALL design that process type as a Fargate service without a load balancer
7. IF the Procfile declares no process types, THEN THE Design_Engine SHALL reject the input and report an error message indicating that at least one process type is required

### Requirement 5: Core Service Mapping — Heroku Postgres to RDS/Aurora

**User Story:** As a migration user, I want my Heroku Postgres databases mapped to the appropriate AWS PostgreSQL service, so that my data tier is properly migrated.

#### Acceptance Criteria

1. THE Design_Engine SHALL map Heroku Postgres add-ons to either RDS PostgreSQL or Aurora PostgreSQL based on the availability preference from the Clarify phase
2. WHEN the availability preference is single-az or multi-az, THE Design_Engine SHALL select RDS PostgreSQL
3. WHEN the availability preference is multi-az-ha or multi-region, THE Design_Engine SHALL select Aurora PostgreSQL
4. THE Design_Engine SHALL map the Heroku Postgres plan tier to an RDS/Aurora instance class that meets or exceeds the RAM and vCPU capacity of the source Heroku plan tier (hobby, standard, premium, private, shield), selecting the smallest instance class that satisfies both constraints
5. WHEN the Heroku Postgres plan includes connection pooling, THE Design_Engine SHALL include RDS Proxy in the design
6. THE Design_Engine SHALL map the Heroku Postgres plan storage allocation to an RDS/Aurora storage configuration that meets or exceeds the source plan's maximum storage capacity
7. IF the availability preference is not set or contains an unrecognized value, THEN THE Design_Engine SHALL default to multi-az and select RDS PostgreSQL, and SHALL include a warning in the design output indicating the default was applied
8. IF the Heroku Postgres plan tier is not recognized, THEN THE Design_Engine SHALL halt mapping for that add-on and SHALL produce an error indicating the unrecognized plan tier

### Requirement 6: Core Service Mapping — Key-Value Store to ElastiCache

**User Story:** As a migration user, I want my Heroku Key-Value Store (Redis) mapped to Amazon ElastiCache, so that my caching and session data workloads continue to function.

#### Acceptance Criteria

1. THE Design_Engine SHALL map Heroku Key-Value Store (Redis) add-ons to Amazon ElastiCache for Redis
2. THE Design_Engine SHALL map the Heroku Redis plan tier to an ElastiCache node type whose available memory is equal to or greater than the memory limit of the source Heroku Redis plan
3. WHEN the Heroku Redis plan includes high availability, THE Design_Engine SHALL configure ElastiCache with Multi-AZ and automatic failover
4. THE Design_Engine SHALL select an ElastiCache Redis engine version that is compatible with the Redis version used by the source Heroku add-on
5. IF the source Heroku Redis plan has encryption in-transit enabled, THEN THE Design_Engine SHALL configure ElastiCache with in-transit encryption enabled
6. IF the Design_Engine cannot identify a compatible ElastiCache node type for the source Heroku Redis plan, THEN THE Design_Engine SHALL report an error indicating the unsupported plan and the reason no mapping could be determined

### Requirement 7: Core Service Mapping — Kafka to MSK

**User Story:** As a migration user, I want my Apache Kafka on Heroku mapped to Amazon MSK, so that my streaming workloads are properly migrated.

#### Acceptance Criteria

1. THE Design_Engine SHALL map Apache Kafka on Heroku add-ons to Amazon MSK
2. THE Design_Engine SHALL map each Heroku Kafka plan tier to an MSK broker instance type and storage allocation that meets or exceeds the throughput and storage capacity of the source plan
3. THE Design_Engine SHALL preserve topic count, partition count per topic, and replication factor from the Heroku Kafka plan in the MSK design
4. THE Design_Engine SHALL specify a minimum of 2 brokers spread across at least 2 availability zones in the MSK design
5. IF the Design_Engine encounters a Heroku Kafka plan tier that has no defined MSK mapping, THEN THE Design_Engine SHALL report an error indicating the unrecognized plan tier and the Kafka add-on identifier

### Requirement 8: Add-On Mapping via Fast-Path Table

**User Story:** As a migration user, I want common Heroku add-ons automatically mapped to AWS equivalents, so that I get a complete migration plan without manual research.

#### Acceptance Criteria

1. THE Design_Engine SHALL maintain a Fast_Path_Table containing deterministic mappings for at least 13 Heroku add-ons to AWS services, where each entry maps one add-on name to one or more AWS service equivalents
2. WHEN a discovered add-on's name matches an entry in the Fast_Path_Table using case-insensitive string comparison, THE Design_Engine SHALL apply that mapping with confidence level "deterministic" and include all mapped AWS services in the design output
3. IF a discovered add-on's name does not match any entry in the Fast_Path_Table, THEN THE Design_Engine SHALL mark that add-on as "Deferred — specialist engagement" and record it in the design warnings
4. THE Fast_Path_Table SHALL include at minimum: Papertrail → CloudWatch Logs, SendGrid → Amazon SES, Heroku Scheduler → Amazon EventBridge Scheduler, Memcachier → ElastiCache Memcached, Bucketeer → S3, CloudAMQP → Amazon MQ, Bonsai Elasticsearch → Amazon OpenSearch, Scout APM → CloudWatch + X-Ray, Rollbar → CloudWatch, New Relic → CloudWatch + X-Ray, Twilio → Amazon SNS (SMS), Cloudinary → S3 + CloudFront, Sentry → CloudWatch
5. WHEN a Fast_Path_Table entry maps a single add-on to multiple AWS services, THE Design_Engine SHALL include all listed AWS services as a composite mapping in the design output and assign a single "deterministic" confidence level to the group

### Requirement 9: Private Space and VPC Peering Handling

**User Story:** As a migration user with Heroku Private Spaces peered to an existing AWS VPC, I want the generated Terraform to reference my existing VPC instead of creating a new one, so that my network topology is preserved.

#### Acceptance Criteria

1. WHEN discovery finds an app running in a Heroku Private Space with existing VPC peering, THE Design_Engine SHALL reference the existing AWS VPC ID as a Terraform data source or variable in generated Terraform rather than creating a new VPC resource
2. WHEN the existing VPC subnet IDs are not available in the Terraform configuration, THE Clarify_Engine SHALL present one question asking the user to provide subnet IDs, accepting between 1 and 6 comma-separated subnet ID values in the format "subnet-xxxxxxxxxxxxxxxxx"
3. IF the user provides subnet IDs that do not match the expected format, THEN THE Clarify_Engine SHALL re-prompt the user with an error message indicating the expected subnet ID format
4. WHEN no Private Space peering is detected, THE Design_Engine SHALL generate a VPC configuration that includes a CIDR block, at least 2 subnets across separate availability zones, a route table, and an internet gateway
5. WHEN generating a VPC design for a Private Space migration, THE Design_Engine SHALL include security group rules that restrict inbound traffic to only the CIDR ranges and ports used by the application's declared dependencies and deny all other inbound traffic by default
6. IF discovery detects VPC peering but cannot retrieve the VPC ID from the Terraform configuration, THEN THE Clarify_Engine SHALL present one question asking the user to provide their existing AWS VPC ID

### Requirement 10: Cedar/Fir Generation Detection

**User Story:** As a migration user, I want the skill to detect whether my apps run on Cedar or Fir generation, so that the migration plan accounts for platform differences.

#### Acceptance Criteria

1. THE Discovery_Engine SHALL detect and record the Heroku generation for each app and space in the inventory, storing a `heroku_generation` field on each inventory entry with a value drawn from the set { `cedar`, `fir`, `unknown` }, inferred from Terraform resource attributes (e.g., `heroku_space` generation field, app stack attributes)
2. WHEN a Fir-generation app or space is detected, THE Clarify_Engine SHALL prompt the user to select exactly one compute migration intent from the following fixed set of options: exit the Heroku abstraction entirely (re-platform to ECS/Fargate) or move to self-managed EKS/ECS, and SHALL persist the selected option in preferences.json under the `global` object before proceeding to the next phase
3. IF the Discovery_Engine cannot determine the Heroku generation for an app or space from the available Terraform metadata, THEN THE Discovery_Engine SHALL set `heroku_generation` to `unknown` and SHALL append the value `generation_unresolved` to that entry's diagnostic reasons, and SHALL continue processing the remaining apps and spaces
4. THE Discovery_Engine SHALL record Cedar/Fir detection in the inventory with a `generation_action` field set to the value `detect_only`, indicating that no generation-specific Terraform or design logic is applied in v1
5. THE Design_Engine SHALL NOT generate Fir-specific Terraform artifacts (including ARM/Graviton instance targeting and CNB buildpack configuration) regardless of `heroku_generation` value, and SHALL include a notation in the design output identifying which workloads are Fir-generation, noting that Fir-specific generation is deferred to a future version, and noting that Fir workloads may already run on AWS infrastructure (potentially reducing compute migration lift) while still requiring exit from the Heroku control plane

### Requirement 11: Clarify Phase — Adaptive Questions

**User Story:** As a migration user, I want to answer a focused set of questions that tailor my migration plan, so that the design matches my operational requirements without overwhelming me.

#### Acceptance Criteria

1. THE Clarify_Engine SHALL present between 12 and 15 questions organized into batches of no more than 5 questions each, where each batch is presented only after all questions in the previous batch have been answered or defaulted
2. THE Clarify_Engine SHALL support a fast-path mode when the source stack contains fewer than 5 apps, no Private Spaces, and no Kafka, reducing the question set to between 3 and 5 questions and applying the defaults documented in the plugin's defaults configuration for all skipped questions
3. WHEN the user responds with "use defaults for the rest", THE Clarify_Engine SHALL apply the defaults documented in the plugin's defaults configuration for all remaining unanswered questions, SHALL record each defaulted answer with a `source` value of `default`, and SHALL complete the phase
4. WHEN all questions in the Clarify phase have been answered or defaulted, THE Clarify_Engine SHALL produce a `preferences.json` artifact in the Migration_Dir conforming to the same schema used by the gcp-to-aws skill, and SHALL not write the file until all required fields are populated
5. THE Clarify_Engine SHALL include questions covering: target AWS region (from a predefined list of valid AWS regions), compliance requirements (from a predefined set of compliance frameworks), availability posture (from a predefined set of availability tiers), migration approach (full cutover vs interim data-first), environment naming, database HA preference, database migration method, containerization status, and Fir intent (when applicable)
6. IF the source stack includes one or more Heroku Fir-generation apps, THEN THE Clarify_Engine SHALL include the Fir intent question; IF no Fir-generation apps are present, THEN THE Clarify_Engine SHALL skip the Fir intent question
7. IF the user provides a response that is not within the predefined valid options for a question, THEN THE Clarify_Engine SHALL reject the input, indicate the valid options, and re-prompt the same question without advancing to the next question
8. THE Clarify_Engine SHALL follow the same Clarify completion protocol as the gcp-to-aws skill, including phase-status update and artifact registration in the Migration_Dir

### Requirement 12: Pipeline and Review Apps Detection

**User Story:** As a migration user, I want the skill to detect my Heroku Pipelines and Review Apps configuration, so that CI/CD mapping can be addressed in the migration plan.

#### Acceptance Criteria

1. WHEN Heroku Pipelines are detected, THE Discovery_Engine SHALL record each pipeline in the inventory with its name, pipeline stages (review, development, staging, production), and the app name and stage assignment for each connected app
2. WHEN Heroku Pipelines or Review Apps are detected, THE Discovery_Engine SHALL record them with a "detect-only" status in the inventory and include them as a dedicated section in the migration report listing each pipeline, its stages, connected apps, and Review Apps enablement status
3. IF Pipeline or Review Apps entries are present in the inventory, THEN THE Design_Engine SHALL include a design warning stating that CI/CD mapping for the detected pipelines requires manual configuration outside the automated skill scope
4. IF pipeline or Review Apps detection fails due to a Terraform parse error or missing resource attributes, THEN THE Discovery_Engine SHALL record the detection failure in the inventory with the pipeline identifier and an error indication describing the failure reason, and continue processing remaining resources

### Requirement 13: Billing Discovery

**User Story:** As a migration user, I want the skill to capture my Heroku spend data, so that cost comparisons can be made between Heroku and the projected AWS architecture.

#### Acceptance Criteria

1. WHEN Heroku Dashboard invoice data or Enterprise CSV billing exports are available, THE Discovery_Engine SHALL parse them to build a billing profile containing at minimum: total monthly cost, billing period, currency, and a list of line items each associated with a resource name and cost amount
2. IF per-app cost breakdowns are available in the invoice detail, THEN THE Discovery_Engine SHALL extract the cost per app including dyno, add-on, and platform service charges as separate line items
3. IF no billing data is available, THEN THE Discovery_Engine SHALL proceed with discovery using Terraform inventory alone and record a limitation entry in the discovery output indicating that cost comparison will be limited to projected AWS costs only
4. IF billing data is present but cannot be parsed due to unrecognized format or missing required fields, THEN THE Discovery_Engine SHALL log a warning indicating the parse failure reason, skip billing profile generation, and continue discovery using Terraform inventory alone

### Requirement 14: Estimate Phase — Cost Projection

**User Story:** As a migration user, I want projected monthly AWS costs for my migrated architecture, so that I can compare them to my current Heroku spend.

#### Acceptance Criteria

1. THE Estimate_Engine SHALL calculate projected monthly AWS costs in USD for each resource in the design individually and as a total, using the shared pricing MCP server and pricing cache, and store the result in the `estimation-infra.json` artifact in the Migration_Dir
2. WHEN Heroku billing data is available from the Discovery phase billing profile, THE Estimate_Engine SHALL include a side-by-side comparison showing current Heroku monthly spend and projected AWS monthly spend broken down per app
3. THE Estimate_Engine SHALL produce an `estimation-infra.json` artifact following the same schema conventions as the gcp-to-aws skill
4. IF the pricing MCP server is unavailable after 3 attempts with a timeout of 10 seconds per attempt, THEN THE Estimate_Engine SHALL fall back to the pricing cache and add `pricing_source: "cached_fallback"` to the estimation artifact
5. IF pricing data for a resource is unavailable from both the pricing MCP server and the pricing cache, THEN THE Estimate_Engine SHALL mark that resource's cost as `"unpriced"` in the estimation artifact, exclude it from the total, and list it in a warnings array indicating the resource requires manual cost verification

### Requirement 15: Generate Phase — Terraform and Migration Artifacts

**User Story:** As a migration user, I want production-ready Terraform configurations and migration scripts generated for my AWS architecture, so that I can execute the migration with minimal manual effort.

#### Acceptance Criteria

1. THE Generate_Engine SHALL produce Terraform configurations for all designed AWS resources in a `terraform/` directory within the Migration_Dir, where the generated configurations pass `terraform validate` without errors
2. THE Generate_Engine SHALL produce a `MIGRATION_GUIDE.md` containing an ordered list of migration steps that includes a prerequisites section, a data migration procedure section covering each detected data store (Postgres, Redis, Kafka), and a verification section describing how to confirm each migration step succeeded
3. THE Generate_Engine SHALL produce a `README.md` that lists all generated artifact files, describes the purpose of each file, and provides the command sequence required to apply the Terraform configurations
4. WHEN Private Space peering to an existing VPC is detected, THE Generate_Engine SHALL generate Terraform that references the provided VPC ID and subnet IDs rather than creating new network resources
5. THE Generate_Engine SHALL include database migration scripts using `pg_dump`/`pg_restore` for Heroku Postgres migrations, including connection parameter placeholders for both source and target databases
6. IF a designed AWS resource has no supported Terraform resource mapping, THEN THE Generate_Engine SHALL skip that resource, log a warning entry in a `generation-warnings.json` file within the Migration_Dir, and continue generating the remaining resources
7. IF a data store type (Postgres, Redis, or Kafka) is not present in the designed architecture, THEN THE Generate_Engine SHALL omit the corresponding data migration procedure from the `MIGRATION_GUIDE.md` rather than including an empty or placeholder section

### Requirement 16: Flat Resource Model — No Clustering

**User Story:** As a plugin developer, I want the heroku-to-aws skill to use a simplified resource model without dependency graphs or clustering, so that the skill complexity matches Heroku's flat architecture.

#### Acceptance Criteria

1. THE Discovery_Engine SHALL produce a flat resource inventory as an array of resource entries without topological sorting, typed edges, depth calculation, or inter-resource dependency fields, where each entry contains at minimum: `resource_id`, `resource_type`, `heroku_app`, and `config`
2. THE Discovery_Engine SHALL NOT implement the clustering algorithm used by the gcp-to-aws skill, and SHALL NOT emit `cluster_id`, `creation_order_depth`, `edges`, `dependencies`, or `must_migrate_together` fields in its output
3. THE Design_Engine SHALL process resources as a flat list in input order with one deterministic mapping per resource type, and SHALL NOT perform multi-pass cluster-based design or vary mapping logic based on inter-resource relationships
4. THE Discovery_Engine SHALL group resources by Heroku app name using a `heroku_app` field on each resource entry, such that all resources belonging to the same Heroku application share an identical `heroku_app` value, while maintaining the flat array structure without nesting resources under app-level container objects
5. IF the Discovery_Engine encounters a resource that cannot be associated with exactly one Heroku app, THEN THE Discovery_Engine SHALL set the `heroku_app` field to the reserved value `unassociated` and SHALL include the resource in the flat inventory without discarding it

### Requirement 17: Reuse of Shared Plugin Infrastructure

**User Story:** As a plugin developer, I want the heroku-to-aws skill to reuse shared infrastructure from the plugin, so that effort is not duplicated and behavior remains consistent.

#### Acceptance Criteria

1. THE Skill SHALL reference the canonical handoff gate protocol file at `references/shared/handoff-gates.md` and SHALL implement the same HANDOFF_OK / GATE_FAIL format and phase re-entry rules defined in that file
2. THE Skill SHALL reference the canonical Phase_Status schema file at `references/shared/schema-phase-status.md` and SHALL validate phase transitions against the same state machine rules defined there
3. THE Skill SHALL invoke the same pricing MCP server endpoints as the gcp-to-aws skill for cost estimation and SHALL produce output conforming to the `schema-estimate-infra.md` schema
4. THE Skill SHALL reuse the existing Feedback phase orchestrator and payload encoder for plan sharing, producing output compatible with the same feedback consumption pipeline
5. THE Skill SHALL reference the canonical migration complexity tier definitions at `references/shared/migration-complexity.md` and SHALL apply the same tier classification logic (Small/Medium/Large) for timeline scaling

### Requirement 18: Specialist Gate for Unknown Add-Ons

**User Story:** As a migration user, I want unknown or complex add-ons flagged for specialist review rather than receiving incorrect automated mappings, so that my migration plan remains reliable.

#### Acceptance Criteria

1. WHEN a Heroku Marketplace add-on is not found in the Fast_Path_Table, THE Design_Engine SHALL apply the Specialist_Gate pattern, produce no automated AWS mapping for that add-on, and mark the add-on as "Deferred — specialist engagement" in the design output
2. THE Design_Engine SHALL record each deferred add-on in the design artifact with the following fields: add-on name, add-on plan, provider, reason for deferral, and a recommendation to engage the AWS account team for replacement selection
3. THE Generate_Engine SHALL include each deferred add-on in the MIGRATION_GUIDE.md as a manual migration item that lists the add-on name, current plan, and a note stating specialist consultation is required for AWS replacement selection
4. IF a discovered add-on's name partially matches a Fast_Path_Table entry but is not an exact case-insensitive match, THEN THE Design_Engine SHALL treat it as unmatched and apply the Specialist_Gate pattern rather than assuming a mapping

### Requirement 19: KTLO Platform Exit Philosophy

**User Story:** As a migration user on a platform in sustaining engineering, I want the skill to default to full exit from Heroku, so that I don't inadvertently remain dependent on a platform with no new investment.

#### Acceptance Criteria

1. THE Skill SHALL declare in its SKILL.md philosophy section that the default migration intent is full exit from Heroku — compute, data, and add-ons off the platform within a user-defined window
2. THE Skill SHALL NOT recommend Elastic Beanstalk, AWS App Runner (no longer accepting new customers as of April 2026), or indefinite continued use of Heroku as migration outcomes
3. WHEN the user selects the interim cutover option (data-first migration with application remaining on Heroku temporarily), THE Clarify_Engine SHALL require a `target_exit_date` value in ISO 8601 date format and SHALL emit a warning in `preferences.json` stating that the Heroku platform is in sustaining engineering and indefinite hybrid operation carries platform risk
4. IF the user selects `interim_cutover_data_first` as their migration approach, THEN THE Generate_Engine SHALL include in the MIGRATION_GUIDE.md a "Platform Risk" callout section stating that Heroku is in sustaining engineering mode, hybrid operation should be bounded to weeks not quarters, and a full compute migration should follow the data migration
5. THE Clarify_Engine SHALL present a migration approach question for ALL stacks that include Heroku Postgres, with options: `full_cutover` (migrate database and application together in one window) and `interim_cutover_data_first` (migrate database first, application remains on Heroku temporarily with a required exit date), and SHALL persist the selected value in `preferences.json` under `global.migration_approach`
6. THE Design_Engine SHALL NOT include Elastic Beanstalk or App Runner service types in the `aws-design.json` artifact under any circumstances

### Requirement 20: Database Migration Method Selection

**User Story:** As a migration user, I want the skill to recommend the appropriate database migration method based on my database size and downtime tolerance, so that I minimize risk and downtime during data migration.

#### Acceptance Criteria

1. THE Clarify_Engine SHALL present a database migration method question with the following options: `pg_dump_restore` (simplest, downtime required), `dms` (AWS Database Migration Service, shorter downtime for large databases), `bucardo` (trigger-based replication, near-zero downtime), and `wal_g` (WAL-based replication, minimal downtime for large databases)
2. THE Clarify_Engine SHALL derive an estimated database size from the Heroku Postgres plan tier using the postgres plan table's maximum storage capacity, and SHALL present this estimate to the user with an option to override with their known actual size; THE Clarify_Engine SHALL recommend `pg_dump_restore` when the estimated database size is under 10GB, `dms` when over 10GB with acceptable brief downtime, and `bucardo` or `wal_g` when near-zero downtime is required regardless of size
3. THE Generate_Engine SHALL produce data migration procedures in the MIGRATION_GUIDE.md that correspond to the selected migration method, including step-by-step instructions with Heroku CLI commands and AWS CLI/console commands with connection parameter placeholders
4. WHEN `pg_dump_restore` is selected, THE Generate_Engine SHALL include in the MIGRATION_GUIDE.md the full cutover runbook: `heroku maintenance:on`, `heroku pg:backups:capture`, `heroku pg:backups:download`, `pg_restore` to target, verification, `heroku addons:detach DATABASE`, `heroku config:set DATABASE_URL=<new_url>`, `heroku maintenance:off`
5. WHEN `dms` is selected, THE Generate_Engine SHALL include DMS replication instance setup, source/target endpoint configuration, migration task creation with "Migrate existing data" type and "Full LOB mode", pre-migration assessment enablement, and the same Heroku CLI cutover sequence for the final switchover; THE Generate_Engine SHALL include a warning that AWS DMS cannot perform continuous replication (CDC) with Heroku Postgres because Heroku does not grant the REPLICATION role required for logical replication — DMS is for one-time bulk data migration with a cutover window only
6. WHEN `bucardo` or `wal_g` is selected, THE Generate_Engine SHALL include a reference to the method's setup requirements, note that these methods require additional EC2 infrastructure, and provide the Heroku CLI cutover sequence for the final DNS/endpoint switchover
7. THE Generate_Engine SHALL include in all migration method procedures a "Post-Migration Lockdown" section instructing the user to disable public accessibility on the RDS/Aurora instance and verify backup configuration once the application has fully migrated off Heroku
8. WHEN the migration approach is `interim_cutover_data_first`, THE Generate_Engine SHALL include in the MIGRATION_GUIDE.md an "Interim Database Exposure" section that documents: configuring the RDS/Aurora instance as publicly accessible during the transition period, downloading and configuring the RDS CA certificate for SSL verification, setting `DATABASE_URL` with `sslmode=verify-full` and `sslrootcert` pointing to the RDS CA cert, requiring SSL connections on the RDS instance server-side (via `rds.force_ssl` parameter), and noting that public access MUST be disabled once the application has migrated off Heroku
9. WHEN a Clarify question asks for estimated database size and the user does not provide an override, THE Clarify_Engine SHALL use the postgres plan table's maximum storage capacity as the default estimate and record `source: "plan_derived"` for that value

### Requirement 21: Containerization Guidance and ECS Express Mode

**User Story:** As a migration user whose application is not yet containerized, I want guidance on containerizing my Heroku app for Fargate, so that I can complete the compute migration.

#### Acceptance Criteria

1. THE Clarify_Engine SHALL present a containerization status question asking whether the application already has a Dockerfile, with options: `containerized` (Dockerfile exists), `buildpack_only` (uses Heroku buildpacks, no Dockerfile), and `partial` (some services containerized, some not)
2. WHEN the containerization status is `buildpack_only` or `partial`, THE Generate_Engine SHALL include a "Containerization Prerequisites" section in the MIGRATION_GUIDE.md with guidance on creating a Dockerfile from the application's Procfile and buildpack configuration, including common patterns for Ruby, Node.js, Python, Go, and Java buildpacks
3. THE Generate_Engine SHALL include in the MIGRATION_GUIDE.md a paragraph noting ECS Express Mode as an optional simplified deployment path for teams wanting Heroku-like deploy simplicity, stating that the underlying cost model remains Fargate + ALB and no design changes are required
4. THE Generate_Engine SHALL NOT map any workloads to ECS Express Mode in the `aws-design.json` artifact — all compute workloads SHALL be mapped to standard Fargate task definitions regardless of containerization status
