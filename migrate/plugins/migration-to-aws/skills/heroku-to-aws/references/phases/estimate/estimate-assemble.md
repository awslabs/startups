---
_assemble: assemble-estimation
_of_phase: estimate
_reads:
  - cost-engine (fragment contribution)
_produces:
  - estimation-infra.json
---

# Estimate — Assemble and Validate estimation-infra.json

> **Assembler unit.** Runs after the cost-engine fragment (`estimate-cost-engine.md`)
> has computed the full financial picture. It assembles the final
> `estimation-infra.json`, enforces the completion handoff gate (including the
> Property-16 total invariant + every-service-priced check), updates
> `.phase-status.json`, and presents the summary. It owns the artifact-level
> contract for this phase.

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
