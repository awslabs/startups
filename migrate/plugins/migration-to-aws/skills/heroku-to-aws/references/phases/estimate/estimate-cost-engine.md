---
_fragment: cost-engine
_of_phase: estimate
_contributes:
  - estimation-infra.json
---

# Estimate Phase: Cost Engine

> Self-contained cost-calculation sub-file. Selects the pricing mode, validates the
> design inputs, and computes the full financial picture: current Heroku costs,
> projected AWS costs (per-service + tiers), observability, comparison, migration
> considerations, ROI, optimization opportunities, complexity tier, and the
> recommendation. The final artifact write, handoff gate, and phase-status update
> are owned by the assembler (`estimate-assemble.md`).

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 0: Pricing Mode Selection

### Step 0a: Load Pricing Cache

Read `references/vendored/pricing/aws-infra-pricing.json` (shared AWS infrastructure pricing data). Check the `_meta.last_updated` date:

- If ≤ 30 days old: **Cached prices are the primary source.** No MCP calls needed for services listed in the file. Set `pricing_source: "cached"`.
- If > 30 days old: Infrastructure prices (Fargate, RDS, S3, etc.) remain reliable. Attempt MCP (Step 0b) for services not in the file; use the cached rates as fallback with `pricing_source: "cached_stale"`.

Each service object carries its rates and (where relevant) a `multi_az_handling` key. Look up the rates from there — do not hardcode them. Apply the cost formula from the Per-Service Calculation Formulas table below.

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

| Priority | Source                                               | Condition                                    | `pricing_source` value |
| -------- | ---------------------------------------------------- | -------------------------------------------- | ---------------------- |
| 1        | `references/vendored/pricing/aws-infra-pricing.json` | Service found in the pricing file            | `"cached"`             |
| 2        | MCP API (`get_pricing`)                              | Service NOT in the file, MCP available       | `"live"`               |
| 3        | Pricing file after MCP failure                       | MCP attempted but failed, service IS in file | `"cached_fallback"`    |
| 4        | Unavailable                                          | NOT in file AND MCP failed                   | `"unavailable"`        |

For typical Heroku migrations (Fargate, RDS, Aurora, ElastiCache, ALB, NAT Gateway, S3, CloudWatch, Secrets Manager, EventBridge, SES, OpenSearch, MQ), ALL prices are in `aws-infra-pricing.json`. Zero MCP calls needed.

---

## Step 1: Prerequisites

The entry gate (design completed, inputs present + valid JSON, non-empty
`services[]`) is enforced by this phase's `_preconditions` frontmatter per
`INTERPRETER.md` § Gate protocol — it has already passed before this fragment
runs. Then:

1. Read `$MIGRATION_DIR/heroku-resource-inventory.json`. Extract `billing_profile` section (may be null/absent).

Proceed to Part 1.

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

For each service in `aws-design.json → services[]`, calculate monthly cost by applying the formula from the Per-Service Calculation Formulas table below, looking up its rates from `references/vendored/pricing/aws-infra-pricing.json`. Track `pricing_source` per service. (`hours_per_month` = 730, from `_meta`.)

### Per-Service Calculation Formulas

Rates below come from the named keys in `aws-infra-pricing.json` — do not hardcode them here. The formula shape + key inputs are shown for reference.

| AWS Service               | Formula (rates from `aws-infra-pricing.json`)                                                                                            | Key inputs from `aws_config`                                                  |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| **Fargate**               | (task_cpu/1024 × `fargate.per_vcpu_hour` + task_memory/1024 × `fargate.per_gb_mem_hour`) × 730 × desired_count                           | `task_cpu`, `task_memory`, `desired_count`                                    |
| **EKS (cluster + nodes)** | `eks.control_plane_monthly` + `eks.node_rates_monthly[type]` × node_count + ALB per web service                                          | `eks_cluster.node_groups[].instance_types`, `desired_size`, web service count |
| **ALB**                   | `alb.monthly_fixed` + LCU estimate (`alb.per_lcu_hour` × 730)                                                                            | Per web service with `load_balancer: true`                                    |
| **RDS PostgreSQL**        | `rds_postgresql.instances[class]` × 730 + storage_gb × `rds_postgresql.storage_per_gb_month` (rate is baked_in Multi-AZ — do NOT double) | `instance_class`, `storage_gb`, `multi_az`                                    |
| **Aurora PostgreSQL**     | `aurora_postgresql.instances[class]` × 730 + storage_gb × `aurora_postgresql.storage_per_gb_month` + I/O estimate (intrinsic multi-AZ)   | `instance_class`, `storage_gb`                                                |
| **ElastiCache Redis**     | `elasticache.nodes[type]` × 730 (× 2 if Multi-AZ — `multiplier_x2`)                                                                      | `node_type`, `multi_az`                                                       |
| **MSK**                   | `msk.brokers[type]` × 730 × broker_count + storage_gb × `msk.storage_per_gb_month` (intrinsic multi-AZ)                                  | `broker_instance_type`, `broker_count`, `storage_per_broker_gb`               |
| **CloudWatch Logs**       | log_volume_gb × `cloudwatch.log_ingestion_per_gb` + storage × `cloudwatch.log_storage_per_gb_month`                                      | `retention_days`, estimated log volume                                        |
| **S3**                    | storage_gb × `fast_path_services.s3.storage_per_gb_month` + request estimates (or `s3.monthly_baseline_est`)                             | `storage_gb` (from Bucketeer/Cloudinary mapping)                              |
| **Amazon SES**            | `fast_path_services.ses.monthly_baseline_est` (flat baseline; see `_basis`)                                                              | Flat estimate from SendGrid mapping                                           |
| **EventBridge Scheduler** | `fast_path_services.eventbridge.monthly_baseline_est` (flat; per_million_events basis)                                                   | From Heroku Scheduler mapping                                                 |
| **Amazon MQ**             | `fast_path_services.amazon_mq.instance_monthly_est` + storage                                                                            | From CloudAMQP mapping                                                        |
| **Amazon OpenSearch**     | `fast_path_services.opensearch.instance_monthly_est` + storage                                                                           | From Bonsai Elasticsearch mapping                                             |
| **Secrets Manager**       | secret_count × `fast_path_services.secrets_manager.per_secret_month` + API calls × `per_10k_api_calls` (or `monthly_baseline_est`)       | Config var count from inventory                                               |
| **NAT Gateway**           | `nat_gateway.monthly_fixed` + data processing estimate (`nat_gateway.per_gb_processed`)                                                  | From VPC design (if new VPC)                                                  |
| **RDS Proxy**             | `rds_proxy.per_vcpu_hour` × 730 × vCPUs                                                                                                  | When connection pooling mapped                                                |
| **Route 53**              | `route53.hosted_zone_monthly` + query estimate (`route53.per_million_queries`)                                                           | When DNS strategy = route53                                                   |
| **CloudFront**            | `fast_path_services.cloudfront.per_gb_first_10tb` × GB + request costs (or `cloudfront.monthly_baseline_est`)                            | From Cloudinary composite mapping                                             |
| **X-Ray**                 | `cloudwatch.xray_per_million_traces` × trace_millions                                                                                    | Only if tracing detected in source                                            |

### Unpriced Resource Handling

IF pricing data for a service is unavailable from both MCP and cache:

1. Mark the resource's cost as `"unpriced"` in the per-service breakdown
2. **Exclude** from the total monthly cost sum
3. Add to `warnings[]`: "Pricing unavailable for [service_id] ([aws_service]). Requires manual cost verification."
4. Add service name to `pricing_source.services_with_missing_fallback[]`

### EKS Cost Calculation

When `aws-design.json` contains EKS services (`aws_service: "EKS"`):

1. **EKS Control Plane**: `eks.control_plane_monthly` (fixed, one cluster regardless of node count)
2. **EC2 Node Group**: Look up the node instance type's monthly rate in `eks.node_rates_monthly[type]` × `desired_size` nodes. The monthly rates (m6i.large, m6i.xlarge, m6i.4xlarge, r6i.4xlarge, m6i.8xlarge, m6i.16xlarge) are maintained in `aws-infra-pricing.json` — do not hardcode them here.
3. **ALB for web services**: Same as Fargate ALB pricing (`alb.monthly_fixed` per web service)
4. **NAT Gateway** (if private subnets): Same as Fargate path (`nat_gateway.monthly_fixed` + data processing)

**Total EKS monthly cost** = `eks.control_plane_monthly` + (node_monthly_rate × node_count) + ALB_costs + NAT_costs. Pods are NOT charged a per-task cost (compute is billed via the EC2 nodes); ALB and NAT are the separate lines above, not re-added here.

**EKS vs Fargate cost comparison note**: When presenting EKS estimates alongside the Heroku baseline, include this note:

> "EKS with EC2 nodes is typically cheaper than Fargate for sustained workloads (>60% utilization) because there is no per-pod Fargate surcharge. However, EKS has a higher base cost (`eks.control_plane_monthly` control plane + minimum 2 nodes) and requires Kubernetes operational expertise."

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

Use the per-service log-volume heuristic from [`knowledge/estimate/estimate-defaults.json`](../../../knowledge/estimate/estimate-defaults.json) → `log_volume_gb_per_service` (billing data not applicable for log volume since Heroku's logging model differs). Keyed by service: `fargate_task` (per task), `rds_or_aurora_instance` (per instance), `alb` (per load balancer), `nat_gateway` (per gateway), `elasticache_node` (per node), `msk_broker` (per broker).

Sum across all applicable services.

### Step 2: Estimate Custom Metrics and Alarms

- `custom_metrics_count = (number of services in aws-design.json × 5)`
- Default floor: 10 custom metrics
- `alarm_count = max(5, number_of_services × 2)` (baseline health/error/latency)

### Step 3: Calculate CloudWatch Costs

```
log_ingestion_cost    = monthly_log_gb × cloudwatch.log_ingestion_per_gb
log_storage_cost      = monthly_log_gb × cloudwatch.log_storage_per_gb_month × retention_months (use preferences.operational.log_retention_days / 30, default: 1)
custom_metrics_cost   = custom_metrics_count × cloudwatch.custom_metric_month
alarms_cost           = alarm_count × cloudwatch.standard_alarm_month
tracing_cost          = 0 (do not add X-Ray costs unless tracing detected in source)

total_observability   = log_ingestion_cost + log_storage_cost + custom_metrics_cost + alarms_cost + tracing_cost
```

(All `cloudwatch.*` rates are in `references/vendored/pricing/aws-infra-pricing.json`.)

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

The savings ranges + applicability come from [`knowledge/estimate/estimate-defaults.json`](../../../knowledge/estimate/estimate-defaults.json) → `optimization_savings_ranges` (keys: `compute_savings_plans`, `database_savings_plans`, `rds_reserved_instances`, `s3_intelligent_tiering`, `fargate_spot`; each carries `savings_percent` / `target_services` / `timing`). Include ONLY opportunities relevant to the designed architecture (per each entry's `target_services` / `timing`).

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

Load the tier thresholds declared in `_knowledge` (`references/vendored/estimate/complexity-tiers.json`). Classify using these inputs from the current artifacts:

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

**Timeline guidance** (infrastructure path):

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

When Parts 1–8 are complete, control passes to the assembler (`estimate-assemble.md`) to
write `estimation-infra.json`, run the handoff gate, and update phase status.

---

## Pricing Recipes (MCP Fallback Only)

Only use these recipes when a service is NOT in `references/vendored/pricing/aws-infra-pricing.json` and MCP is available. Do NOT call `get_pricing_service_codes` or `get_pricing_service_attributes` — go directly to `get_pricing`.

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
