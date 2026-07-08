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

Assemble the full artifact conforming to `references/vendored/estimate/estimation-infra.schema.json`
(that schema is the field contract — do not re-enumerate it here). Each section is the
corresponding output the cost-engine fragment computed: `pricing_source` +
`current_costs` (Part 1), `projected_costs` (Parts 2/2B), `cost_comparison` (Part 3),
`migration_cost_considerations` (Part 4), `roi_analysis` (Part 5),
`optimization_opportunities` (Part 6), `complexity_tier` + `complexity_inputs`
(Part 7), and `recommendation` (Part 8).

The assembler additionally DERIVES the `financial_summary` roll-up (not produced by
any single cost-engine Part; the schema leaves its shape open):

```json
{
  "financial_summary": {
    "current_heroku_monthly": "<N or null>",
    "projected_aws_balanced_monthly": "<N>",
    "projected_aws_optimized_monthly": "<N>",
    "monthly_savings_balanced": "<heroku - balanced, negative = AWS more expensive>",
    "monthly_savings_optimized": "<heroku - optimized>",
    "annual_savings_optimized": "<× 12>",
    "recommendation": "<summary sentence>"
  }
}
```

Write to `$MIGRATION_DIR/estimation-infra.json`.

---

## Completion Handoff Gate (Fail Closed)

The completion checks are declared in this phase's `_postconditions` frontmatter
and enforced per `INTERPRETER.md` § Gate protocol: **re-read `estimation-infra.json`
from disk**, run the mechanical checks (`_check_file_exists` / `_validate_json`) and
the `_assert` judgment checks (recommendation shape, the Property-16 total-invariant,
every-service-priced, complexity tier), then emit `GATE_FAIL` (do NOT patch artifacts;
STOP) or `HANDOFF_OK | phase=estimate | artifacts=estimation-infra.json` and advance.

One check needs this fragment's context: `estimation-infra.json` must also pass
`references/vendored/estimate/estimation-infra.schema.json` validation (the schema shape) — verify that as part
of the `_validate_json` postcondition.

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
