# Phase 3: Design AWS Architecture

Single-pass mapping engine that translates each Heroku resource to its AWS equivalent using deterministic lookup tables. No clustering, no dependency graphs — resources are processed as a flat list in input order.
**Execute ALL steps in order. Do not skip or deviate.**

## Lookup Table References (Conditional Loading)

Load these reference files **only when the corresponding resource type exists in the inventory**:

| Resource Type in Inventory | Reference File to Load |
|---------------------------|----------------------|
| `formation` (any) | `design-refs/dyno-type-table.md` |
| `addon:*:heroku-postgresql:*` | `design-refs/postgres-plan-table.md` |
| `addon:*:heroku-redis:*` | `design-refs/redis-plan-table.md` |
| `addon:*:heroku-kafka:*` | `design-refs/kafka-plan-table.md` |
| `addon:*` (non-core) | `design-refs/fast-path-table.md` |

Do NOT speculatively load tables for resource types absent from the inventory.

---

## Phase Status State Machine

### Valid Transitions

```
pending → in_progress → completed
```

Status NEVER goes backward under normal operation. Only an **unrecoverable error** reverts the current phase to `pending`.

### Phase Gate Rules (Fail Closed)

**Rule 1 — Predecessor gate:** Design requires `phases.clarify == "completed"`. If not:

```
GATE_FAIL | phase=design | field=phases.clarify | reason=missing
```

Do NOT advance. Do NOT modify `.phase-status.json`. Tell the user to complete Phase 2 (Clarify) first.

**Rule 2 — Single active phase:** At most one core phase may be `in_progress`. If another is active:

```
GATE_FAIL | phase=design | field=phases.<active_phase> | reason=invalid
```

**Rule 3 — GATE_FAIL halt behavior:** On any handoff gate failure at phase completion:

1. Retain `phases.design` as `in_progress`.
2. Do NOT advance `current_phase`.
3. Do NOT modify artifacts to force the gate to pass.
4. Surface diagnostic: phase, field, reason.
5. Tell user: "Re-run Phase 3 (Design) to produce the missing field, then continue."

**Rule 4 — Unrecoverable error:** If the phase fails fatally:

1. Revert `phases.design` to `"pending"`.
2. Preserve all prior completed phases unchanged.
3. Surface diagnostic with error category and actionable guidance.

---

## Step 0: Validate Prerequisites

1. Read `$MIGRATION_DIR/.phase-status.json`. Validate per SKILL.md State Validation rules.
2. Confirm `phases.clarify == "completed"`. If not → GATE_FAIL (Rule 1).
3. Confirm no other core phase is `in_progress`. If violated → GATE_FAIL (Rule 2).
4. Set `phases.design` to `"in_progress"` and `current_phase` to `"design"`. Write `.phase-status.json`.
5. Read `$MIGRATION_DIR/heroku-resource-inventory.json` from disk.
6. Read `$MIGRATION_DIR/preferences.json` from disk.
7. Confirm both files exist and parse as valid JSON. If either is missing or invalid:

```
GATE_FAIL | phase=design | field=<filename> | reason=missing
```

---

## Step 1: Initialize Design Output Structure

Create the `aws-design.json` output structure in memory:

```json
{
  "phase": "design",
  "design_source": "<discovery_source from inventory metadata>",
  "timestamp": "<current ISO 8601>",
  "metadata": {
    "total_services": 0,
    "total_apps_migrated": 0,
    "fir_workloads_detected": [],
    "fir_generation_note": ""
  },
  "services": [],
  "deferred": [],
  "warnings": [],
  "vpc_design": {}
}
```

Extract from `preferences.json`:
- `global.target_region` → used as `region` for all designed services
- `global.availability` → drives RDS vs Aurora and HA decisions
- `data.database_ha` → overrides availability for database specifically (if present)
- `data.redis_ha` → Redis HA configuration
- `operational.log_retention_days` → CloudWatch log retention

---

## Step 2: Single-Pass Resource Mapping

Process each resource in `heroku-resource-inventory.json`.resources[] in **input order**. For each resource, determine its `resource_type` and route to the appropriate mapping logic below.

**Processing order is deterministic**: first resource in → first mapping out. No reordering, no multi-pass.

---

### 2A: Formation Mapping (Fargate)

**Trigger**: `resource_type == "formation"`

**Prerequisites**: Load `design-refs/dyno-type-table.md` if not already loaded.

**Mapping logic:**

1. Extract `config.dyno_type`, `config.quantity`, `config.process_type` from the resource.

2. **Empty Procfile check**: If there are NO formation resources in the entire inventory for this app (i.e., no process types declared), reject the input:

   > "No process types declared for app `{app_name}`. At least one process type is required in the Procfile."

   Record this in `warnings[]` and skip the app's formations.

3. **Dyno type lookup**: Match `config.dyno_type` (case-insensitive) against the Dyno Type Table.

   - **If NOT found**: Reject this formation entry. Add to `warnings[]`:

     > "Unsupported dyno type: `{dyno_type}`. Cannot map to Fargate. Please contact support or provide manual sizing."

     Do NOT produce a Fargate mapping for this formation. Continue to next resource.

   - **If found**: Extract `fargate_cpu` and `fargate_memory` from the matched row.

4. **Desired count**: Set `desired_count` = `config.quantity`. Valid range: 0–100. If outside range, clamp to nearest boundary and add a warning.

5. **Produce Fargate service entry**:

   ```json
   {
     "service_id": "fargate:{heroku_app}:{process_type}",
     "source_resource_id": "{resource_id}",
     "heroku_app": "{heroku_app}",
     "aws_service": "Fargate",
     "confidence": "deterministic",
     "aws_config": {
       "region": "{target_region}",
       "task_cpu": <fargate_cpu>,
       "task_memory": <fargate_memory>,
       "desired_count": <desired_count>,
       "container_image": "placeholder:{heroku_app}-{process_type}",
       "process_type": "{process_type}",
       "load_balancer": <true if process_type == "web", false otherwise>
     }
   }
   ```

6. **ALB for web process types**: If `process_type == "web"`, produce an additional ALB entry:

   ```json
   {
     "service_id": "alb:{heroku_app}:{process_type}",
     "source_resource_id": "{resource_id}",
     "heroku_app": "{heroku_app}",
     "aws_service": "ALB",
     "confidence": "deterministic",
     "aws_config": {
       "region": "{target_region}",
       "scheme": "internet-facing",
       "target_group": "fargate:{heroku_app}:{process_type}"
     }
   }
   ```

   Non-web process types (worker, release, clock, custom) do NOT get an ALB.

7. Append entries to `services[]`. Increment `metadata.total_services`.

---

### 2B: Postgres Mapping (RDS / Aurora)

**Trigger**: `resource_type == "addon"` AND `config.addon_service == "heroku-postgresql"`

**Prerequisites**: Load `design-refs/postgres-plan-table.md` if not already loaded.

**Mapping logic:**

1. Extract `config.plan`, `config.connection_pooling` from the resource.

2. **Plan lookup**: Match `config.plan` (case-insensitive) against the Postgres Plan Table.

   - **If NOT found**: Halt mapping for this add-on. Add to `warnings[]`:

     > "Unrecognized heroku-postgresql plan tier: `{plan}`. Cannot determine AWS sizing. Deferring to specialist engagement."

     Add a deferred entry (see Step 2F for format). Continue to next resource.

3. **Determine availability preference**:

   - Use `preferences.data.database_ha` if set; otherwise use `preferences.global.availability`.
   - **If unset or unrecognized value** (not one of: `single-az`, `multi-az`, `multi-az-ha`, `multi-region`):
     - Default to `multi-az`.
     - Add warning: "Availability preference unset or unrecognized. Defaulting to multi-az with RDS PostgreSQL."

4. **Service selection**:

   - `single-az` or `multi-az` → **RDS PostgreSQL** (use "Recommended RDS Instance Class" column)
   - `multi-az-ha` or `multi-region` → **Aurora PostgreSQL** (use "Recommended Aurora Instance Class" column)

5. **Instance class**: Read directly from the matched table row. The table already provides the minimum adequate instance class.

6. **Storage**: Read the Storage column from the matched row. Configure storage allocation ≥ this value.

7. **Multi-AZ deployment**: If availability is `multi-az`, `multi-az-ha`, or `multi-region`, set `multi_az: true`.

8. **Connection pooling → RDS Proxy**: If `config.connection_pooling == true`, set `rds_proxy: true`.

9. **Produce RDS/Aurora entry**:

   ```json
   {
     "service_id": "rds:{heroku_app}:postgres",
     "source_resource_id": "{resource_id}",
     "heroku_app": "{heroku_app}",
     "aws_service": "RDS PostgreSQL" | "Aurora PostgreSQL",
     "confidence": "deterministic",
     "aws_config": {
       "region": "{target_region}",
       "instance_class": "<from table>",
       "multi_az": <true|false>,
       "storage_gb": <from table, numeric>,
       "engine_version": "15",
       "rds_proxy": <true|false>
     }
   }
   ```

10. Append to `services[]`. Increment `metadata.total_services`.

---

### 2C: Redis Mapping (ElastiCache)

**Trigger**: `resource_type == "addon"` AND `config.addon_service == "heroku-redis"`

**Prerequisites**: Load `design-refs/redis-plan-table.md` if not already loaded.

**Mapping logic:**

1. Extract `config.plan`, `config.ha_enabled`, `config.encryption_in_transit`, `config.redis_version` from the resource.

2. **Plan lookup**: Match `config.plan` (case-insensitive) against the Redis Plan Table.

   - **If NOT found**: Report error. Add to `warnings[]`:

     > "Unrecognized heroku-redis plan tier: `{plan}`. Cannot determine ElastiCache node type. Deferring to specialist engagement."

     Add a deferred entry. Continue to next resource.

3. **Node type**: Read "Recommended ElastiCache Node Type" from the matched row.

4. **High availability**:

   - If the source plan HA column is "Yes" (or `config.ha_enabled == true`):
     - Set `multi_az: true`
     - Set `automatic_failover: true`
   - Otherwise:
     - Set `multi_az: false`
     - Set `automatic_failover: false`

5. **Engine version**: Use the source plan's Redis Version column. Select a compatible ElastiCache engine version (same major version). For example, source `7.0` → ElastiCache `7.0`.

6. **Encryption in-transit**: If `config.encryption_in_transit == true` (or table Encryption column is "Yes"), set `transit_encryption: true`.

7. **Produce ElastiCache entry**:

   ```json
   {
     "service_id": "elasticache:{heroku_app}:redis",
     "source_resource_id": "{resource_id}",
     "heroku_app": "{heroku_app}",
     "aws_service": "ElastiCache Redis",
     "confidence": "deterministic",
     "aws_config": {
       "region": "{target_region}",
       "node_type": "<from table>",
       "multi_az": <true|false>,
       "automatic_failover": <true|false>,
       "transit_encryption": <true|false>,
       "engine_version": "<compatible version>"
     }
   }
   ```

8. Append to `services[]`. Increment `metadata.total_services`.

---

### 2D: Kafka Mapping (MSK)

**Trigger**: `resource_type == "addon"` AND `config.addon_service == "heroku-kafka"`

**Prerequisites**: Load `design-refs/kafka-plan-table.md` if not already loaded.

**Mapping logic:**

1. Extract `config.plan` and topology fields (`config.topics`, `config.partitions`, `config.replication_factor`) from the resource. If topology fields are missing, use the table's Max Topics, Max Partitions, and default replication factor.

2. **Plan lookup**: Match `config.plan` (case-insensitive) against the Kafka Plan Table.

   - **If NOT found**: Report error. Add to `warnings[]`:

     > "Unrecognized heroku-kafka plan tier: `{plan}`. Cannot determine MSK broker instance type. Deferring to specialist engagement."

     Add a deferred entry. Continue to next resource.

3. **Broker instance type**: Read "Recommended MSK Broker Instance Type" from the matched row.

4. **Storage per broker**: Read "Recommended Storage Per Broker" from the matched row.

5. **Broker count and availability zones**:

   - Basic plans: minimum **2 brokers** across **2 AZs**.
   - Standard/Extended/Private plans: **3 brokers** across **3 AZs**.
   - Never fewer than 2 brokers or 2 AZs.

6. **Topology preservation**:

   - `max_topics`: From table row or `config.topics` (whichever is available).
   - `max_partitions`: From table row or `config.partitions`.
   - `replication_factor`: From `config.replication_factor` or table default (3 for standard/extended/private, 2 for basic).

7. **Produce MSK entry**:

   ```json
   {
     "service_id": "msk:{heroku_app}:kafka",
     "source_resource_id": "{resource_id}",
     "heroku_app": "{heroku_app}",
     "aws_service": "Amazon MSK",
     "confidence": "deterministic",
     "aws_config": {
       "region": "{target_region}",
       "broker_instance_type": "<from table>",
       "storage_per_broker_gb": <from table, numeric>,
       "broker_count": <2 or 3>,
       "availability_zones": <2 or 3>,
       "max_topics": <preserved>,
       "max_partitions": <preserved>,
       "replication_factor": <preserved>
     }
   }
   ```

8. Append to `services[]`. Increment `metadata.total_services`.

---

### 2E: Fast-Path Table Mapping (Other Add-Ons)

**Trigger**: `resource_type == "addon"` AND `config.addon_service` is NOT one of: `heroku-postgresql`, `heroku-redis`, `heroku-kafka`

**Prerequisites**: Load `design-refs/fast-path-table.md` if not already loaded.

**Mapping logic:**

1. Extract `config.addon_service` (the add-on name to match).

2. **Normalize the add-on name** before matching. Terraform `heroku_addon` resources use a `plan` attribute in the format `service:plan-tier` (e.g., `"heroku-postgresql:standard-0"`, `"papertrail:choklad"`). The `addon_service` extracted from this is a lowercase slug. app.json and billing data may use display names. Apply this normalization:

   - Strip the `heroku-` prefix if present (e.g., `heroku-scheduler` → `scheduler`)
   - Replace hyphens with spaces (e.g., `bonsai-elasticsearch` → `bonsai elasticsearch`)
   - The match is then case-insensitive against the fast-path table

   **Common Terraform/app.json slug → display name mappings:**

   | Terraform/app.json Label | Normalized for Fast-Path Match |
   |--------------------------|-------------------------------|
   | `papertrail` | `papertrail` |
   | `sendgrid` | `sendgrid` |
   | `heroku-scheduler` | `heroku scheduler` |
   | `memcachier` | `memcachier` |
   | `bucketeer` | `bucketeer` |
   | `cloudamqp` | `cloudamqp` |
   | `bonsai` | `bonsai elasticsearch` * |
   | `scout` | `scout apm` * |
   | `rollbar` | `rollbar` |
   | `newrelic` | `new relic` * |
   | `twilio` | `twilio` |
   | `cloudinary` | `cloudinary` |
   | `sentry` | `sentry` |

   \* These require special-case mapping because the Terraform/app.json slug differs from the display name. If the slug does not directly match after normalization, check if it is a known prefix of a fast-path entry (e.g., `bonsai` is a known prefix for `bonsai elasticsearch`). Known prefix mappings are:
   - `bonsai` → `bonsai elasticsearch`
   - `scout` → `scout apm`
   - `newrelic` or `new-relic` → `new relic`

3. **Exact case-insensitive match** the normalized name against the Fast-Path Table "Heroku Add-On" column.

   **CRITICAL**: Only exact full-string matches count. Partial matches are NOT valid.

   - "Paper" does NOT match "Papertrail"
   - "papertrail" DOES match "Papertrail" (case-insensitive)
   - "Papertrail Pro" does NOT match "Papertrail"
   - "New Relic APM" does NOT match "New Relic"

3. **If matched — Single mapping** (Mapping Type = "Single"):

   Produce one service entry:

   ```json
   {
     "service_id": "<aws_service_snake_case>:{heroku_app}:{addon_service}",
     "source_resource_id": "{resource_id}",
     "heroku_app": "{heroku_app}",
     "aws_service": "<AWS Service from table>",
     "confidence": "deterministic",
     "aws_config": {
       "region": "{target_region}",
       "log_group": "/heroku/{heroku_app}",
       "retention_days": <from preferences.operational.log_retention_days or 30>
     }
   }
   ```

   Adjust `aws_config` fields based on the specific AWS service (e.g., `log_group` and `retention_days` for CloudWatch Logs; `bucket_name` placeholder for S3; etc.).

4. **If matched — Composite mapping** (Mapping Type = "Composite"):

   Produce a **single** service entry listing all AWS services in the composite:

   ```json
   {
     "service_id": "<primary_service_snake_case>:{heroku_app}:{addon_service}",
     "source_resource_id": "{resource_id}",
     "heroku_app": "{heroku_app}",
     "aws_service": "<All AWS Services joined by ' + '>",
     "confidence": "deterministic",
     "aws_config": {
       "region": "{target_region}",
       "services": ["<Service1>", "<Service2>"]
     }
   }
   ```

   All services in the composite must appear. A single `"deterministic"` confidence covers the group.

5. **If NOT matched** (no exact case-insensitive match):

   Route to **Specialist Gate** (Step 2F).

6. Append matched entries to `services[]`. Increment `metadata.total_services`.

---

### 2F: Specialist Gate (Deferred Add-Ons)

**Trigger**: Any add-on that fails lookup in Steps 2B, 2C, 2D, or 2E.

**Record format:**

```json
{
  "addon_name": "<config.addon_service>",
  "addon_plan": "<config.plan>",
  "provider": "<config.provider>",
  "reason": "Not found in Fast_Path_Table" | "Unrecognized plan tier: {plan}",
  "recommendation": "Engage AWS account team for replacement selection"
}
```

**Required fields** (all must be present):
- `addon_name`: The add-on service name
- `addon_plan`: The specific plan tier
- `provider`: The add-on provider
- `reason`: Why the mapping was deferred
- `recommendation`: Actionable next step

Append to `deferred[]` in the design output.

---

### 2G: Pipeline Detection (Detect-Only Warning)

**Trigger**: `resource_type == "pipeline"`

**Action**: Do NOT produce any service mapping. Add a warning to `warnings[]`:

> "Pipeline '{config.pipeline_name}' detected — CI/CD mapping requires manual configuration"

Pipelines are detect-only in v1. No AWS services are designed for them.

---

### 2H: Space / VPC Design

**Trigger**: `resource_type == "space"`

Processing is deferred to Step 3 (VPC Design) below. Collect all space resources during the pass, then handle VPC design after all resources are mapped.

---

## Step 3: VPC Design

After all resources have been processed in Step 2, design the VPC configuration.

### 3A: Determine VPC Mode

Examine all space resources collected from the inventory:

- **If any space has `config.peering.detected == true`** with a valid `vpc_id`:
  - Mode = `existing_vpc`
  - Use `config.peering.vpc_id` from the space resource
  - Use subnet IDs from `preferences.network.subnet_ids`

- **If no peering detected** (or no space resources at all):
  - Mode = `new_vpc`
  - Generate a new VPC design

### 3B: Existing VPC (Peering Detected)

```json
{
  "mode": "existing_vpc",
  "existing_vpc_id": "<vpc_id from space config>",
  "subnet_ids": ["<from preferences.network.subnet_ids>"],
  "security_groups": [<see 3D below>]
}
```

### 3C: New VPC (No Peering)

Generate a VPC design that includes:

- **CIDR block**: Default `10.0.0.0/16` (or user-specified if in preferences)
- **Subnets**: At least 2 subnets across separate availability zones:
  - `10.0.1.0/24` in AZ-a (public)
  - `10.0.2.0/24` in AZ-b (public)
  - `10.0.3.0/24` in AZ-a (private)
  - `10.0.4.0/24` in AZ-b (private)
- **Route table**: Default route `0.0.0.0/0` → Internet Gateway (for public subnets)
- **Internet Gateway**: One IGW attached to the VPC

```json
{
  "mode": "new_vpc",
  "cidr_block": "10.0.0.0/16",
  "subnets": [
    {"cidr": "10.0.1.0/24", "az": "a", "type": "public"},
    {"cidr": "10.0.2.0/24", "az": "b", "type": "public"},
    {"cidr": "10.0.3.0/24", "az": "a", "type": "private"},
    {"cidr": "10.0.4.0/24", "az": "b", "type": "private"}
  ],
  "route_table": {"destination": "0.0.0.0/0", "target": "internet_gateway"},
  "internet_gateway": true,
  "security_groups": [<see 3D below>]
}
```

### 3D: Security Groups (Private Space Migrations)

When migrating from a Private Space (regardless of peering mode), generate security groups with **restricted inbound rules**:

- Inbound traffic is allowed **only** from declared dependency CIDRs and ports.
- All other inbound traffic is denied by default (implicit deny).
- Outbound allows all traffic (default egress).

Determine declared dependencies from:
- Space peering CIDRs (`config.peering.peer_cidr`)
- Database ports (5432 for Postgres)
- Redis ports (6379)
- Kafka ports (9092)
- Application ports (443 for HTTPS, 80 for HTTP)

```json
{
  "name": "heroku-migrated-app-sg",
  "inbound_rules": [
    {"port": 443, "protocol": "tcp", "cidr": "<peer_cidr or app CIDR>"},
    {"port": 5432, "protocol": "tcp", "cidr": "<vpc_cidr>"},
    {"port": 6379, "protocol": "tcp", "cidr": "<vpc_cidr>"},
    {"port": 9092, "protocol": "tcp", "cidr": "<vpc_cidr>"}
  ],
  "outbound_rules": [
    {"port": 0, "protocol": "-1", "cidr": "0.0.0.0/0"}
  ]
}
```

Only include ports for services that are actually present in the design. If no Postgres → no 5432 rule. If no Redis → no 6379 rule.

### 3E: No Private Space — Default Security Group

If no Private Space exists, produce a standard security group:

```json
{
  "name": "heroku-migrated-app-sg",
  "inbound_rules": [
    {"port": 443, "protocol": "tcp", "cidr": "0.0.0.0/0"},
    {"port": 80, "protocol": "tcp", "cidr": "0.0.0.0/0"}
  ],
  "outbound_rules": [
    {"port": 0, "protocol": "-1", "cidr": "0.0.0.0/0"}
  ]
}
```

Set the completed `vpc_design` object in the design output.

---

## Step 4: Cedar/Fir Notation

After all resources are mapped:

1. Scan `heroku-resource-inventory.json`.apps[] for any app with `heroku_generation == "fir"`.

2. **If Fir workloads exist**:
   - Add each Fir app name to `metadata.fir_workloads_detected[]`.
   - Set `metadata.fir_generation_note`: "Fir-generation workloads detected. No Fir-specific Terraform (ARM/Graviton instance targeting, CNB buildpack configuration) is generated in v1. These workloads are deferred to a future version."
   - Add a warning: "Fir-generation workloads deferred to future version: {comma-separated app names}"

3. **If NO Fir workloads**:
   - Set `metadata.fir_workloads_detected` to `[]`.
   - Set `metadata.fir_generation_note`: "No Fir workloads detected; all Cedar generation."

4. **CRITICAL CONSTRAINT**: Do NOT produce ARM/Graviton instance targeting or CNB buildpack configuration in ANY output, regardless of `heroku_generation` value. Fir detection is **detect-only** in v1.

---

## Step 5: Finalize Metadata

1. Count total unique apps with at least one mapped service → `metadata.total_apps_migrated`.
2. Count total entries in `services[]` → `metadata.total_services`.
3. Set `timestamp` to current ISO 8601.
4. Set `design_source` from inventory metadata `discovery_sources[0]` (or "terraform" if source is unclear).

---

## Step 6: Write `aws-design.json`

Write the completed design object to `$MIGRATION_DIR/aws-design.json`.

Verify the written file:
1. Parses as valid JSON.
2. Has at least one entry in `services[]` OR at least one entry in `deferred[]`.
3. `vpc_design` section is present and non-empty.
4. All entries in `services[]` have: `service_id`, `source_resource_id`, `heroku_app`, `aws_service`, `confidence`, `aws_config`.
5. All entries in `deferred[]` have: `addon_name`, `addon_plan`, `provider`, `reason`, `recommendation`.

---

## Step 7: Check Outputs

Verify required artifacts exist in `$MIGRATION_DIR/`:

1. `aws-design.json` — MUST exist with valid structure per Step 6 checks.
2. `.phase-status.json` — MUST exist and be valid JSON.

**Route output gates (fail closed):**

- If inventory had formation resources → `services[]` MUST contain at least one Fargate entry (unless all dyno types were unrecognized).
- If inventory had `heroku-postgresql` add-ons with recognized plans → `services[]` MUST contain RDS or Aurora entries.
- If inventory had `heroku-redis` add-ons with recognized plans → `services[]` MUST contain ElastiCache entries.
- If inventory had `heroku-kafka` add-ons with recognized plans → `services[]` MUST contain MSK entries.
- If inventory had pipelines → `warnings[]` MUST contain pipeline detect-only warnings.

---

## Completion Handoff Gate (Fail Closed)

Load `shared/handoff-gates.md`. **Re-read from disk** every artifact below before checking.

**Re-entry guard:** If `estimation-infra.json` exists AND `phases.estimate` is `"completed"`: STOP unless the user explicitly confirms re-running Design. Emit:

```
GATE_FAIL | phase=design | field=estimation-infra.json | reason=stale_downstream
```

**Checks (all must PASS):**

1. `aws-design.json` exists and parses as valid JSON.
2. `aws-design.json` has `phase == "design"` and a valid `timestamp`.
3. `services[]` array is present (may be empty only if ALL resources deferred to specialist gate).
4. Every entry in `services[]` has: `service_id`, `source_resource_id`, `heroku_app`, `aws_service`, `confidence`, `aws_config`.
5. Every entry in `deferred[]` has: `addon_name`, `addon_plan`, `provider`, `reason`, `recommendation`.
6. `vpc_design` section is present and has a valid `mode` value (`existing_vpc` or `new_vpc`).
7. If `mode == "existing_vpc"`: `existing_vpc_id` is non-empty.
8. If `mode == "new_vpc"`: at least 2 subnets present across separate AZs.
9. `metadata.total_services` matches `services[].length`.
10. No Fir-specific Terraform (ARM/Graviton, CNB) appears anywhere in output.
11. Route output gates from Step 7 all pass.

**On any FAIL:** Emit `GATE_FAIL | phase=design | field=<path> | reason=<missing|invalid|stale_downstream>`. **Do NOT modify artifacts to pass the gate.** **Do NOT update `.phase-status.json`.** Tell the user what failed and how to fix it.

**On PASS:** Emit `HANDOFF_OK | phase=design | artifacts=aws-design.json`.

---

## Step 8: Update Phase Status

Only after `HANDOFF_OK`. In the **same turn** as the output message below, use the Phase Status Update Protocol (read-merge-write) to update `.phase-status.json`:

1. Read current `.phase-status.json` from disk.
2. Set `phases.design` to `"completed"`.
3. Set `current_phase` to `"estimate"`.
4. Update `last_updated` to current ISO 8601 timestamp.
5. Keep all other phase values unchanged.
6. Write the full file.

Output to user — build message from design contents:

- "Designed X AWS services across Y apps."
- If deferred add-ons: "Deferred N add-on(s) to specialist engagement."
- If Fir detected: "Fir-generation workloads noted as deferred (detect-only)."
- If pipeline warnings: "N pipeline(s) detected (CI/CD requires manual config)."
- VPC mode: "VPC design: [existing VPC referenced | new VPC generated with N subnets]."

Format: "Design phase complete. [artifact summaries] Next required step: Phase 4 — Estimate. Load `references/phases/estimate/estimate.md` now."

---

## Output Files

**Design phase writes files to `$MIGRATION_DIR/`. Required outputs:**

1. `.phase-status.json` — updated per Step 8
2. `aws-design.json` — complete AWS architecture design

**No other files must be created:**

- No README.md
- No design-summary.md
- No EXECUTION_REPORT.txt
- No documentation or report files

All user communication via output messages only.

---

## Error Handling

| Error Category | Behavior | Status Transition |
|---------------|----------|-------------------|
| Predecessor phase incomplete | GATE_FAIL, halt | Remain `pending` |
| Input artifact missing/invalid | GATE_FAIL, halt | Retain `in_progress` |
| Unrecognized dyno type | Reject formation, add warning, continue | Continue `in_progress` |
| Empty Procfile (no process types) | Reject app formations, add warning, continue | Continue `in_progress` |
| Unrecognized Postgres/Redis/Kafka plan | Defer to specialist gate, add warning, continue | Continue `in_progress` |
| Unrecognized availability preference | Default to `multi-az` + RDS + warning, continue | Continue `in_progress` |
| Add-on not in Fast-Path Table | Specialist gate (deferred), continue | Continue `in_progress` |
| Partial match on Fast-Path Table | Specialist gate (NOT a match), continue | Continue `in_progress` |
| No services AND no deferred entries produced | Unrecoverable error | Revert to `pending` (Rule 4) |
| Handoff gate check fails (GATE_FAIL) | Halt pipeline, surface diagnostic | Retain `in_progress` (Rule 3) |
| Downstream artifacts stale (re-entry) | Halt, emit GATE_FAIL stale_downstream | Retain `in_progress` (Rule 3) |

---

## Scope Boundary

**This phase covers Heroku → AWS Design ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Cost estimates or pricing calculations (that is Phase 4 — Estimate)
- Terraform generation or HCL code (that is Phase 5 — Generate)
- Migration scripts or runbooks (that is Phase 5 — Generate)
- Data migration procedures (that is Phase 5 — Generate)
- Feedback collection or plan sharing (that is Phase 6 — Feedback)
- Clarify questions or preference gathering (that is Phase 2 — Clarify)
- Resource discovery or API calls (that is Phase 1 — Discover)

**Your ONLY job: Map each Heroku resource to its AWS equivalent. Nothing else.**
