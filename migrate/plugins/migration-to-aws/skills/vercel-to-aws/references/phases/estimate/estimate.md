---
_phase: estimate
_title: "Estimate AWS Costs"
_requires_phase: recommend
_advances_to: generate
_input:
  - recommendation.json
  - discovery.json
  - clarify-answers.json
  - coupling-score.json
_knowledge:
  - { file: references/vendored/pricing/aws-infra-pricing.json }
  - { file: references/vendored/estimate/complexity-tiers.json }
  - { file: references/vendored/estimate/estimation-infra.schema.json }
_fragments:
  - _id: cost-engine
    _trigger: { _always: true }
    _file: phases/estimate/estimate-cost-engine.md
_assemble:
  _file: phases/estimate/estimate-assemble.md
_produces:
  - estimation-infra.json
_interactive: false
_exec:
  _agent: rw
_preconditions:
  - _check_phase_completed: recommend
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: [recommendation.json, discovery.json, clarify-answers.json]
    _on_failure: _unrecoverable
  - _validate_json: [recommendation.json, discovery.json, clarify-answers.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: estimation-infra.json
    _on_failure: _halt_and_inform
  - _validate_json: estimation-infra.json
    _on_failure: _halt_and_inform
  - _assert: "recommendation.path is one of {migrate_optimized, migrate_phased, stay} and recommendation.path_label is a non-empty string"
    _on_failure: _halt_and_inform
  - _assert: "recommendation.migrate_if and recommendation.stay_if are non-empty arrays"
    _on_failure: _halt_and_inform
  - _assert: "projected_costs.aws_monthly_balanced is a positive number"
    _on_failure: _halt_and_inform
  - _assert: "every designed service appears in the cost breakdown, or is listed as 'unpriced' in warnings"
    _on_failure: _halt_and_inform
  - _assert: "the balanced total equals the arithmetic sum of the per-service costs, excluding unpriced (Property-16 invariant)"
    _on_failure: _halt_and_inform
  - _assert: "complexity_tier is one of {small, medium, large}"
    _on_failure: _halt_and_inform
_forbids_files:
  - "terraform/**"
  - "scripts/**"
  - MIGRATION_GUIDE.md
  - README.md
  - "*.tf"
---

# Phase: Estimate AWS Costs

**Execute ALL steps in order. Do not skip or optimize.**

Calculate projected monthly AWS costs for the recommended Vercel-to-AWS
architecture, producing `estimation-infra.json` (conforming to
`references/vendored/estimate/estimation-infra.schema.json`) and classifying
migration complexity using the tier thresholds in
`references/vendored/estimate/complexity-tiers.json`. After a successful
assemble, the skill **offers the optional what-if workshop**
(`references/phases/workshop/workshop.md`) before Generate.

---

## Step 0: Validate Prerequisites

The entry gate (recommend completed, single active phase, all inputs present +
valid JSON) is enforced by this phase's `_preconditions` frontmatter per
`INTERPRETER.md` § Gate protocol; proceed once it passes.

---

## Step 1: Compute the Estimate

Load `references/phases/estimate/estimate-cost-engine.md` and follow it. It
selects the pricing mode, validates the inputs, determines current Vercel costs,
computes projected AWS costs per the recommended outcome, classifies complexity,
and produces the full financial picture.

---

## Step 2: Assemble and Validate

Load `references/phases/estimate/estimate-assemble.md` (the phase's assembler)
and follow it to write the final `estimation-infra.json`, run the completion
handoff gate, update `.phase-status.json`, and present the cost summary to the
founder.

---

## Scope Boundary

**This phase covers financial analysis ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Changes to the recommendation outcome (Phase 4 decisions are final)
- Terraform or IaC code generation (Phase 6 handles this)
- Detailed migration procedures or runbooks
- Team staffing, human labor costs, or professional services fees
- Re-running the Recommendation Engine

**Your ONLY job: Show the financial picture of moving from Vercel to AWS.
Nothing else.**
