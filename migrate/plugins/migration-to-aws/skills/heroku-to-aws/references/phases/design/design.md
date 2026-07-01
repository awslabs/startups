---
_phase: design
_title: "Design AWS Architecture"
_requires_phase: clarify
_input:
  - heroku-resource-inventory.json
  - preferences.json
_fragments:
  - _id: mapping-engine
    _trigger: { _always: true }
    _file: phases/design/design-mapping.md
  - _id: eks-mapping
    _trigger: { _when: "preferences.design_constraints.kubernetes.value is 'eks-managed' or 'eks-or-ecs'" }
    _file: phases/design/design-eks.md
_assemble:
  _file: phases/design/design-assemble.md
_produces:
  - aws-design.json
_advances_to: estimate
---

# Phase 3: Design AWS Architecture

Single-pass mapping engine that translates each Heroku resource to its AWS equivalent using deterministic lookup tables. No clustering, no dependency graphs — resources are processed as a flat list in input order.
**Execute ALL steps in order. Do not skip or deviate.**

## Sub-Files

- **design-mapping.md** → the always-on mapping engine: prerequisites, single-pass resource mapping (Elastic Beanstalk/Fargate/RDS/ElastiCache/MSK/fast-path/deferred), VPC + security-group design, Cedar/Fir notation, and metadata.
- **design-eks.md** → the EKS branch: fires (via its `_when` trigger) only when `design_constraints.kubernetes.value` is `"eks-managed"` or `"eks-or-ecs"`; maps ALL formations to EKS pods + an `eks_cluster` aggregate instead of the default EB path.
- **design-assemble.md** → the assembler: writes `aws-design.json`, runs the output route gates + completion handoff gate, and updates `.phase-status.json`.

## Lookup Table References (Conditional Loading)

Load these reference files **only when the corresponding resource type exists in the inventory**:

| Resource Type in Inventory                                                                    | Reference File to Load                                             |
| --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `formation` (any) + `design_constraints.kubernetes.value` = `"eks-managed"` or `"eks-or-ecs"` | `design-refs/eks-mapping-table.md` + `phases/design/design-eks.md` |
| `formation` (any) + `design_constraints.kubernetes.value` = `"ecs-fargate"`                   | `design-refs/dyno-type-table.md`                                   |
| `formation` (any) + `design_constraints.kubernetes.value` = `"elastic_beanstalk"` or absent   | (no additional file needed — EB mapping is inline in `design-mapping.md`) |
| `addon:*:heroku-postgresql:*`                                                                 | `design-refs/postgres-plan-table.md`                               |
| `addon:*:heroku-redis:*`                                                                      | `design-refs/redis-plan-table.md`                                  |
| `addon:*:heroku-kafka:*`                                                                      | `design-refs/kafka-plan-table.md`                                  |
| `addon:*` (non-core)                                                                          | `design-refs/fast-path-table.md`                                   |

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

## Step 1: Run the Mapping Engine

Load `references/phases/design/design-mapping.md` and follow it. It validates
prerequisites, performs the single-pass resource mapping (loading `design-eks.md`
for formations when the Kubernetes preference selects EKS), designs the VPC +
security groups, and adds Cedar/Fir notation + metadata.

---

## Step 2: Assemble and Validate

Load `references/phases/design/design-assemble.md` (the phase's assembler) and
follow it to write `aws-design.json`, run the output route gates + completion
handoff gate, and update `.phase-status.json`. It owns the artifact-level contract
for this phase.

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
