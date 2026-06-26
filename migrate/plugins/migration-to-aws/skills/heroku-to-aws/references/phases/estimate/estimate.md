# Phase 4: Estimate AWS Costs

> Loaded by SKILL.md when `phases.design == "completed"` AND `phases.estimate != "completed"`.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Overview

Calculate projected monthly AWS costs for the designed Heroku-to-AWS architecture. Produce `estimation-infra.json` conforming to `shared/schema-estimate-infra.md`. Classify migration complexity using `shared/migration-complexity.md`.

**Inputs:**

- `$MIGRATION_DIR/aws-design.json` (from Phase 3)
- `$MIGRATION_DIR/preferences.json` (from Phase 2)
- `$MIGRATION_DIR/heroku-resource-inventory.json` (from Phase 1 — for billing profile)

**Outputs:**

- `$MIGRATION_DIR/estimation-infra.json`
- `.phase-status.json` updated (estimate → completed)

---

## Step 0: Pricing Mode Selection

### Step 0a: Load Pricing Cache

Read `shared/pricing-cache.md`. Check the `Last updated` date in the header:

- If ≤ 30 days old: **Cached prices are the primary source.** No MCP calls needed for services listed in the cache. Set `pricing_source: "cached"`.
- If > 30 days old: Cache is stale for AI model prices. Infrastructure prices (Fargate, RDS, S3, etc.) remain reliable. Attempt MCP (Step 0b) for services not in cache; use stale cache as fallback with `pricing_source: "cached_stale"`.

### Step 0b: MCP Availability Check (only if cache stale or service not listed)

Attempt to reach awspricing MCP with **up to 2 retries** (3 total attempts, 10-second timeout per attempt):

1. **Attempt 1**: Call `get_pricing_service_codes()`
2. **If timeout/error after 10s**: Wait 1 second, retry (Attempt 2)
3. **If still fails after 10s**: Wait 2 seconds, retry (Attempt 3)
4. **If all 3 attempts fail**: Use cached prices. Set `pricing_source: "cached_fallback"`.

### Step 0c: Display Pricing Mode to User

**Before any calculation**, surface the pricing status:

- **Cache fresh + all services covered**: "Pricing source: cached (updated [date], ±5-10% accuracy). Live pricing API not required."
- **Cache stale + MCP available**: "Pricing source: live API (awspricing MCP). Cache is stale ([date]) — using real-time pricing."
- **Cache stale + MCP unavailable**: "⚠️ Pricing source: stale cache only (updated [date]). The awspricing MCP server is unreachable. Proceeding with cached pricing; accuracy ±5-10% for infrastructure."
- **Service not in cache + MCP unavailable**: "⚠️ Some services not in pricing cache and MCP unreachable. Those services will show `pricing_source: unavailable` in the estimate."

### Pricing Hierarchy (per-service lookup order)

| Priority | Source                    | Condition                                     | `pricing_source` value |
| -------- | ------------------------- | --------------------------------------------- | ---------------------- |
| 1        | `shared/pricing-cache.md` | Service found in cache                        | `"cached"`             |
| 2        | MCP API (`get_pricing`)   | Service NOT in cache, MCP available           | `"live"`               |
| 3        | Cache after MCP failure   | MCP attempted but failed, service IS in cache | `"cached_fallback"`    |
| 4        | Unavailable               | NOT in cache AND MCP failed                   | `"unavailable"`        |

For typical Heroku migrations (Fargate, RDS, Aurora, ElastiCache, ALB, NAT Gateway, S3, CloudWatch, Secrets Manager, EventBridge, SES, OpenSearch, MQ), ALL prices are in `pricing-cache.md`. Zero MCP calls needed.

---

## Step 1: Prerequisites

1. Read `$MIGRATION_DIR/.phase-status.json`. If `phases.design` is not exactly `"completed"`: **STOP**. Output: "Phase 3 (Design) not completed. Run Phase 3 first."
2. Read `$MIGRATION_DIR/aws-design.json`. If missing or invalid JSON: **STOP**. Output: "Design artifact missing or corrupted. Re-run Phase 3."
3. Read `$MIGRATION_DIR/preferences.json`. If missing: **STOP**. Output: "Preferences file missing. Re-run Phase 2."
4. Read `$MIGRATION_DIR/heroku-resource-inventory.json`. Extract `billing_profile` section (may be null/absent).

### Validate Design

- `services` array must exist and not be empty. If empty: **STOP**. Output: "No services in design. Re-run Phase 3."
- Each service entry must have `aws_service` and `aws_config` fields. If missing: **STOP**. Output: "Service [service_id] missing aws_service or aws_config. Re-run Phase 3."

If all validations pass, proceed to Part 1.

---

## Part 1: Determine Current Heroku Costs

Use the best available source for Heroku monthly baseline (first match wins):

1. **`billing_profile` in inventory (preferred)** — Use actual billing data as the Heroku baseline. Highest confidence.
   - Extract `billing_profile.total_monthly_cost` as the total
   - Extract `billing_profile.line_items[]` for per-app breakdown
   - Set `current_costs.source: "billing_data"`

2. **Heroku pricing cache** — If no billing data, Load `references/shared/heroku-pricing-cache.md` and derive costs from discovered resources:
   - For each resource in inventory, look up its plan in the cache tables (case-insensitive exact match)
   - Multiply dyno costs by `formation.quantity`
   - Sum all matched resources to get `heroku_monthly_estimated`
   - Set `current_costs.source: "pricing_cache"`
   - Set `current_costs.accuracy: "±5%"`
   - If any resource plan is not found in cache, mark as `"unpriced_heroku"` and exclude from total; add to warnings

3. **User-provided** — If pricing cache produces zero matched resources (unlikely with Terraform discovery), ask: "I need your current Heroku monthly spend to produce a meaningful cost comparison. What is your approximate Heroku monthly cost?" Use the answer.
   - Set `current_costs.source: "user_provided"`

4. **Unavailable** — If user declines: present AWS costs without Heroku comparison.
   - Set `current_costs.source: "unavailable"`
   - Note: "Heroku baseline unavailable — AWS costs shown without comparison."

When billing data or pricing cache is available, present the Heroku baseline as:

- Total monthly cost
- Per-app breakdown (dyno, add-on, platform charges)
- Billing period

---

## Part 2: Calculate Projected AWS Costs

For each service in `aws-design.json → services[]`, calculate monthly cost using rates from `pricing-cache.md`. Track `pricing_source` per service.

### Per-Service Calculation Formulas

| AWS Service               | Formula                                                                                              | Key inputs from `aws_config`                                                  |
| ------------------------- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| **Fargate**               | (task_cpu/1024 × $0.04048 + task_memory/1024 × $0.004445) × 730 hrs × desired_count                  | `task_cpu`, `task_memory`, `desired_count`                                    |
| **EKS (cluster + nodes)** | $0.10/hr control plane ($73/month) + node_instance_rate × 730 hrs × node_count + ALB per web service | `eks_cluster.node_groups[].instance_types`, `desired_size`, web service count |
| **ALB**                   | $16.43/month fixed + LCU estimate ($0.008/LCU-hr × 730)                                              | Per web service with `load_balancer: true`                                    |
| **RDS PostgreSQL**        | instance_rate × 730 hrs + storage_gb × $0.23/GB-month                                                | `instance_class`, `storage_gb`, `multi_az`                                    |
| **Aurora PostgreSQL**     | instance_rate × 730 hrs + storage_gb × $0.10/GB-month + I/O estimate                                 | `instance_class`, `storage_gb`                                                |
| **ElastiCache Redis**     | node_rate × 730 hrs (× 2 if Multi-AZ)                                                                | `node_type`, `multi_az`                                                       |
| **MSK**                   | broker_rate × 730 hrs × broker_count + storage_gb × rate                                             | `broker_instance_type`, `broker_count`, `storage_per_broker_gb`               |
| **CloudWatch Logs**       | log_volume_gb × $0.50/GB + storage × $0.03/GB-month                                                  | `retention_days`, estimated log volume                                        |
| **S3**                    | storage_gb × $0.023/GB-month + request estimates                                                     | `storage_gb` (from Bucketeer/Cloudinary mapping)                              |
| **Amazon SES**            | $0.10 per 1000 emails (minimal baseline)                                                             | Flat estimate from SendGrid mapping                                           |
| **EventBridge Scheduler** | $1.00 per million events (minimal for cron jobs)                                                     | From Heroku Scheduler mapping                                                 |
| **Amazon MQ**             | instance_rate × 730 hrs + storage                                                                    | From CloudAMQP mapping                                                        |
| **Amazon OpenSearch**     | instance_rate × 730 hrs + storage                                                                    | From Bonsai Elasticsearch mapping                                             |
| **Secrets Manager**       | secret_count × $0.40/month + API calls × $0.05/10K                                                   | Config var count from inventory                                               |
| **NAT Gateway**           | $32.85/month fixed + data processing estimate                                                        | From VPC design (if new VPC)                                                  |
| **RDS Proxy**             | $0.015 per vCPU-hour × 730 hrs × vCPUs                                                               | When connection pooling mapped                                                |
| **Route 53**              | $0.50/hosted zone + query estimate                                                                   | When DNS strategy = route53                                                   |
| **CloudFront**            | $0.085/GB (first 10TB) + request costs                                                               | From Cloudinary composite mapping                                             |
| **X-Ray**                 | $5.00 per million traces                                                                             | Only if tracing detected in source                                            |

### Unpriced Resource Handling

IF pricing data for a service is unavailable from both MCP and cache:

1. Mark the resource's cost as `"unpriced"` in the per-service breakdown
2. **Exclude** from the total monthly cost sum
3. Add to `warnings[]`: "Pricing unavailable for [service_id] ([aws_service]). Requires manual cost verification."
4. Add service name to `pricing_source.services_with_missing_fallback[]`

### EKS Cost Calculation

When `aws-design.json` contains EKS services (`aws_service: "EKS"`):

1. **EKS Control Plane**: $0.10/hour = **$73.00/month** (fixed, one cluster regardless of node count)
2. **EC2 Node Group**: Look up instance type hourly rate × 730 hours × `desired_size` nodes

   | Node Instance Type | Hourly Rate | Monthly (730 hrs) |
   | ------------------ | ----------- | ----------------- |
   | m6i.large          | $0.096      | $70.08/node       |
   | m6i.xlarge         | $0.192      | $140.16/node      |
   | m6i.4xlarge        | $0.768      | $560.64/node      |
   | r6i.4xlarge        | $1.008      | $735.84/node      |
   | m6i.8xlarge        | $1.536      | $1,121.28/node    |
   | m6i.16xlarge       | $3.072      | $2,242.56/node    |

3. **ALB for web services**: Same as Fargate ALB pricing ($16.43/month per web service)
4. **NAT Gateway** (if private subnets): Same as Fargate path ($32.85/month + data processing)

**Total EKS monthly cost** = control_plane + (node_rate × 730 × node_count) + ALB_costs + NAT_costs

**EKS vs Fargate cost comparison note**: When presenting EKS estimates alongside the Heroku baseline, include this note:

> "EKS with EC2 nodes is typically cheaper than Fargate for sustained workloads (>60% utilization) because there is no per-pod Fargate surcharge. However, EKS has a higher base cost ($73/month control plane + minimum 2 nodes) and requires Kubernetes operational expertise."

### Cost Tier Calculation

Calculate 3 cost tiers to show the optimization range:

| Tier          | Description              | Adjustments                                                                                       |
| ------------- | ------------------------ | ------------------------------------------------------------------------------------------------- |
| **Premium**   | Highest resilience       | Multi-AZ everything, latest-gen instances, no Spot, enhanced monitoring                           |
| **Balanced**  | Standard setup (default) | On-demand pricing, Multi-AZ where configured, standard monitoring                                 |
| **Optimized** | Cost-minimized           | Reserved pricing assumption (20-40% discount), Fargate Spot where applicable, S3-IA for cold data |

**Balanced** is the primary comparison tier. Generated Terraform (Phase 5) aligns with **Balanced**.

### Total Cost Calculation

```
total_monthly = sum(individual_resource_costs) — excluding "unpriced" resources
```

Verify: total equals the arithmetic sum of all individually calculated resource costs. This is the **Property 16** invariant.

---

## Part 2B: Observability Cost Estimation (CloudWatch)

Heroku includes basic logging via its log drain. AWS CloudWatch charges from the first GB. This section ensures observability costs are not a surprise.

### Step 1: Estimate Log Volume

Use per-service heuristic (billing data not applicable for log volume since Heroku logging model differs):

| AWS Service (from aws-design.json) | Estimated log volume/month | Basis                   |
| ---------------------------------- | -------------------------- | ----------------------- |
| Fargate task                       | 3 GB per task              | Container stdout/stderr |
| RDS/Aurora instance                | 1 GB per instance          | Error log + slow query  |
| ALB                                | 2 GB per load balancer     | Access logs             |
| NAT Gateway                        | 1 GB per gateway           | Flow logs               |
| ElastiCache                        | 0.5 GB per node            | Slow log                |
| MSK                                | 2 GB per broker            | Broker logs             |

Sum all applicable services.

### Step 2: Estimate Custom Metrics and Alarms

- `custom_metrics_count = (number of services in aws-design.json × 5)`
- Default floor: 10 custom metrics
- `alarm_count = max(5, number_of_services × 2)` (baseline health/error/latency)

### Step 3: Calculate CloudWatch Costs

```
log_ingestion_cost    = monthly_log_gb × $0.50
log_storage_cost      = monthly_log_gb × $0.03 × retention_months (use preferences.operational.log_retention_days / 30, default: 1)
custom_metrics_cost   = custom_metrics_count × $0.30
alarms_cost           = alarm_count × $0.10
tracing_cost          = 0 (do not add X-Ray costs unless tracing detected in source)

total_observability   = log_ingestion_cost + log_storage_cost + custom_metrics_cost + alarms_cost + tracing_cost
```

### Step 4: Add Observability Entry

Add to `projected_costs.breakdown`:

```json
{
  "service": "CloudWatch + X-Ray (Observability)",
  "low": "<total × 0.7>",
  "mid": "<total>",
  "high": "<total × 1.5>",
  "accuracy": "±30%",
  "pricing_source": "cached",
  "components": {
    "log_ingestion": "<log_ingestion_cost>",
    "log_storage": "<log_storage_cost>",
    "custom_metrics": "<custom_metrics_cost>",
    "alarms": "<alarms_cost>",
    "tracing": "<tracing_cost>"
  },
  "volume_source": "heuristic",
  "note": "Heroku includes basic logging at no extra charge. CloudWatch charges from the first GB. Actual costs depend on log verbosity and retention."
}
```

This entry REPLACES any CloudWatch entries in a "Supporting" row — never double-count.

---

## Part 3: Cost Comparison (Heroku vs AWS)

### When Billing Data Available

Present a side-by-side comparison:

- **Heroku current monthly total** (from `billing_profile.total_monthly_cost`)
- **AWS Premium / Balanced / Optimized monthly totals**
- **Difference** (savings or increase) per tier vs Heroku — monthly and annual
- **Per-app breakdown** for the Balanced tier: for each Heroku app, show:
  - Current Heroku spend (from `billing_profile.line_items` filtered by app)
  - Projected AWS spend (sum of services mapped from that app)
  - Difference

Include in `estimation-infra.json`:

```json
"cost_comparison": {
  "heroku_monthly_baseline": "<total from billing>",
  "option_a_premium": {
    "aws_monthly": "<premium total>",
    "monthly_difference": "<premium - heroku>",
    "annual_difference": "<(premium - heroku) × 12>",
    "percent_change": "<+/-X%>"
  },
  "option_b_balanced": {
    "aws_monthly": "<balanced total>",
    "monthly_difference": "<balanced - heroku>",
    "annual_difference": "<(balanced - heroku) × 12>",
    "percent_change": "<+/-X%>"
  },
  "option_c_optimized": {
    "aws_monthly": "<optimized total>",
    "monthly_difference": "<optimized - heroku>",
    "annual_difference": "<(optimized - heroku) × 12>",
    "percent_change": "<+/-X%>"
  }
}
```

### When Billing Data NOT Available

Omit `cost_comparison` section or set `heroku_monthly_baseline` to null. Present AWS costs without comparison. State: "Heroku billing data not available — showing projected AWS costs only. Provide Heroku invoices and re-run discovery to see side-by-side comparison."

---

## Part 4: Migration Cost Considerations

Heroku does not charge egress fees for data transfer during migration (unlike GCP). However, there may be time-based costs during parallel operation.

### IF billing data IS available:

```json
"migration_cost_considerations": {
  "billing_data_available": true,
  "categories": [
    "Heroku platform fees during parallel operation (both Heroku and AWS running simultaneously during cutover window)"
  ],
  "note": "Heroku charges are subscription-based. During migration, both Heroku and AWS costs apply until Heroku apps are decommissioned. No data transfer egress fees from Heroku."
}
```

### IF billing data is NOT available:

```json
"migration_cost_considerations": {
  "billing_data_available": false,
  "categories": [],
  "note": "Parallel operation costs depend on Heroku billing. Provide Heroku invoices for dual-run cost projections."
}
```

---

## Part 5: ROI Analysis

Present monthly and annual cost difference between Heroku baseline and each AWS tier.

- If AWS is cheaper: present monthly and annual savings per tier
- If AWS is more expensive: state clearly and justify with operational benefits

**Operational efficiency factors (qualitative — do not assign dollar values):**

- Full infrastructure control (VPC, security groups, IAM policies)
- Auto-scaling granularity (Fargate service scaling, Aurora auto-scaling)
- Broader AWS service integration (Step Functions, EventBridge, SNS/SQS)
- Cost optimization levers unavailable on Heroku (Spot, Savings Plans, Reserved Instances)
- Reduced vendor lock-in risk

**Non-cost benefits:**

- Global infrastructure (25+ AWS regions vs Heroku's limited regions)
- Compliance certifications (SOC2, HIPAA, PCI, FedRAMP) built into AWS services
- Enterprise integration (Direct Connect, Transit Gateway, Organizations)
- Service breadth (200+ AWS services for future workloads)
- Scaling flexibility (auto-scaling, reserved capacity, burst pricing)

```json
"roi_analysis": {
  "recurring_savings": {
    "monthly_difference_balanced": "<negative = AWS cheaper>",
    "monthly_difference_optimized": "<negative = AWS cheaper>",
    "annual_difference_balanced": "<× 12>",
    "annual_difference_optimized": "<× 12>",
    "note": "Negative = AWS cheaper. Positive = Heroku cheaper on pure cost basis."
  },
  "operational_efficiency_factors": [...],
  "non_cost_benefits": [...],
  "note": "Heroku parallel-operation fees during migration window are excluded from recurring ROI calculations."
}
```

---

## Part 6: Cost Optimization Opportunities

Present applicable optimizations with estimated savings. These are **incremental post-migration actions** beyond the Balanced on-demand baseline.

| Optimization           | Savings Range                               | Applies To                       | When                                           |
| ---------------------- | ------------------------------------------- | -------------------------------- | ---------------------------------------------- |
| Compute Savings Plans  | 20-66%                                      | Fargate                          | Post-migration (after 30-90 day baseline)      |
| Database Savings Plans | Up to 35% (serverless) / ~20% (provisioned) | Aurora, RDS, ElastiCache         | Post-migration or after right-sizing           |
| RDS Reserved Instances | Up to 69%                                   | RDS, Aurora (provisioned)        | Post-migration (after architecture stabilizes) |
| S3 Intelligent-Tiering | 38-50%                                      | S3 storage                       | During migration                               |
| Fargate Spot           | 60-70%                                      | Non-critical/batch Fargate tasks | If worker dynos exist                          |

**Emit in `optimization_opportunities[]`:**

### Compute Savings Plans (when Fargate in design)

```json
{
  "opportunity": "Compute Savings Plans",
  "type": "compute_savings_plan",
  "target_services": ["Fargate"],
  "savings_percent": "20-66%",
  "savings_monthly": null,
  "commitment": "1-year or 3-year",
  "timing": "post-migration (after 30-90 days of usage data)",
  "implementation_effort": "low",
  "prerequisite": "Establish AWS compute usage baseline before committing",
  "description": "Heroku dyno billing is flat-rate per dyno type. Fargate usage patterns may differ — establish AWS baseline before Savings Plan commitment. Use Cost Explorer recommendations after 30+ days.",
  "references": [
    "https://aws.amazon.com/savingsplans/compute-pricing/",
    "https://aws.amazon.com/savingsplans/faqs/"
  ]
}
```

### Database Savings Plans (when RDS/Aurora in design, projected > $50/month)

```json
{
  "opportunity": "Database Savings Plans",
  "type": "database_savings_plan",
  "target_services": ["RDS", "Aurora"],
  "savings_percent": "up to 35% (serverless) / up to 20% (provisioned)",
  "savings_monthly": "<calculated or null if < $50/mo>",
  "commitment": "1-year no-upfront",
  "timing": "immediately post-migration or after instance right-sizing",
  "implementation_effort": "low",
  "prerequisite": "Confirm target instance class; omit savings_monthly when DB on-demand < $50/month",
  "description": "Heroku Postgres runs 24/7 with predictable usage. Database Savings Plans offer flexibility to change engines/instances post-migration. Mutually exclusive with RDS RIs on same workload.",
  "alternative": {
    "opportunity": "RDS Reserved Instances",
    "type": "rds_reserved_instances",
    "savings_percent": "up to 69%",
    "trade_off": "Locked to specific instance family and region"
  },
  "references": [
    "https://aws.amazon.com/savingsplans/database-pricing/",
    "https://aws.amazon.com/rds/reserved-instances/"
  ]
}
```

### Fargate Spot (when worker dynos exist)

```json
{
  "opportunity": "Fargate Spot for Worker Tasks",
  "type": "fargate_spot",
  "target_services": ["Fargate"],
  "savings_percent": "60-70%",
  "savings_monthly": "<calculated based on worker task costs>",
  "commitment": "none",
  "timing": "during migration (for fault-tolerant workers)",
  "implementation_effort": "medium",
  "prerequisite": "Worker tasks must be fault-tolerant and idempotent",
  "description": "Heroku worker dynos mapped to Fargate can use Spot pricing for background/batch work that tolerates interruption."
}
```

Only include optimizations relevant to the designed architecture. Do not include EC2-specific optimizations if no EC2 in design.

---

## Part 7: Complexity Tier Classification

Load `shared/migration-complexity.md`. Classify using these inputs from the current artifacts:

| Input                | Source                                                                            | Key                                                                                                   |
| -------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Service count        | `aws-design.json`                                                                 | `metadata.total_services`                                                                             |
| Monthly spend        | `estimation-infra.json` (just calculated) or `billing_profile.total_monthly_cost` | Projected AWS balanced monthly                                                                        |
| Has databases        | `aws-design.json → services[]`                                                    | `aws_service` in {RDS PostgreSQL, Aurora PostgreSQL, ElastiCache Redis, Amazon MQ, Amazon OpenSearch} |
| Has stateful storage | `aws-design.json → services[]`                                                    | `aws_service` in {S3} with replication hints                                                          |
| Availability         | `preferences.json`                                                                | `global.availability`                                                                                 |
| Compliance           | `preferences.json`                                                                | `global.compliance`                                                                                   |
| Multi-region         | `aws-design.json → services[]`                                                    | More than one distinct `aws_config.region` value                                                      |

**Evaluate from Large down to Small (first match wins):**

### Large — ANY of:

- Service count ≥ 9
- Monthly spend > $10,000
- Multi-region deployment (services span 2+ AWS regions)
- Compliance requirements present (`compliance` is not `"none"`)

### Medium — NOT Large, and ANY of:

- Service count 4–8
- Monthly spend $1,000–$10,000
- Has databases
- Availability is `"multi-az"` or `"multi-az-ha"`

### Small — NOT Large, NOT Medium (ALL of):

- Service count ≤ 3
- Monthly spend < $1,000
- No databases or stateful storage with replication
- Availability is `"single-az"` or unspecified
- No compliance requirements

Include in `estimation-infra.json`:

```json
{
  "complexity_tier": "small|medium|large",
  "complexity_inputs": {
    "service_count": "<N>",
    "monthly_spend": "<projected balanced>",
    "has_databases": true|false,
    "has_stateful_storage": true|false,
    "availability": "<from preferences>",
    "compliance": "<from preferences>",
    "multi_region": true|false
  }
}
```

**Timeline guidance** (from `migration-complexity.md` Infrastructure Path):

| Tier   | Weeks | Approach                            |
| ------ | ----- | ----------------------------------- |
| Small  | 2-6   | Compressed                          |
| Medium | 6-12  | Phased cluster migration            |
| Large  | 12-18 | Phased cluster migration (extended) |

---

## Part 8: Recommendation

Present 3 paths:

1. **Migrate with Optimizations (Best ROI)** — optimized service choices, projected savings
2. **Phased Migration (Lower Risk)** — app-by-app per design order, validate each before proceeding
3. **Stay on Heroku (Lowest Complexity)** — only if AWS is more expensive and costs are the sole metric

Include migrate/stay decision factors:

- **Migrate if:** infrastructure control matters, AWS-specific services needed, compliance requirements exceed Heroku's offerings, scaling beyond Heroku limits, long-term cost optimization (Savings Plans, Spot)
- **Stay if:** cost is the only metric and AWS is more expensive, team benefits from Heroku's managed simplicity, no need for AWS-specific services, migration risk exceeds benefit

### Persist recommendation to estimation-infra.json

```json
"recommendation": {
  "path": "migrate_optimized|migrate_phased|stay",
  "path_label": "Migrate with Optimizations|Phased Migration|Stay on Heroku",
  "roi_justification": "<one-sentence ROI case>",
  "confidence": "high|medium|low",
  "migrate_if": ["<factors specific to THIS stack>"],
  "stay_if": ["<factors specific to THIS stack>"],
  "next_steps": ["<actionable items>"]
}
```

**Path selection logic:**

| Scenario                                     | `path` value          | `path_label`                   |
| -------------------------------------------- | --------------------- | ------------------------------ |
| AWS cheaper or operational benefits justify  | `"migrate_optimized"` | `"Migrate with Optimizations"` |
| Complex stack, app-by-app safer              | `"migrate_phased"`    | `"Phased Migration"`           |
| AWS more expensive AND costs are sole metric | `"stay"`              | `"Stay on Heroku"`             |

---

## Output: Write `estimation-infra.json`

Assemble the full artifact conforming to `shared/schema-estimate-infra.md`:

```json
{
  "phase": "estimate",
  "design_source": "infrastructure",
  "timestamp": "<ISO 8601>",
  "pricing_source": {
    "status": "cached|live|cached_fallback|unavailable",
    "message": "<human-readable pricing status>",
    "fallback_staleness": {
      "last_updated": "<cache date>",
      "days_old": "<N>",
      "is_stale": false,
      "staleness_warning": null
    },
    "services_by_source": {
      "live": [],
      "fallback": [],
      "estimated": []
    },
    "services_with_missing_fallback": []
  },
  "accuracy_confidence": "±5-10%",

  "current_costs": {
    "source": "billing_data|user_provided|unavailable",
    "heroku_monthly": "<total or null>",
    "heroku_annual": "<total × 12 or null>",
    "baseline_note": "<source description>",
    "breakdown": { "dyno": "<X>", "addon": "<X>", "platform": "<X>" }
  },

  "projected_costs": {
    "aws_monthly_premium": "<N>",
    "aws_monthly_balanced": "<N>",
    "aws_monthly_optimized": "<N>",
    "aws_annual_optimized": "<N × 12>",
    "breakdown": { "...per-service entries..." }
  },

  "cost_comparison": { "...from Part 3..." },
  "migration_cost_considerations": { "...from Part 4..." },
  "roi_analysis": { "...from Part 5..." },
  "optimization_opportunities": [ "...from Part 6..." ],

  "complexity_tier": "<small|medium|large>",
  "complexity_inputs": { "...from Part 7..." },

  "financial_summary": {
    "current_heroku_monthly": "<N or null>",
    "projected_aws_balanced_monthly": "<N>",
    "projected_aws_optimized_monthly": "<N>",
    "monthly_savings_balanced": "<heroku - balanced, negative = AWS more expensive>",
    "monthly_savings_optimized": "<heroku - optimized>",
    "annual_savings_optimized": "<× 12>",
    "recommendation": "<summary sentence>"
  },

  "recommendation": { "...from Part 8..." }
}
```

Write to `$MIGRATION_DIR/estimation-infra.json`.

---

## Completion Handoff Gate (Fail Closed)

Load `shared/handoff-gates.md`. **Re-read from disk** before checking.

Before returning control to SKILL.md, require:

1. `estimation-infra.json` exists in `$MIGRATION_DIR/`
2. Valid JSON that passes `shared/schema-estimate-infra.md` validation
3. `recommendation.path` ∈ `{migrate_optimized, migrate_phased, stay}`
4. `recommendation.path_label` is non-empty string
5. `recommendation.migrate_if` and `recommendation.stay_if` are non-empty arrays
6. `projected_costs.aws_monthly_balanced` is a positive number
7. Every service in `aws-design.json → services[]` appears in the cost breakdown (or is listed as `"unpriced"` in warnings)
8. Total equals sum of individual resource costs (excluding unpriced) — **Property 16 invariant**
9. `complexity_tier` is one of: `"small"`, `"medium"`, `"large"`

**On FAIL:** Emit `GATE_FAIL | phase=estimate | field=<path> | reason=<reason>`. **Do NOT modify artifacts to pass the gate.** STOP.

**On PASS:** Emit `HANDOFF_OK | phase=estimate | artifacts=estimation-infra.json`.

After `HANDOFF_OK`, use the Phase Status Update Protocol (read-merge-write) to update `.phase-status.json`:

- Set `phases.estimate` to `"completed"`
- Set `current_phase` to `"generate"`
- Update `last_updated` timestamp

---

## Present Summary

After writing `estimation-infra.json`, present a concise summary to the user:

1. **Pricing source and accuracy** — State cache age and accuracy range
2. **Heroku baseline vs AWS projected** (balanced tier) — one-line comparison (if billing available)
3. **Three-tier table**: Premium, Balanced, Optimized with monthly totals
   - Premium: _Highest resilience / highest monthly estimate_
   - Balanced: _Default scenario; compare Heroku to this first_
   - Optimized: _Lower estimate; reservations / Spot trade-offs assumed_
   - One-line note: Three figures are pricing scenarios for the same architecture (not three Terraform stacks). Generated Terraform aligns with Balanced.
4. **Per-service cost breakdown** (balanced tier, 1 line per service)
5. **Migration complexity**: tier + timeline range
6. **Monthly and annual savings** (or increase) vs Heroku per tier (if comparison available)
7. **Top 2-3 optimization opportunities** with savings potential
8. **Recommendation**: `path_label` with one-line justification

Keep under 25 lines. The user can ask for details or re-read `estimation-infra.json`.

---

## Pricing Recipes (MCP Fallback Only)

Only use these recipes when a service is NOT in `pricing-cache.md` and MCP is available. Do NOT call `get_pricing_service_codes` or `get_pricing_service_attributes` — go directly to `get_pricing`.

| AWS Service       | service_code      | filters                                                                                                     | output_options                                                                                                                                     |
| ----------------- | ----------------- | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Fargate           | AmazonECS         | `[{"Field":"productFamily","Value":"Compute"}]`                                                             | `{"pricing_terms":["OnDemand"],"product_attributes":["usagetype","location"],"exclude_free_products":true}`                                        |
| Aurora PostgreSQL | AmazonRDS         | `[{"Field":"databaseEngine","Value":"Aurora PostgreSQL"},{"Field":"deploymentOption","Value":"Single-AZ"}]` | `{"pricing_terms":["OnDemand"],"product_attributes":["instanceType","databaseEngine","deploymentOption","location"],"exclude_free_products":true}` |
| RDS PostgreSQL    | AmazonRDS         | `[{"Field":"databaseEngine","Value":"PostgreSQL"},{"Field":"deploymentOption","Value":"Multi-AZ"}]`         | `{"pricing_terms":["OnDemand"],"product_attributes":["instanceType","databaseEngine","deploymentOption","location"],"exclude_free_products":true}` |
| ElastiCache Redis | AmazonElastiCache | `[{"Field":"cacheEngine","Value":"Redis"},{"Field":"instanceType","Value":"cache.t4g","Type":"CONTAINS"}]`  | `{"pricing_terms":["OnDemand"],"product_attributes":["instanceType","cacheEngine","location"],"exclude_free_products":true}`                       |
| S3                | AmazonS3          | `[{"Field":"storageClass","Value":"General Purpose"}]`                                                      | `{"pricing_terms":["OnDemand"],"product_attributes":["storageClass","volumeType","location"],"exclude_free_products":true}`                        |
| ALB               | AWSELB            | `[{"Field":"productFamily","Value":"Load Balancer-Application"}]`                                           | `{"pricing_terms":["OnDemand"],"product_attributes":["productFamily","location"],"exclude_free_products":true}`                                    |
| NAT Gateway       | AmazonEC2         | `[{"Field":"productFamily","Value":"NAT Gateway"}]`                                                         | `{"pricing_terms":["OnDemand"],"product_attributes":["productFamily","location","group"],"exclude_free_products":true}`                            |
| CloudWatch Logs   | AmazonCloudWatch  | `[{"Field":"usagetype","Value":"DataProcessing-Bytes"}]`                                                    | `{"pricing_terms":["OnDemand"],"product_attributes":["productFamily","location","usagetype"],"exclude_free_products":true}`                        |
| Secrets Manager   | AWSSecretsManager | `[]`                                                                                                        | `{"pricing_terms":["OnDemand"],"exclude_free_products":true}`                                                                                      |
| MSK               | AmazonMSK         | `[{"Field":"productFamily","Value":"Managed Streaming for Apache Kafka"}]`                                  | `{"pricing_terms":["OnDemand"],"product_attributes":["instanceType","location"],"exclude_free_products":true}`                                     |
| Amazon MQ         | AmazonMQ          | `[{"Field":"productFamily","Value":"Broker Instances"}]`                                                    | `{"pricing_terms":["OnDemand"],"product_attributes":["instanceType","location"],"exclude_free_products":true}`                                     |
| OpenSearch        | AmazonES          | `[{"Field":"productFamily","Value":"Compute Instance"}]`                                                    | `{"pricing_terms":["OnDemand"],"product_attributes":["instanceType","location"],"exclude_free_products":true}`                                     |

**Batching rule:** Group up to 4 MCP requests in parallel per turn.

**Important notes:**

- **Aurora**: Use `deploymentOption=Single-AZ` — Aurora handles multi-AZ natively, no "Multi-AZ" pricing option
- **Fargate**: Use `productFamily=Compute`, NOT EC2-style filters
- **CloudWatch**: Filter by `usagetype=DataProcessing-Bytes` for log ingestion pricing

---

## Scope Boundary

**This phase covers financial analysis ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Changes to architecture mappings from Phase 3 (Design)
- Execution timelines or migration schedules (beyond tier classification)
- Terraform or IaC code generation
- Detailed migration procedures or runbooks
- Team staffing, human labor costs, or professional services fees
- AI workload estimation (not applicable to Heroku migrations)

**Your ONLY job: Show the financial picture of moving from Heroku to AWS. Nothing else.**
