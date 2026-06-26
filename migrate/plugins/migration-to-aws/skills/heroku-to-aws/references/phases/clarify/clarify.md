# Phase 2: Clarify Requirements

**Phase 2 of 6** — Ask adaptive questions before design begins, then interpret answers into ready-to-apply design constraints.

> **HARD GATE — Clarify before Design:** Do not load `references/phases/design/design.md` (or any later phase) until this phase finishes **and** `$MIGRATION_DIR/.phase-status.json` records `phases.clarify` as `"completed"`. Writing `preferences.json` without updating phase status is a protocol violation. If the user asks to skip questions, use documented defaults and still complete this phase (including phase status).

The output — `preferences.json` — is consumed directly by Design and Estimate without any further interpretation.

Questions are organized into **three batches** (≤7 per batch) presented sequentially. A standalone **fast-path** mode exists for simple stacks (< 5 apps, no Private Spaces, no Kafka).

---

## Step 0: Prior Run Check

Check `$MIGRATION_DIR/` for existing state:

**Case 1 — Completed preferences exist** (`preferences.json` present):

> "I found existing migration preferences from a previous run. Would you like to:"
>
> A) Re-use these preferences and skip questions
> B) Start fresh and re-answer all questions

- If A: Skip to Validation Checklist with the existing `preferences.json`.
- If B: Delete `preferences.json`, continue to Step 1.

**Case 2 — Draft preferences exist** (`preferences-draft.json` present, no `preferences.json`):

> "I found a partial set of answers from a previous session ([N] of [total] batches completed). Would you like to:"
>
> A) Resume from where you left off — I'll pick up the remaining questions
> B) Start fresh and re-answer all questions

- If A: Load the draft, read `metadata.batches_completed` to determine which batches are done, skip completed batches when entering Step 3.
- If B: Delete `preferences-draft.json`, continue to Step 1.

**Case 3 — No prior state**: Continue to Step 1.

---

## Step 1: Read Inventory and Determine Fast-Path Eligibility

Read `$MIGRATION_DIR/heroku-resource-inventory.json`. This artifact must exist (produced by Phase 1: Discover).

### Discovery Summary

Present a discovery summary:

> **Apps discovered:** [total_apps_discovered] Heroku apps
> **Resource types:** [count formations], [count addons], [count spaces], [count pipelines]
> **Top add-on services:** [list top 3–5 add-on services by frequency]
> **Heroku generation:** [Cedar/Fir/Mixed — summarize `heroku_generation` across apps]

**If `billing_profile.available == true`:**

> **Monthly Heroku spend:** $[total_monthly_cost] ([billing_period])
> **Top cost categories:** [top 3 from line_items by cost]

### Fast-Path Gate

After the Discovery Summary, evaluate fast-path eligibility:

```
IF total_apps_discovered < 5
   AND no resource with resource_type == "space" exists
   AND no resource with config.addon_service == "heroku-kafka" exists
THEN eligible for fast-path (3–5 questions)
ELSE full question flow (12–15 questions)
```

**If fast-path eligible**, present:

> "Your stack looks straightforward — [N] app(s), no Private Spaces, no Kafka.
>
> Want to use smart defaults and answer just 4–6 questions? I'll apply sensible defaults for the rest.
>
> **[Yes — short path]** / **[No — ask me everything]**"

**If user chooses Yes:**

1. Ask only: **Q1** (region), **Q2** (compliance), **Q3** (availability), **Q4** (maintenance window), **Q12c** (Kubernetes preference) — and optionally **Q11** (Fir intent, only if Fir detected).
2. Apply documented defaults for ALL other questions. Record each in `metadata.questions_defaulted`.
3. Write `preferences.json` with `metadata.clarify_mode: "fast_path"`. Skip Steps 2–3 batch loop.
4. Proceed to Step 4 (Validation Checklist).

**Fast-path default values applied when skipping questions:**

- `migration_urgency`: `routine`
- `migration_approach`: `full_cutover`
- `migration_method`: `pg_dump_restore`
- `containerization_status`: `buildpack_only`
- `database_ha`: matches Q3 availability
- `redis_ha`: `true`
- `dns_strategy`: `route53`
- `log_retention_days`: `30`
- `cost_optimization`: `balanced`
- `container_registry`: `ecr`

Users are informed: "Smart defaults applied: full cutover approach, pg_dump for database migration, routine urgency, buildpack-only containerization status. Say 'I want to change something' to override any of these."

**If user chooses No, or stack is not eligible:** Continue to Step 2.

---

## Step 2: Determine Active Questions

Before generating questions, scan the inventory to determine which questions apply:

### Conditional Question Rules

| Question                       | Condition to Include                                             | Skip When                                 |
| ------------------------------ | ---------------------------------------------------------------- | ----------------------------------------- |
| Q1 — Target AWS region         | Always                                                           | Never                                     |
| Q2 — Compliance                | Always                                                           | Never                                     |
| Q3 — Availability posture      | Always                                                           | Never                                     |
| Q4 — Maintenance window        | Always                                                           | Never                                     |
| Q5 — Environment naming        | Always                                                           | Never                                     |
| Q5b — Migration urgency        | Always                                                           | Never                                     |
| Q6 — Database HA               | Postgres add-on present                                          | No Postgres in inventory                  |
| Q6b — Migration approach       | Postgres add-on present                                          | No Postgres in inventory                  |
| Q6c — DB migration method      | Postgres add-on present                                          | No Postgres in inventory                  |
| Q7 — Redis HA                  | Redis add-on present                                             | No Redis in inventory                     |
| Q8 — Kafka retention           | Kafka add-on present                                             | No Kafka in inventory                     |
| Q9 — VPC subnet IDs            | Private Space with peering detected BUT subnet IDs not available | No Private Space or subnets already known |
| Q9b — VPC ID                   | Peering detected but VPC ID not found in Terraform               | VPC ID already available or no peering    |
| Q10 — DNS strategy             | Always                                                           | Never                                     |
| Q11 — Fir intent               | At least one app has `heroku_generation == "fir"`                | No Fir-generation apps                    |
| Q12b — Containerization status | Always                                                           | Never                                     |
| Q12c — Kubernetes preference   | Always                                                           | Never                                     |
| Q12 — Container registry       | Always                                                           | Never                                     |
| Q13 — Log retention            | Always                                                           | Never                                     |
| Q14 — Alerting preference      | Always                                                           | Never                                     |
| Q15 — Cost optimization        | Always                                                           | Never                                     |

### Batch Planning

After determining active questions, organize into **three batches** (≤5 each):

| Batch | Name                      | Questions            | Content                                                                                                     |
| ----- | ------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------- |
| **1** | Global / Strategic        | Q1–Q5, Q5b, Q12c     | Region, compliance, availability, maintenance, environment naming, migration urgency, Kubernetes preference |
| **2** | Data / Network            | Q6, Q6b, Q6c, Q7–Q10 | Database HA, migration approach, DB migration method, Redis HA, Kafka retention, VPC subnets, DNS strategy  |
| **3** | Operational / Conditional | Q11, Q12b, Q12–Q15   | Fir intent, containerization status, container registry, log retention, alerting, cost optimization         |

**Batch 2 is active** if ANY of: Postgres present, Redis present, Kafka present, Private Space detected, or DNS question is needed (always true → Batch 2 always fires with at least Q10).

**Batch 3 is always active** (Q12–Q15 always fire; Q11 fires only if Fir detected).

Record the ordered list of active batches and count questions per batch after filtering.

---

## Step 3: Present Questions in Progressive Batches

### Batch Loop

For each active batch, execute steps 3a–3d:

#### 3a. Present Batch

Use a conversational tone with brief context explaining why each question matters. Number questions within each batch starting from 1.

**Batch 1 — Global / Strategic (always first):**

```
Before designing your AWS architecture, I have a few sections of questions
to tailor the migration plan. You can answer each, skip individual ones
(I'll use sensible defaults), or say "use defaults for the rest" at any point.

Let's start with your strategic requirements.

--- Global / Strategic ---

[Present active questions Q1–Q5]
```

**Batch 2 — Data / Network (if active):**

```
Got it — strategic preferences saved.

Next up: [N] questions about your data services and networking.
You can answer each, skip individual ones, or say "use defaults for the rest."

--- Data / Network ---

[Present active questions Q6–Q10]
```

**Batch 3 — Operational / Conditional:**

```
[Data/Network preferences saved.]

Last section — [N] questions about operations and platform choices, then we're ready to design.
You can answer each, skip individual ones, or say "use defaults for the rest."

--- Operational / Conditional ---

[Present active questions Q11–Q15]
```

#### 3b. Wait for Response

Wait for the user's response to the current batch. Do NOT present the next batch or proceed to Design without a response or an explicit "use defaults for the rest."

**"Use defaults for the rest" handling:** If the user says this at any point:

1. Apply documented defaults for all unanswered questions in the current batch.
2. Apply documented defaults for all questions in remaining batches.
3. Record each defaulted answer with `source: "default"`.
4. Skip directly to Step 4 (write final `preferences.json`).

#### 3c. Interpret Batch Answers and Validate

For each answered question, apply the interpretation rule. For skipped questions within the batch, apply the documented default.

**Input Validation:** If the user provides a response that does not match the valid options for a question:

1. Reject the input.
2. Present an error message indicating the valid options.
3. Re-prompt the same question without advancing.

Example:

> "That's not a valid option for [question topic]. Please choose from: [list valid options]"

**Subnet ID validation (Q9):** If the user provides subnet IDs that do not match the format `subnet-[17 hex characters]`:

> "Invalid subnet ID format. Expected format: `subnet-xxxxxxxxxxxxxxxxx` (subnet- followed by 17 hexadecimal characters). Please provide 1–6 valid subnet IDs, comma-separated."

Re-prompt Q9 until valid input is provided.

**VPC ID validation (Q9b):** If the user provides a VPC ID that does not match the format `vpc-[17 hex characters]`:

> "Invalid VPC ID format. Expected format: `vpc-xxxxxxxxxxxxxxxxx` (vpc- followed by 17 hexadecimal characters). Please provide your existing AWS VPC ID."

Re-prompt Q9b until valid input is provided.

#### 3d. Save Draft

**If more batches remain** after this one: Write (or update) `$MIGRATION_DIR/preferences-draft.json` with all answers collected so far:

```json
{
  "metadata": {
    "draft": true,
    "batches_completed": ["global"],
    "batches_remaining": ["data_network", "operational"],
    "timestamp": "<ISO timestamp>"
  },
  "global": { ... },
  "data": { ... },
  "network": { ... },
  "operational": { ... }
}
```

Batch name values: `"global"`, `"data_network"`, `"operational"`.

Return to **3a** for the next batch.

**If this was the last active batch**: Do not write a draft — proceed to Step 4.

---

## Question Catalog

### Batch 1: Global / Strategic

#### Q1 — Target AWS Region

> Which AWS region should your infrastructure be deployed to?
>
> A) us-east-1 (N. Virginia) — lowest latency to East Coast, most services available
> B) us-west-2 (Oregon) — West Coast, good general-purpose choice
> C) eu-west-1 (Ireland) — Europe, good for EU-based users
> D) eu-central-1 (Frankfurt) — Central Europe, German data residency
> E) ap-southeast-1 (Singapore) — Asia-Pacific
> F) ap-northeast-1 (Tokyo) — Japan
> G) Other — specify a valid AWS region code

**Interpret:**

- A → `target_region: "us-east-1"`
- B → `target_region: "us-west-2"`
- C → `target_region: "eu-west-1"`
- D → `target_region: "eu-central-1"`
- E → `target_region: "ap-southeast-1"`
- F → `target_region: "ap-northeast-1"`
- G → validate user-provided region code; `target_region: "<user value>"`

**Default:** A → `target_region: "us-east-1"`

**Valid options:** Any valid AWS region code (e.g., `us-east-1`, `eu-west-1`, `ap-southeast-2`). Reject non-existent region codes.

---

#### Q2 — Compliance Requirements

> Do you need to meet any compliance frameworks?
>
> A) None — no specific compliance requirements
> B) SOC 2 — service organization controls
> C) HIPAA — healthcare data protection
> D) PCI DSS — payment card data
> E) Multiple — specify which ones

**Interpret:**

- A → `compliance: "none"`
- B → `compliance: "soc2"`
- C → `compliance: "hipaa"`
- D → `compliance: "pci"`
- E → `compliance: [user-specified array]`

**Default:** A → `compliance: "none"`

**Design impact:** HIPAA → BAA-eligible services only; PCI → encryption at rest and in transit mandatory; SOC 2 → audit logging required.

---

#### Q3 — Availability Posture

> What availability level does your production workload need?
>
> A) Single-AZ — development/staging, cost-optimized (no redundancy)
> B) Multi-AZ — production standard (automatic failover within a region)
> C) Multi-AZ HA — mission-critical (Aurora, enhanced monitoring, aggressive failover)
> D) Multi-Region — catastrophic tolerance (global distribution, highest cost)

**Interpret:**

- A → `availability: "single-az"`
- B → `availability: "multi-az"`
- C → `availability: "multi-az-ha"`
- D → `availability: "multi-region"`

**Default:** B → `availability: "multi-az"`

**Design impact:**

- `single-az` or `multi-az` → RDS PostgreSQL
- `multi-az-ha` or `multi-region` → Aurora PostgreSQL
- Applies to all data services (Postgres, Redis, Kafka broker distribution)

---

#### Q4 — Maintenance Window

> When should AWS perform maintenance operations (patches, minor upgrades)?
>
> A) Weekday off-hours (Tue–Thu, 02:00–06:00 UTC)
> B) Weekend early morning (Sat–Sun, 02:00–06:00 UTC)
> C) Sunday pre-dawn (Sun 03:00–05:00 UTC) — recommended
> D) Flexible — no preference, use AWS defaults

**Interpret:**

- A → `maintenance_window: {"day": "tuesday-thursday", "hour_utc": 3}`
- B → `maintenance_window: {"day": "saturday-sunday", "hour_utc": 3}`
- C → `maintenance_window: {"day": "sunday", "hour_utc": 4}`
- D → `maintenance_window: "flexible"`

**Default:** D → `maintenance_window: "flexible"`

---

#### Q5 — Environment Naming

> What should the primary environment be called in AWS resource naming and tags?
>
> A) production
> B) prod
> C) live
> D) Other — specify

**Interpret:**

- A → `environment_naming: "production"`
- B → `environment_naming: "prod"`
- C → `environment_naming: "live"`
- D → `environment_naming: "<user value>"`

**Default:** A → `environment_naming: "production"`

---

#### Q5b — Migration Approach

> _Fires only when Heroku Postgres add-on is present in inventory._
>
> How would you like to sequence the migration?
>
> A) Full cutover — migrate database and application together in one maintenance window (simpler, single downtime event)
> B) Database first — migrate the database to AWS now, keep the app on Heroku temporarily while you prepare the compute migration (requires a target exit date)
>
> ⚠️ Option B requires your AWS database to be publicly accessible during the transition period (with SSL/TLS encryption). Public access is removed once the app migrates off Heroku.

**Interpret:**

- A → `migration_approach: "full_cutover"`
- B → `migration_approach: "interim_cutover_data_first"`

**Default:** A → `migration_approach: "full_cutover"`

**If user selects B:**

1. Ask follow-up: "What's your target date to complete the app migration off Heroku? (YYYY-MM-DD format)"
2. Validate ISO 8601 date format. If invalid, re-prompt.
3. Set `target_exit_date: "<validated date>"`
4. Set `interim_cutover: true`
5. Set `ktlo_warning: "Heroku is in sustaining engineering. Hybrid operation should be bounded to weeks, not quarters."`

**Design impact:** Option B → MIGRATION_GUIDE.md includes "Interim Database Exposure" section with public RDS + TLS configuration and "Platform Risk" callout.

---

#### Q12c — Kubernetes Preference

> _Fires always. This question determines the compute orchestration target for all dyno formations._
>
> Would you prefer EKS (Kubernetes) or ECS Fargate for your containerized workloads?
>
> EKS gives you full Kubernetes control but requires cluster management expertise. Fargate eliminates cluster management entirely — simpler operations, no nodes to manage.
>
> A) EKS preferred — team has Kubernetes expertise, wants full K8s control (self-managed node groups)
> B) EKS acceptable — team can operate K8s, prefers managed node groups to reduce burden
> C) ECS Fargate preferred — simplest managed containers, no cluster management (default)
> D) I don't know

**Interpret:**

- A → `design_constraints.kubernetes: { "value": "eks-managed", "chosen_by": "user" }`
- B → `design_constraints.kubernetes: { "value": "eks-or-ecs", "chosen_by": "user" }`
- C → `design_constraints.kubernetes: { "value": "ecs-fargate", "chosen_by": "user" }`
- D → `design_constraints.kubernetes: { "value": "ecs-fargate", "chosen_by": "default" }`

**Default:** C → `design_constraints.kubernetes: { "value": "ecs-fargate", "chosen_by": "default" }`

**Design impact:** When `"eks-managed"` or `"eks-or-ecs"` is selected, ALL formation resources map to EKS Deployments with pod resource requests/limits instead of Fargate task definitions. Non-formation resources (Postgres, Redis, Kafka, add-ons) are unaffected.

**Fir intent precedence:** If both Q11 (Fir intent = "self_managed_eks_ecs") and Q12c (kubernetes = "ecs-fargate") are set, the global kubernetes preference takes precedence for non-Fir formations. Fir workloads remain deferred in v1 regardless of this setting.

---

### Batch 2: Data / Network

#### Q6 — Database HA Preference

> _Fires only when Heroku Postgres add-on is present in inventory._
>
> For your PostgreSQL database(s), what high-availability configuration do you want on AWS?
>
> A) Single-AZ — matches typical Heroku standard plans, lowest cost
> B) Multi-AZ — automatic failover to standby replica (RDS Multi-AZ)
> C) Multi-AZ HA — Aurora with read replicas and fast failover
> D) Match global availability posture — use same tier as Q3 answer

**Interpret:**

- A → `database_ha: "single-az"`
- B → `database_ha: "multi-az"`
- C → `database_ha: "multi-az-ha"`
- D → `database_ha: <value from Q3 availability>`

**Default:** D → matches Q3 availability answer

**Design impact:**

- `single-az` or `multi-az` → RDS PostgreSQL
- `multi-az-ha` → Aurora PostgreSQL

---

#### Q6b — Migration Approach

> _Fires only when Heroku Postgres add-on is present in inventory._
>
> How do you want to phase the migration?
>
> A) Full cutover — migrate database and application together in one maintenance window
> B) Data-first (interim cutover) — migrate database to AWS first, keep application on Heroku temporarily while you containerize and prepare compute migration
>
> ⚠️ Note: Option B requires your RDS instance to be publicly accessible during the interim period (with SSL/TLS enforced). Heroku is in sustaining engineering — hybrid operation should be bounded to weeks, not quarters.

**Interpret:**

- A → `migration_approach: "full_cutover"`
- B → `migration_approach: "interim_cutover_data_first"` — also triggers follow-up for target exit date

**If B selected, immediately ask:**

> When do you plan to complete the full migration (move compute off Heroku)?
> Please provide a target date (YYYY-MM-DD format).

Validate: must be valid ISO 8601 date, must be in the future.

**On valid date:** Set `target_exit_date: "<date>"`, `interim_cutover: true`, `ktlo_warning: "Heroku is in sustaining engineering. Hybrid operation should be bounded to weeks, not quarters."`

**Default:** A → `migration_approach: "full_cutover"`

**Design impact:** Option B triggers interim database exposure section in MIGRATION_GUIDE.md (public RDS + TLS), Platform Risk callout, and post-migration lockdown emphasis.

---

#### Q6c — Database Migration Method

> _Fires only when Heroku Postgres add-on is present in inventory._
>
> How would you like to migrate your PostgreSQL data to AWS?
>
> Estimated database size from your plan: ~[derive from postgres plan table max storage]
> (If you know your actual database size, tell me and I'll adjust the recommendation.)
>
> A) pg_dump / pg_restore — simplest method, requires application downtime during migration (recommended for databases under ~10GB)
> B) AWS DMS (Database Migration Service) — bulk migration with shorter downtime window for large databases (recommended for databases over ~10GB)
> ⚠️ Note: DMS cannot do continuous replication with Heroku Postgres (Heroku does not grant the REPLICATION role). This is a one-time bulk copy with a final cutover window.
> C) Bucardo — trigger-based replication for near-zero downtime (requires additional EC2 infrastructure)
> D) WAL-G — WAL-based replication for minimal downtime on large databases (requires additional EC2 infrastructure)

**Interpret:**

- A → `migration_method: "pg_dump_restore"`
- B → `migration_method: "dms"`
- C → `migration_method: "bucardo"`
- D → `migration_method: "wal_g"`

**Default:** A → `migration_method: "pg_dump_restore"`

**Size-based recommendation logic:**

- If estimated DB size < 10GB → recommend A (pg_dump_restore)
- If estimated DB size ≥ 10GB and user accepts brief downtime → recommend B (dms)
- If user requires near-zero downtime regardless of size → recommend C or D

**Estimating size:** Use the postgres plan table's maximum storage capacity for the detected plan tier as the estimated size. **Note: This is an upper-bound estimate — your actual database may be much smaller than the plan allows.** If your actual data is well below the plan maximum (e.g., 2 GB actual on a 64 GB plan), override downward to get a more appropriate method recommendation. If user provides actual size, use that instead and record `source: "user_override"` for the size estimate.

**Design impact:** Determines which data migration procedure section appears in MIGRATION_GUIDE.md. DMS selection triggers the CDC limitation warning.

---

#### Q7 — Redis HA

> _Fires only when Heroku Redis (Key-Value Store) add-on is present in inventory._
>
> Should your Redis cluster on AWS include Multi-AZ with automatic failover?
>
> A) Yes — Multi-AZ with automatic failover (higher availability, ~2x cost)
> B) No — single-node, no replication (matches Heroku mini/premium-0 without HA)

**Interpret:**

- A → `redis_ha: true`
- B → `redis_ha: false`

**Default:** A → `redis_ha: true` (if source plan has HA enabled), otherwise B → `redis_ha: false`

---

#### Q8 — Kafka Retention

> _Fires only when Heroku Kafka (Apache Kafka on Heroku) add-on is present in inventory._
>
> How long should Kafka messages be retained on AWS MSK?
>
> A) 1 day — minimal retention, lowest storage cost
> B) 3 days — short-term replay
> C) 7 days — standard retention (matches Heroku default)
> D) 14 days — extended replay window
> E) 30 days — long retention for analytics/audit
> F) Custom — specify number of days

**Interpret:**

- A → `kafka_retention_days: 1`
- B → `kafka_retention_days: 3`
- C → `kafka_retention_days: 7`
- D → `kafka_retention_days: 14`
- E → `kafka_retention_days: 30`
- F → `kafka_retention_days: <user value>` (validate: integer 1–365)

**Default:** C → `kafka_retention_days: 7`

---

#### Q9 — VPC Subnet IDs

> _Fires only when Private Space with VPC peering is detected AND subnet IDs are not available from the API._
>
> Your Heroku Private Space has VPC peering configured. I need your AWS subnet IDs to reference the existing VPC instead of creating a new one.
>
> Please provide 1–6 subnet IDs (comma-separated) in the format: `subnet-xxxxxxxxxxxxxxxxx`
>
> Example: `subnet-0a1b2c3d4e5f67890, subnet-1a2b3c4d5e6f78901`

**Interpret:** Parse comma-separated values, trim whitespace, validate each matches `^subnet-[0-9a-f]{17}$`.

**Validation:** If any ID does not match the format, reject and re-prompt:

> "Invalid subnet ID format. Expected format: `subnet-xxxxxxxxxxxxxxxxx` (subnet- followed by 17 hexadecimal characters). Please provide 1–6 valid subnet IDs."

**Accept:** 1–6 valid subnet IDs → `subnet_ids: [<validated array>]`

---

#### Q9b — VPC ID

> _Fires only when VPC peering is detected but the VPC ID could not be found in Terraform._
>
> I detected VPC peering for your Private Space but couldn't find the AWS VPC ID in your Terraform files. Please provide your existing AWS VPC ID.
>
> Format: `vpc-xxxxxxxxxxxxxxxxx`

**Interpret:** Validate matches `^vpc-[0-9a-f]{17}$`.

**Validation:** If format doesn't match, reject and re-prompt:

> "Invalid VPC ID format. Expected format: `vpc-xxxxxxxxxxxxxxxxx` (vpc- followed by 17 hexadecimal characters). Please provide your existing AWS VPC ID."

**Accept:** Valid VPC ID → `existing_vpc_id: "<validated value>"`

---

#### Q10 — DNS Strategy

> How do you want to manage DNS for your migrated services?
>
> A) Route 53 — migrate DNS to AWS for full integration (health checks, failover routing)
> B) External DNS — keep current DNS provider, update records manually during cutover

**Interpret:**

- A → `dns_strategy: "route53"`
- B → `dns_strategy: "external"`

**Default:** A → `dns_strategy: "route53"`

---

### Batch 3: Operational / Conditional

#### Q11 — Fir Intent

> _Fires ONLY when at least one app has `heroku_generation == "fir"` in the inventory._
>
> I detected Fir-generation app(s) in your Heroku account. Fir runs on Kubernetes with ARM/Graviton and Cloud Native Buildpacks — these workloads may already run on AWS infrastructure, which can reduce your compute migration lift.
>
> What's your compute migration intent for these Fir workloads?
>
> A) Exit Heroku entirely — re-platform all Fir workloads to AWS (ECS/Fargate, standard containers)
> B) Self-managed EKS/ECS — move to Kubernetes or ECS on AWS with your own orchestration

**Interpret:**

- A → `fir_intent: "exit_heroku"`
- B → `fir_intent: "self_managed_eks_ecs"`

**Default:** A → `fir_intent: "exit_heroku"`

**Note:** Cutover timing (full vs data-first) is handled by the migration_approach question (Q5b), not this question. This question only determines the compute destination for Fir workloads.

**Design impact:** Both options result in full Fir workload migration to AWS. Option B indicates the user wants to manage their own Kubernetes/ECS orchestration rather than using the skill's standard Fargate mapping.

---

#### Q12b — Containerization Status

> Is your application already containerized (has a Dockerfile)?
>
> A) Yes — Dockerfile exists, ready for Fargate deployment
> B) No — uses Heroku buildpacks only, no Dockerfile yet
> C) Partial — some services have Dockerfiles, others use buildpacks

**Interpret:**

- A → `containerization_status: "containerized"`
- B → `containerization_status: "buildpack_only"`
- C → `containerization_status: "partial"`

**Default:** B → `containerization_status: "buildpack_only"`

**Design impact:** Options B and C trigger a "Containerization Prerequisites" section in the MIGRATION_GUIDE.md with Procfile→Dockerfile guidance for common buildpacks (Ruby, Node.js, Python, Go, Java). Does not change design mappings — all compute targets are Fargate regardless.

---

#### Q12 — Container Registry

> Where should container images be stored for your containerized workloads?
>
> A) Amazon ECR — fully integrated with ECS/Fargate, no cross-account config needed
> B) Existing registry — you already have a container registry (Docker Hub, GitHub Container Registry, etc.)

**Interpret:**

- A → `container_registry: "ecr"`
- B → `container_registry: "external"`

**Default:** A → `container_registry: "ecr"`

---

#### Q13 — Log Retention

> How long should application logs be retained in CloudWatch Logs?
>
> A) 7 days — short retention, lowest cost
> B) 14 days — standard short-term
> C) 30 days — typical production retention
> D) 90 days — extended for debugging and compliance
> E) 365 days — long-term compliance/audit
> F) Custom — specify number of days

**Interpret:**

- A → `log_retention_days: 7`
- B → `log_retention_days: 14`
- C → `log_retention_days: 30`
- D → `log_retention_days: 90`
- E → `log_retention_days: 365`
- F → `log_retention_days: <user value>` (validate: integer 1–3653)

**Default:** C → `log_retention_days: 30`

---

#### Q14 — Alerting Preference

> How do you want to handle alerting and on-call notifications?
>
> A) CloudWatch Alarms + SNS — native AWS alerting (email, SMS, Lambda triggers)
> B) PagerDuty — integrate with existing PagerDuty setup
> C) OpsGenie — integrate with existing OpsGenie setup
> D) None for now — I'll configure alerting later

**Interpret:**

- A → `alerting: "cloudwatch"`
- B → `alerting: "pagerduty"`
- C → `alerting: "opsgenie"`
- D → `alerting: "none"`

**Default:** A → `alerting: "cloudwatch"`

---

#### Q15 — Cost Optimization Aggressiveness

> How aggressively should we optimize for cost vs. operational safety?
>
> A) Conservative — match current capacity closely, prioritize stability over savings
> B) Balanced — reasonable right-sizing with safety margins (recommended)
> C) Aggressive — minimize cost, accept tighter margins and potential scaling events

**Interpret:**

- A → `cost_optimization: "conservative"`
- B → `cost_optimization: "balanced"`
- C → `cost_optimization: "aggressive"`

**Default:** B → `cost_optimization: "balanced"`

---

## Step 4: Assemble and Write preferences.json

Assemble all interpreted answers into the final `$MIGRATION_DIR/preferences.json`. If `preferences-draft.json` exists, use it as the base — merge in the final batch's answers, remove draft-specific metadata fields (`draft`, `batches_completed`, `batches_remaining`), and set timestamp to current time.

Write `$MIGRATION_DIR/preferences.json`:

```json
{
  "migration_id": "<from .phase-status.json>",
  "skill": "heroku-to-aws",
  "metadata": {
    "timestamp": "<ISO timestamp>",
    "clarify_mode": "full|fast_path",
    "questions_asked": ["Q1", "Q2", ...],
    "questions_defaulted": ["Q7", "Q8", ...],
    "questions_skipped_not_applicable": ["Q6", "Q8", ...]
  },
  "global": {
    "target_region": "<Q1 value>",
    "compliance": "<Q2 value>",
    "availability": "<Q3 value>",
    "maintenance_window": "<Q4 value>",
    "environment_naming": "<Q5 value>",
    "migration_approach": "<Q6b value>",
    "interim_cutover": false,
    "target_exit_date": "<ISO date or null>",
    "ktlo_warning": "<warning text or null>",
    "fir_intent": "<Q11 value or null>"
  },
  "data": {
    "database_ha": "<Q6 value>",
    "migration_method": "<Q6c value>",
    "estimated_db_size_gb": "<derived or user-provided>",
    "db_size_source": "plan_derived|user_override",
    "redis_ha": "<Q7 value>",
    "kafka_retention_days": "<Q8 value>",
    "dns_strategy": "<Q10 value>"
  },
  "network": {
    "existing_vpc_id": "<Q9b value or null>",
    "subnet_ids": ["<Q9 values>"],
    "private_space_detected": true|false
  },
  "operational": {
    "container_registry": "<Q12 value>",
    "containerization_status": "<Q12b value>",
    "log_retention_days": "<Q13 value>",
    "alerting": "<Q14 value>",
    "cost_optimization": "<Q15 value>"
  },
  "design_constraints": {
    "kubernetes": { "value": "<Q12c value>", "chosen_by": "user|default" }
  },
  "defaults_applied": ["<list of defaulted question IDs>"],
  "sources": {
    "Q1": "user|default",
    "Q2": "user|default",
    ...
  }
}
```

### Schema Rules

1. The `sources` object records how each question was answered: `"user"` (explicitly answered), `"default"` (system default applied, including skipped questions and "use defaults for the rest").
2. `defaults_applied` is the array of question IDs that received default values.
3. `metadata.questions_skipped_not_applicable` records questions skipped because their triggering condition was not met (e.g., Q6 skipped because no Postgres).
4. Only write keys with non-null values. Omit sections/keys that are entirely null.
5. `global.fir_intent` is `null` when no Fir apps detected (Q11 not fired).
6. `network.existing_vpc_id` and `network.subnet_ids` are `null`/empty when no Private Space peering exists.
7. `data.database_ha`, `data.redis_ha`, `data.kafka_retention_days` are omitted entirely when those services are not present in the inventory.

After writing `preferences.json`, delete `$MIGRATION_DIR/preferences-draft.json` if it exists.

---

## Defaults Table

| Question                  | Default                                 | Constraint                                           |
| ------------------------- | --------------------------------------- | ---------------------------------------------------- |
| Q1 — Region               | A (us-east-1)                           | `target_region: "us-east-1"`                         |
| Q2 — Compliance           | A (none)                                | `compliance: "none"`                                 |
| Q3 — Availability         | B (multi-az)                            | `availability: "multi-az"`                           |
| Q4 — Maintenance          | D (flexible)                            | `maintenance_window: "flexible"`                     |
| Q5 — Env naming           | A (production)                          | `environment_naming: "production"`                   |
| Q6 — Database HA          | D (match Q3)                            | `database_ha: <Q3 value>`                            |
| Q6b — Migration approach  | A (full cutover)                        | `migration_approach: "full_cutover"`                 |
| Q6c — DB migration method | A (pg_dump)                             | `migration_method: "pg_dump_restore"`                |
| Q7 — Redis HA             | A (yes)                                 | `redis_ha: true`                                     |
| Q8 — Kafka retention      | C (7 days)                              | `kafka_retention_days: 7`                            |
| Q9 — Subnet IDs           | _(no default — must ask if applicable)_ | —                                                    |
| Q9b — VPC ID              | _(no default — must ask if applicable)_ | —                                                    |
| Q10 — DNS                 | A (Route 53)                            | `dns_strategy: "route53"`                            |
| Q11 — Fir intent          | A (exit Heroku)                         | `fir_intent: "exit_heroku"`                          |
| Q12b — Containerization   | B (buildpack_only)                      | `containerization_status: "buildpack_only"`          |
| Q12c — Kubernetes pref    | C (Fargate)                             | `design_constraints.kubernetes.value: "ecs-fargate"` |
| Q12 — Registry            | A (ECR)                                 | `container_registry: "ecr"`                          |
| Q13 — Log retention       | C (30 days)                             | `log_retention_days: 30`                             |
| Q14 — Alerting            | A (CloudWatch)                          | `alerting: "cloudwatch"`                             |
| Q15 — Cost optimization   | B (balanced)                            | `cost_optimization: "balanced"`                      |

**Important:** Q9 and Q9b have no default — they are only asked when Private Space peering exists and required data is missing. If they fire, they must be answered (the system cannot proceed without subnet/VPC information for existing VPC references).

---

## Validation Checklist

Before handing off to Design:

- [ ] `preferences.json` written to `$MIGRATION_DIR/`
- [ ] `global.target_region` is populated with a valid AWS region code
- [ ] `global.availability` is populated
- [ ] If Postgres in inventory → `data.database_ha` is populated
- [ ] If Postgres in inventory → `global.migration_approach` is populated
- [ ] If Postgres in inventory → `data.migration_method` is populated
- [ ] If `migration_approach` is `interim_cutover_data_first` → `global.target_exit_date` is a valid future ISO date
- [ ] If `migration_approach` is `interim_cutover_data_first` → `global.interim_cutover` is `true`
- [ ] If Private Space peering detected → `network.subnet_ids` contains 1–6 valid IDs
- [ ] If peering detected and VPC ID needed → `network.existing_vpc_id` is populated
- [ ] If Fir apps detected → `global.fir_intent` is populated (not null)
- [ ] `operational.containerization_status` is populated
- [ ] `design_constraints.kubernetes.value` is one of: `"eks-managed"`, `"eks-or-ecs"`, `"ecs-fargate"`
- [ ] `design_constraints.kubernetes.chosen_by` is `"user"` or `"default"`
- [ ] All entries in `sources` have a value of `"user"` or `"default"`
- [ ] `metadata.clarify_mode` is set to `"fast_path"` or `"full"`
- [ ] Only keys with non-null values are present
- [ ] Output is valid JSON
- [ ] `preferences-draft.json` has been deleted (if it existed)

---

## Completion Handoff Gate (Fail Closed)

Load `shared/handoff-gates.md`. **Re-read from disk** before checking.

**Re-entry guard:** If `aws-design.json` exists and `phases.design` is `"completed"`: STOP unless the user explicitly confirms re-running Clarify. Emit `GATE_FAIL | phase=clarify | field=aws-design.json | reason=stale_downstream`.

**Checks (all must PASS):**

1. `preferences.json` exists and parses as valid JSON.
2. All Validation Checklist items pass.
3. If `heroku-resource-inventory.json` contains Postgres add-ons → `data.database_ha` is set (non-null).
4. If `heroku-resource-inventory.json` contains Postgres add-ons → `global.migration_approach` is set (non-null).
5. If `global.migration_approach` is `interim_cutover_data_first` → `global.target_exit_date` is non-null and a valid future date.
6. If Fir-generation apps detected → `global.fir_intent` is set (non-null).
7. If Private Space peering detected and subnet IDs were required → `network.subnet_ids` is non-empty array.

**On any FAIL:** Emit `GATE_FAIL | phase=clarify | field=<path> | reason=missing`. **Do NOT modify artifacts to pass the gate.** **Do NOT update `.phase-status.json`.** Tell the user to answer the missing question or re-run Clarify.

**On PASS:** Emit `HANDOFF_OK | phase=clarify | artifacts=preferences.json`.

---

## Step 5: Update Phase Status

Only after `HANDOFF_OK`. In the **same turn** as the output message below, use the Phase Status Update Protocol (read-merge-write) to update `.phase-status.json`:

- Set `phases.clarify` to `"completed"`
- Set `current_phase` to `"design"`
- Update `last_updated` to current ISO timestamp

Output to user: "Clarification complete. Proceeding to Phase 3: Design AWS Architecture."

---

## Scope Boundary

**This phase covers requirements gathering ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Detailed AWS architecture or service configurations
- Code migration examples or SDK snippets
- Detailed cost calculations
- Migration timelines or execution plans
- Terraform generation
- Dyno-to-Fargate sizing decisions
- Database instance class selection

**Your ONLY job: Understand what the user needs. Nothing else.**
