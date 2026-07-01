---
_assemble: assemble-preferences
_of_phase: clarify
_reads:
  - interview (fragment contribution)
_produces:
  - preferences.json
---

# Clarify — Assemble and Validate preferences.json

> **Assembler unit.** Runs after the interview fragment (`clarify-interview.md`)
> has collected and interpreted the answers. It assembles the final
> `preferences.json`, enforces the validation checklist + completion handoff gate,
> and updates `.phase-status.json`. It owns the artifact-level contract for this
> phase (this is a pure validator/finalizer — the interview created the answers,
> the assembler owns the final schema + gate).

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
