---
_fragment: cost-engine
_of_phase: estimate
_contributes:
  - estimation-infra.json
---

# Estimate Phase: Cost Engine

> Self-contained cost-calculation fragment. Selects the pricing mode, determines
> current Vercel costs, computes projected AWS costs per the recommended outcome,
> models three tiers (Premium/Balanced/Optimized), classifies complexity, and
> produces the recommendation. The final artifact write, handoff gate, and
> phase-status update are owned by the assembler (`estimate-assemble.md`).

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 0: Pricing Mode Selection

Execute `references/vendored/estimate/pricing-mode.md` (the canonical
Step 0, vendored from `skills/shared/estimate/pricing-mode.md` and kept
byte-identical by `shared:sync`) as this step: cache staleness check, MCP
retry ladder, pricing-mode display, and the per-service pricing hierarchy
(including the `estimated` and `unavailable` rungs). Do not restate or
fork that logic here.

For typical Vercel migrations (Fargate, Lambda, API Gateway, CloudFront, S3, NAT Gateway, ALB, RDS, ElastiCache, EventBridge, Secrets Manager), ALL prices are in `aws-infra-pricing.json`. Zero MCP calls needed in the common case.

### Step 0a-workshop: What-if knobs (when present)

Read optional `clarify-answers.json.workshop` (created by
`references/phases/workshop/`). Defaults when absent match skill norms:

1. `target_region` (default `us-east-1`). Pricing cache is us-east-1 — when
   `workshop.target_region` differs, prefer MCP lookups for that region; when
   still using cache rates, set `workshop.region_note`:
   `"Rates from us-east-1 cache applied to {target_region} — verify via awspricing MCP for regional deltas."`
2. `availability_multi_az_balanced` — when `true`, price Balanced-tier data
   services Multi-AZ (Premium already does).
3. `cpu_architecture` — `arm64` (default) or `x86_64`; Graviton rates when
   workshop is an explicit comparison override.
4. Carry `workshop.active_scenario_id` into the contribution as
   `workshop.scenario_id` for the assembler.

---

## Part 1: Determine Current Vercel Costs

Use the best available source for Vercel monthly baseline (first match wins):

1. **Vercel API billing data (preferred)** — If
   `discovery.json.usage_metrics.billing_data` is present, use actual billing
   data as the Vercel baseline. Highest confidence.
   - Extract the monthly total and per-feature breakdown
   - Set `current_costs.source: "api_billing_data"`

2. **User-provided from Clarify** — If `clarify-answers.json.Q6_vercel_spend`
   is present (not skipped), parse the range answer:
   - `$0-50` -> use midpoint $25
   - `$50-200` -> use midpoint $125
   - `$200-1000` -> use midpoint $600
   - `$1000+` -> use $1500 (conservative estimate for comparison)
   - `skipped` -> fall through to priority 3
   - Set `current_costs.source: "user_provided"`

3. **Plan-based estimation** — Derive from discovered signals:
   - Pro plan: $20/member/month + usage overage estimation from
     `discovery.json.usage_metrics` (function invocations, bandwidth, build
     minutes) where available
   - Enterprise: mark as "custom pricing, not estimable"
   - Set `current_costs.source: "plan_estimation"`
   - Set `current_costs.accuracy: "+/-30%"`

4. **Unavailable** — If none of the above yields a number: present AWS costs
   without Vercel comparison.
   - Set `current_costs.source: "unavailable"`
   - Note: "Vercel baseline unavailable — AWS costs shown without comparison."

When a baseline is available, present it briefly before proceeding:

> "Current Vercel spend: ~${amount}/month ({source}). Now computing AWS
> projected costs for comparison."

---

## Part 2: Compute Per-Service AWS Costs

Read `recommendation.json.outcome` to determine which AWS services to price.
For each service, look up the rate in the pricing cache (Step 0a) or MCP
(Step 0b), then apply the cost formula.

**Unresolved tiebreak (`outcome == ["A", "B"]`):** this phase is
non-interactive, so it cannot ask the founder to pick (Generate owns that ask).
Price BOTH candidate outcomes — the cost delta between them is itself a
resolving input for the founder's pick:

- `projected_costs` (all three tiers + `breakdown`, and everything downstream
  of them: comparison, complexity, Property-16) is computed from **Outcome A's
  service set** — the array's first element, matching the engine's ordering.
- Add a top-level `tiebreak_alternative` object with the SAME tier structure
  (`aws_monthly_premium/balanced/optimized` + `breakdown`) computed from
  **Outcome B's service set**. Property-16 applies to it independently.
- `financial_summary.one_liner` and `recommendation.path_label` MUST state
  that the outcome is an unresolved A-vs-B tiebreak, give both balanced
  totals, and say that Generate will ask the founder to pick (naming
  `recommendation.resolving_input` as the other way to resolve it).

### Outcome A (OpenNext/SST) — Services to Price

| AWS Service                      | Sizing Source                                                         | Formula                                          |
| -------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------ |
| Lambda (server function)         | Estimated invocations from traffic shape (Q1) + route count           | requests * $0.20/1M + GB-seconds * $0.0000166667 |
| CloudFront                       | Estimated bandwidth from `discovery.json.usage_metrics` or plan-based | requests * $/10K + data_transfer * $/GB          |
| S3 (static assets + ISR cache)   | Asset count + ISR page count from route disposition                   | storage * $/GB/month + requests * $/1K           |
| EventBridge (revalidation queue) | ISR page count * revalidation frequency                               | invocations * $1.00/1M                           |
| Secrets Manager                  | `discovery.json.env_var_names` count                                  | secrets * $0.40/month + API calls * $0.05/10K    |
| NAT Gateway                      | Estimated outbound from Lambda in VPC                                 | hours * $/hr + data * $/GB                       |

### Outcome B (Fargate) — Services to Price

| AWS Service     | Sizing Source                          | Formula                                    |
| --------------- | -------------------------------------- | ------------------------------------------ |
| Fargate (tasks) | Traffic shape + dyno-equivalent sizing | vCPU-hours * $/hr + memory-GB-hours * $/hr |
| ALB             | Always-on for web traffic              | hours * $/hr + LCU-hours * $/LCU-hr        |
| CloudFront      | Same as Outcome A                      | requests * $/10K + data_transfer * $/GB    |
| ECR             | Container image storage                | storage * $/GB/month                       |
| NAT Gateway     | Outbound from private subnets          | hours * $/hr + data * $/GB                 |
| Secrets Manager | Same as Outcome A                      | secrets * $0.40/month                      |

### Outcome C (Hybrid Backend) — Services to Price

Price ONLY the backend compute + peripherals. The Next.js app stays on Vercel,
so its cost continues unchanged — note this explicitly in the comparison.

| AWS Service                                           | Sizing Source                          | Formula                                 |
| ----------------------------------------------------- | -------------------------------------- | --------------------------------------- |
| Lambda + API Gateway (A-shaped) OR Fargate (B-shaped) | Backend route count + traffic estimate | per the matching Outcome A or B formula |
| Peripheral services (only those migrating)            | Per peripheral detection               | per service                             |

**Critical:** Under Outcome C, `current_costs` must split into "stays on
Vercel" vs "migrates to AWS" — the founder's total bill becomes
Vercel-remaining + AWS-new, NOT a full replacement. Surface this clearly.

### Outcome "stay" — Services to Price

Price ONLY peripheral services (if any are being carved off) + baseline
(GuardDuty, CloudTrail, etc. — mostly free-tier eligible). The app itself
stays on Vercel entirely.

### Peripheral Services (All Outcomes)

For each detected peripheral in `discovery.json.peripherals[]`, add its AWS
equivalent cost:

| Peripheral  | AWS Service          | Default Sizing                                                                                               |
| ----------- | -------------------- | ------------------------------------------------------------------------------------------------------------ |
| Postgres    | RDS PostgreSQL       | Sized by Q7: <1GB -> db.t4g.micro, 1-10GB -> db.t4g.small, 10-100GB -> db.r6g.large, >100GB -> db.r6g.xlarge |
| KV          | ElastiCache Redis    | cache.t4g.micro (single node)                                                                                |
| Blob        | S3 Standard          | Estimated storage from discovery                                                                             |
| Cron        | EventBridge + Lambda | Invocations * standard Lambda rate                                                                           |
| Edge Config | SSM Parameter Store  | $0.05/10K API calls (negligible)                                                                             |

---

## Part 3: Three-Tier Modeling

For each service computed in Part 2, produce three cost scenarios by applying
multipliers to the Balanced (default) figure:

| Tier          | Philosophy                                     | Multipliers                                                                                                                                                        |
| ------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Premium**   | Higher HA, production-hardened                 | Multi-AZ databases (2x RDS), larger Fargate tasks (1.5x), provisioned concurrency on Lambda, dedicated NAT per AZ (2x NAT)                                         |
| **Balanced**  | Default posture — what the Terraform generates | Standard instance classes, single NAT, GP3 storage, on-demand pricing                                                                                              |
| **Optimized** | Cost-minimized without degrading functionality | Graviton instances (20% cheaper), Spot for non-critical tasks (60-70% cheaper), S3 Intelligent-Tiering, 1-year reserved capacity where applicable (30-40% savings) |

Sum each tier to produce the three top-line numbers:

- `projected_costs.aws_monthly_premium`
- `projected_costs.aws_monthly_balanced`
- `projected_costs.aws_monthly_optimized`

---

## Part 4: Cost Comparison and ROI

### Cost Comparison

```json
{
  "cost_comparison": {
    "vercel_monthly": <current_costs total>,
    "aws_monthly_balanced": <balanced total>,
    "monthly_delta": <aws_balanced - vercel>,
    "monthly_delta_pct": <delta / vercel * 100>,
    "breakeven_note": "<if negative delta: 'AWS is cheaper by $X/mo'; if positive: 'AWS costs $X/mo more — migration value is operational control, not cost'"
  }
}
```

### ROI Analysis

- **Cost savings** (if AWS cheaper): monthly savings * 12 = annual savings
- **Migration cost** (one-time): complexity-tier-based estimate (small: 1-2
  engineer-weeks, medium: 2-4 weeks, large: 1-2 months)
- **Payback period**: migration_cost / monthly_savings (only when savings exist)
- **Non-financial value**: always list operational control, vendor
  independence, AWS ecosystem access regardless of cost delta

### Optimization Opportunities

List 3-5 concrete opportunities the founder could pursue post-migration:

- Graviton (ARM64) — 20% cost reduction on compute (already defaulted in
  Balanced tier; Premium uses x86 for compatibility)
- Reserved capacity — 30-40% savings with 1-year commitment
- Spot instances — 60-70% savings for fault-tolerant workloads
- S3 lifecycle policies — automatic tiering for infrequently accessed assets
- CloudFront caching optimization — reduce origin hits (and Lambda/Fargate
  invocations) with longer TTLs where ISR revalidation handles freshness

---

## Part 5: Complexity Tier Classification

Read `references/vendored/estimate/complexity-tiers.json`. Evaluate tiers from
`large` down to `small` (highest-matching-tier wins):

**Inputs for classification:**

- `service_count`: count of distinct AWS services in the design (from Part 2)
- `monthly_spend`: `projected_costs.aws_monthly_balanced`
- `multi_region`: always `false` for Vercel migrations (single-region default)
- `compliance_present`: `clarify-answers.json.Q8_compliance.answer != "none"`
- `has_databases`: `discovery.json.peripherals[]` contains `"postgres"` (case-insensitive)
- `availability_multi_az`: only in Premium tier (Balanced is single-AZ default)

Record `complexity_tier` and `complexity_inputs` (the values that fed the
classification) in the output.

---

## Part 6: Financial Recommendation Path

Based on the cost comparison and complexity tier, determine
`recommendation.path`:

| Path                | Condition                                                                                                                                      |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `migrate_optimized` | AWS Balanced cost <= Vercel current cost (clear financial win)                                                                                 |
| `migrate_phased`    | AWS Balanced cost > Vercel current BUT delta < 30% AND non-financial benefits are strong (operational control, vendor lock-in reduction)       |
| `stay`              | AWS Balanced cost > Vercel current BY > 50% AND no compelling non-financial offset — OR recommendation.outcome from Phase 4 was already "stay" |

Populate:

- `recommendation.path_label`: human-readable one-liner (e.g. "Migrate — AWS
  is ~$X/mo cheaper with comparable capability")
- `recommendation.migrate_if`: array of conditions favoring migration
- `recommendation.stay_if`: array of conditions favoring staying on Vercel

---

## Output Contribution for Parent Orchestrator

The full `estimation-infra.json` object conforming to the vendored schema. The
assembler (`estimate-assemble.md`) writes it to disk and validates it.

---

## Error Handling

| Error Category                                               | Behavior                                                                                                                                                     |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| A service is not in the pricing cache AND MCP is unavailable | Mark that service as `pricing_source: "unavailable"` in the per-service breakdown; exclude from totals; add to `warnings`                                    |
| Vercel current cost is unavailable                           | Present AWS costs standalone; set `cost_comparison` to null; `recommendation.path` still evaluable (defaults to `migrate_phased` when comparison impossible) |
| Property-16 arithmetic doesn't balance (rounding)            | Accept if difference < $0.01; otherwise recompute                                                                                                            |
| `recommendation.json.outcome` is "stay"                      | Still compute baseline/peripheral costs (they're valuable even without a full migration); set `recommendation.path: "stay"` unconditionally                  |

---

## Scope Boundary

**This fragment covers cost computation ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Terraform or IaC code generation
- Changes to the recommendation outcome
- Migration timelines beyond complexity-tier classification
- Re-running the Recommendation Engine

**Your ONLY job: compute the financial picture. Nothing else.**
