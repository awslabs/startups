---
_assemble: estimate-assemble
_of_phase: estimate
_reads:
  - cost-engine (full estimation-infra.json content)
_produces:
  - estimation-infra.json
---

# Estimate Phase: Assembler

> Writes `estimate-cost-engine.md`'s contribution to `estimation-infra.json`,
> validates it against the vendored schema, runs the Property-16 arithmetic
> check and all postconditions, and emits `HANDOFF_OK`. This is the SINGLE
> creator of `estimation-infra.json`.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Write `estimation-infra.json`

Write the full object produced by `estimate-cost-engine.md`, adding phase
metadata:

```json
{
  "phase": "estimate",
  "design_source": "recommendation.json",
  "timestamp": "<ISO 8601>",
  "pricing_source": {
    "status": "cached" | "live" | "cached_fallback" | "unavailable",
    "message": "<human-readable pricing mode from Step 0c>",
    "services_by_source": { "live": [], "fallback": [], "estimated": [] }
  },
  "accuracy_confidence": "+/-5-10% for cached infrastructure pricing",
  "current_costs": {
    "source": "api_billing_data" | "user_provided" | "plan_estimation" | "unavailable",
    "vercel_monthly": <number or null>,
    "baseline_note": "<explanation of source and confidence>"
  },
  "projected_costs": {
    "aws_monthly_premium": <number>,
    "aws_monthly_balanced": <number>,
    "aws_monthly_optimized": <number>,
    "aws_annual_optimized": <aws_monthly_optimized * 12>,
    "breakdown": {
      "total": { "premium": <N>, "mid": <N>, "low": <N> },
      "<service_name>": { "premium": <N>, "mid": <N>, "low": <N>, "pricing_source": "..." }
    }
  },
  "cost_comparison": { ... } | null,
  "roi_analysis": { ... },
  "optimization_opportunities": [ ... ],
  "migration_cost_considerations": {
    "estimated_effort": "<complexity tier -> effort range>",
    "one_time_costs": "<data transfer, parallel-run period>"
  },
  "tiebreak_alternative": { "outcome": "B", "aws_monthly_premium": <N>, "aws_monthly_balanced": <N>, "aws_monthly_optimized": <N>, "breakdown": { ... } },
  "complexity_tier": "small" | "medium" | "large",
  "complexity_inputs": { ... },
  "financial_summary": {
    "one_liner": "<e.g. 'AWS Balanced is ~$X/mo vs Vercel ~$Y/mo — Z% savings'>",
    "verdict": "cheaper" | "comparable" | "more_expensive"
  },
  "recommendation": {
    "path": "migrate_optimized" | "migrate_phased" | "stay",
    "path_label": "<human-readable one-liner>",
    "migrate_if": [ ... ],
    "stay_if": [ ... ]
  }
}
```

---

`tiebreak_alternative` is present ONLY when `recommendation.json.outcome` is
the unresolved array `["A", "B"]` (see the cost engine's Part 2 tiebreak
handling); `projected_costs` then reflects Outcome A and the alternative
reflects Outcome B.

---


Also attach optional workshop metadata when present:

```json
{
  "workshop": {
    "scenario_id": "<clarify-answers.workshop.active_scenario_id or null>",
    "region_note": "<from cost-engine, or null>"
  }
}
```

Omit `workshop` when neither field is set.


## Step 2: Validate Property-16 (Arithmetic Integrity)

Read back `estimation-infra.json.projected_costs.breakdown`. When
`tiebreak_alternative` is present, run this same check a second time on its
breakdown against its own totals. For each tier (premium, mid/balanced,
low/optimized):

1. Sum all per-service values for that tier.
2. Compare to the corresponding total (`projected_costs.aws_monthly_premium`,
   `aws_monthly_balanced`, `aws_monthly_optimized`).
3. Accept if difference < $0.01 (floating-point rounding tolerance).
4. If difference >= $0.01: recompute the total from the sum and overwrite it
   (the per-service breakdown is the source of truth; totals are derived).

---

## Step 3: Schema Validation

Validate the written file against
`references/vendored/estimate/estimation-infra.schema.json`:

- All `required` top-level fields present (`phase`, `pricing_source`,
  `projected_costs`, `complexity_tier`, `recommendation`)
- `recommendation.path` is one of the enum values
- `projected_costs.aws_monthly_balanced` is a positive number
- `complexity_tier` is one of `{small, medium, large}`

On schema validation failure: surface the specific missing/invalid field and
halt (do NOT emit `HANDOFF_OK`).

---

## Completion Gate

Run the checks declared in `estimate.md`'s `_postconditions`:

1. `estimation-infra.json` exists and parses as valid JSON.
2. `recommendation.path` is one of `{migrate_optimized, migrate_phased, stay}`
   and `recommendation.path_label` is a non-empty string.
3. `recommendation.migrate_if` and `recommendation.stay_if` are non-empty
   arrays.
4. `projected_costs.aws_monthly_balanced` is a positive number.
5. Every service in the design appears in the cost breakdown, or is listed as
   `"unpriced"` in warnings.
6. Property-16: the balanced total equals the arithmetic sum of the per-service
   balanced costs, excluding unpriced (verified in Step 2).
7. `complexity_tier` is one of `{small, medium, large}`.

**On any failure:** emit exactly:

```
GATE_FAIL | phase=estimate | field=<failing field> | reason=<missing|invalid|arithmetic>
```

Do NOT modify artifacts to force a pass. Do NOT update `.phase-status.json`.

**On all-pass (outer Estimate only):** emit exactly:

```
HANDOFF_OK | phase=estimate | artifacts=estimation-infra.json
```

### Inner workshop reprice — skip state transition

When invoked from `workshop-refresh.md` (inner reprice): write
`estimation-infra.json`, optionally soft-check Property-16, present a brief
summary, then **return to the workshop loop**. Do **not** emit `HANDOFF_OK`, do
**not** update `.phase-status.json`, do **not** offer the what-if workshop below.

### Outer Estimate — deferred Generate advance

After outer-run `HANDOFF_OK`:

1. Mark `phases.estimate` → `"completed"`.
2. Ensure `phases.workshop` exists (seed `"pending"` if missing).
3. **Do not** set `current_phase` to `"generate"` yet — leave `current_phase` at
   `"estimate"` until the workshop checkpoint is resolved (entered then exited,
   or declined).
4. Offer the what-if workshop below.

---

## Step 4: Present Cost Summary to Founder

After `HANDOFF_OK`, output a brief cost summary:

> **Cost Estimate Complete**
>
> |                  | Monthly               |
> | ---------------- | --------------------- |
> | Vercel (current) | ~${vercel_monthly}/mo |
> | AWS Premium      | ~${premium}/mo        |
> | **AWS Balanced** | **~${balanced}/mo**   |
> | AWS Optimized    | ~${optimized}/mo      |
>
> Complexity tier: {tier} | Recommendation: {path_label}
>
> Full breakdown in `estimation-infra.json`. Proceeding to generate migration
> artifacts.

If Vercel baseline is unavailable, omit the Vercel row and note "Vercel
baseline unavailable — comparison not shown."

If `tiebreak_alternative` is present (unresolved A-vs-B outcome), show BOTH
paths' tiers side by side (columns "AWS — Outcome A (serverless)" and "AWS —
Outcome B (Fargate)"), and close with: "The outcome is an unresolved tiebreak —
the Generate phase will ask you to pick, and {resolving_input} would also
resolve it."

---



---

## Post-Estimate: What-If Workshop Offer

After outer-run `HANDOFF_OK`, the summary above, and the deferred phase-status
update — offer:

```
Estimate complete. Before Generate, you can run a what-if workshop:
change traffic shape, outcome (A/B/C), region, Multi-AZ, or CPU architecture
(arm64 vs x86) and compare priced scenarios without re-discovering.

[A] Enter what-if workshop
[B] Proceed toward Generate
```

- **A** → Load `references/phases/workshop/workshop.md` (checkpoint; baseline
  capture if `scenarios/` missing, then the sheet). Keep
  `current_phase: estimate`; set `phases.workshop` → `"in_progress"`.
- **B** → Mark `phases.workshop` → `"completed"` (resolved/declined). Set
  `current_phase` → `"generate"`. Continue toward Generate / Report per
  `SKILL.md`.

## Scope Boundary

**This assembler covers writing `estimation-infra.json`, Property-16
validation, the completion gate, the user-facing summary, and the workshop
offer ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Re-running `estimate-cost-engine.md`'s computation logic
- Terraform generation
- Advancing `.phase-status.json` before `HANDOFF_OK` is emitted

**Your ONLY job: write, validate, gate, present, hand off (and offer workshop).**
