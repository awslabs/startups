# Organization & Guardrails (Q7.5–Q7.6, within Strategic Questions)

**Fires when:** Migration type is "full" (not AI-only), AND fast-path was NOT chosen by user (if user chose full clarify despite being eligible, these questions still fire).

**Does NOT fire when:**

- Fast-path was chosen by user (defaults applied silently)
- AI-only migration (no infrastructure artifacts)

**Note:** This is NOT a separate category letter. Category G is used by Agentic Workflows in the AI clarify flow. These org questions extend the strategic batch (after Q4/maintenance window) before infrastructure questions.

**When organization questions do NOT fire:** Write the following default to `preferences.json` and skip this category entirely:

```json
{
  "org_guardrails": {
    "org_structure": "single-account",
    "guardrail_scps": [],
    "chosen_by": "default",
    "recommendation": {
      "value": "single-account",
      "confidence": "low",
      "reasons": ["Organization questions skipped — defaulting to single account"]
    },
    "user_override": true
  }
}
```

**Position:** After strategic questions (region, compliance, spend, maintenance window — Q1–Q4), before infrastructure/data questions (database HA, Redis, Kafka, etc.).

**Loaded by:** The main `clarify.md` orchestrator as a reference when org question routing conditions are met. The Heroku skill uses a single `clarify.md` (not separate category files), so this file is loaded inline when the routing condition is met.

---

## Pre-Computation: Run Recommendation Engine

**BEFORE presenting Q7.5**, load and evaluate the shared recommendation engine:

📄 **Load:** `../../../../shared/org-recommendation-engine.md`

The recommendation engine reads existing discover and clarify signals to compute an `org_recommendation`. It uses the following signal sources adapted for the Heroku skill:

| Signal                         | Artifact                         | Key Path                                                                                | Notes                                                             |
| ------------------------------ | -------------------------------- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Compliance                     | `preferences.json`               | `design_constraints.compliance.value`                                                   | From Q2 answer                                                    |
| Monthly spend                  | `preferences.json`               | `design_constraints.heroku_monthly_spend.value` OR `billing_profile.total_monthly_cost` | Heroku billing data                                               |
| Migration complexity           | `migration-preview.json`         | `complexity_tier`                                                                       | Small / Medium / Large                                            |
| Workload shape — cluster count | `heroku-resource-inventory.json` | Count of distinct app formations + add-on services                                      | Analogous to GCP cluster count                                    |
| Workload shape — AI-only flag  | Discovery artifacts              | `true` if only AI/ML workloads detected (no infra)                                      | `false` for full migrations (org questions won't fire if AI-only) |
| Availability                   | `preferences.json`               | `design_constraints.availability.value`                                                 | From Q3 answer                                                    |
| Fast-path eligibility          | `migration-preview.json`         | `eligible_for_clarify_fast_path`                                                        | Already `false` if org questions fire                             |

### Heroku-Specific Signal Adaptations

- **Cluster count equivalent:** Count distinct app groups that serve different environments. If inventory shows apps with clear prod/staging/dev separation (e.g., `myapp-production`, `myapp-staging` or pipeline stages), set `has_distinct_prod_nonprod_clusters = true`.
- **Spend mapping:** Map Heroku spend brackets the same as GCP: `<$1K`, `$1K-$5K`, `$5K-$20K`, `$20K+`.
- **Complexity tier:** Read directly from `migration-preview.json` — same field as GCP skill.

Execute the recommendation engine's profile assignment algorithm with these signals. Store the result as `org_recommendation`.

---

## Q7.5 — Account Structure

**Rationale:** Account structure affects isolation, billing visibility, and compliance posture. Most early-stage startups (~70%) use a single account successfully.

Present the computed recommendation with plain-language reasons, then ask:

> Based on your [signals summary — e.g., "SOC2 compliance, $8K/mo Heroku spend, and medium migration complexity"], I recommend: **[Profile Name]**
>
> Reasons:
>
> - [reason 1 from recommendation engine]
> - [reason 2 from recommendation engine]
>
> How would you like to structure your AWS account(s)?
>
> A) Use recommendation ([profile name]) — default
> B) Separate prod and dev accounts — two-account structure with lightweight SCPs _(not shown when recommendation is "defer-multi-account")_
> C) Not sure — stick with single account
>
> _This question is optional. Most early-stage startups use a single account._

**Defer-profile UX rule:** When the recommendation is `"defer-multi-account"`, do NOT present option B. Instead show only:

> A) Use recommendation (single account for now, revisit later) — default
> C) Not sure — stick with single account
>
> _Your workload complexity suggests engaging a platform team before adopting multi-account. We'll include guidance in the migration report._

If the user explicitly asks for multi-account despite the defer recommendation, honor it (set `user_override: true`, proceed to Q7.6). But do not proactively offer B when the recommendation says "you need a platform team."

### Answer Interpretation

| Answer                 | Action                                                                                                        |
| ---------------------- | ------------------------------------------------------------------------------------------------------------- |
| A (use recommendation) | `org_structure` = recommendation value mapped per engine rules; `user_override = false`; `chosen_by = "user"` |
| B (separate prod/dev)  | `org_structure = "multi-account"`; `user_override = true`; `chosen_by = "user"`                               |
| C (not sure)           | `org_structure = "single-account"`; `user_override = true`; `chosen_by = "default"`                           |
| Skip (no selection)    | `org_structure = "single-account"`; `user_override = true`; `chosen_by = "default"`                           |

### Recommendation Value → org_structure Mapping

| recommendation.value    | org_structure written to preferences                                   |
| ----------------------- | ---------------------------------------------------------------------- |
| `"single-account"`      | `"single-account"`                                                     |
| `"prod-dev-split"`      | `"multi-account"`                                                      |
| `"defer-multi-account"` | `"single-account"` (no Terraform org resources; education-only report) |

**Note:** Profile 3 ("defer") maps to `org_structure: "single-account"` because no organization Terraform is generated. The distinction is preserved in `recommendation.value` for report generation.

### Routing After Q7.5

- If `org_structure == "multi-account"` → present Q7.6 (Guardrail SCP Selection)
- If `org_structure == "single-account"` OR question was skipped → skip Q7.6, proceed to next batch/category (Data / Network questions)

---

## Q7.6 — Guardrail SCP Selection

**Fires when:** Q7.5 resolved to `org_structure: "multi-account"` (either via recommendation acceptance or user override to option B).

**Rationale:** SCPs provide lightweight account-level guardrails without requiring a full Control Tower deployment. These are the three most impactful guardrails for startups with multiple accounts.

> Which guardrail policies would you like applied to your organization?
> (Multi-select: choose one or more, or E for none)
>
> A) Deny leaving the organization — prevents member accounts from leaving
> B) Restrict to your target region ([region from Q1]) — blocks resource creation outside your region
> C) Deny root user access in member accounts — blocks root actions in member accounts
> D) All of the above — recommended minimal set
> E) None — just the account structure, no SCPs
>
> _Recommendation: D (all three) provides a lightweight guardrail baseline without overhead._

### Answer Interpretation

| Answer | `guardrail_scps` array                               |
| ------ | ---------------------------------------------------- |
| A      | `["deny-leave-org"]`                                 |
| B      | `["region-restrict"]`                                |
| C      | `["deny-root"]`                                      |
| D      | `["deny-leave-org", "region-restrict", "deny-root"]` |
| E      | `[]`                                                 |
| A+B    | `["deny-leave-org", "region-restrict"]`              |
| A+C    | `["deny-leave-org", "deny-root"]`                    |
| B+C    | `["region-restrict", "deny-root"]`                   |

**Default:** D → all three SCPs.

**Multi-select handling:** Users may combine options A, B, and C in any combination. Option D is shorthand for all three. Option E means no SCPs. Options D and E are mutually exclusive with individual selections.

---

## Writing to Preferences JSON

After Q7.5 (and conditionally Q7.6), write the `org_guardrails` object to `preferences.json`:

```json
{
  "org_guardrails": {
    "org_structure": "<single-account | multi-account>",
    "guardrail_scps": ["<selected values or empty array>"],
    "chosen_by": "<user | default>",
    "recommendation": {
      "value": "<single-account | prod-dev-split | defer-multi-account>",
      "confidence": "<high | medium | low>",
      "reasons": ["<reason strings from recommendation engine>"]
    },
    "user_override": <true | false>
  }
}
```

### Validation Rules (MUST enforce before writing)

1. `org_structure` MUST be one of: `"single-account"`, `"multi-account"`
2. `guardrail_scps` MUST be an array containing zero or more values from: `{"deny-leave-org", "region-restrict", "deny-root"}` — no duplicates allowed
3. `chosen_by` MUST be one of: `"user"`, `"default"`
4. `recommendation.value` MUST be one of: `"single-account"`, `"prod-dev-split"`, `"defer-multi-account"`
5. `recommendation.confidence` MUST be one of: `"high"`, `"medium"`, `"low"`
6. `recommendation.reasons` MUST contain at least one string
7. `user_override` MUST be a boolean

### Invariants (MUST be true after write)

- When `org_structure == "single-account"` → `guardrail_scps` MUST be `[]`
- When `org_structure == "multi-account"` AND user selected option E → `guardrail_scps` MUST be `[]`
- `recommendation` object is always present (computed before question is shown)
- `user_override == false` ONLY when user selected option A (accept recommendation)

### Error Handling

If any field would contain a value outside its defined valid set:

1. Reject the write
2. Surface an error indicating the invalid field and value
3. Leave any prior `preferences.json` unchanged
4. Re-prompt the question that produced the invalid state

---

## Profile 3 (Defer) — Special Handling

When the recommendation engine returns `"defer-multi-account"`:

1. Present Q7.5 with the defer recommendation and its reasons (e.g., "FedRAMP compliance combined with Large migration complexity requires a dedicated platform team")
2. Do NOT present option B — only show options A and C (per the defer UX rule above)
3. If user accepts (option A): `org_structure = "single-account"`, `recommendation.value = "defer-multi-account"` — no organization Terraform will be generated, but the Generate phase will include an education-only report section
4. If the user explicitly asks for multi-account despite the defer recommendation (not via option B which is hidden, but via free-text request), honor it: set `user_override: true`, proceed to Q7.6
5. Q7.6 fires normally if the final resolution is multi-account

---

## Integration Notes

- This file is loaded as a **reference** by the main `clarify.md` orchestrator when org question routing conditions are met
- The Heroku skill's `clarify.md` handles all questions in a single file with batched presentation — Q7.5 and Q7.6 are added to **Batch 1 (Global / Strategic)** after Q4 (maintenance window)
- The recommendation engine at `../../../../shared/org-recommendation-engine.md` is the shared logic used by both GCP and Heroku skills
- Signal reading from `heroku-resource-inventory.json` replaces `gcp-resource-clusters.json` for workload shape detection
- All other logic (profiles, confidence, answer mappings, preference writing) is identical across both skills
