# Organization & Guardrails (Q7.5–Q7.6, within Category A)

These questions determine account structure and lightweight guardrail policies. They are positioned within Category A (Global/Strategic) after Q7 (maintenance window) and before Category B/C begins. The agent computes a tailored recommendation from existing signals before presenting the question — the user confirms or overrides rather than deciding cold.

**Note:** This is NOT a separate category letter. It extends Category A with Q7.5 and Q7.6. Category G is already used by Agentic Workflows (Q23–Q26) in `clarify-ai.md`.

---

## Firing Rules

Organization questions (Q7.5–Q7.6) fire WHEN:

- Migration type is "full" (not AI-only)
- AND fast-path was NOT chosen by user (if user chose full clarify despite being eligible, these questions still fire)

Organization questions do NOT fire WHEN:

- AI-only migration (no infrastructure artifacts)
- Fast-path was chosen by user (fast-path applies defaults silently)

When organization questions do **not** fire, write the following default to `preferences.json` and skip Q7.5/Q7.6:

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

---

## Step 1: Run Recommendation Engine (BEFORE presenting Q7.5)

**CRITICAL:** You MUST compute the organization recommendation BEFORE presenting Q7.5 to the user. Load and evaluate the decision table in `../../../../shared/org-recommendation-engine.md`.

**Instructions:**

1. Read signal sources from existing artifacts:
   - `preferences.json` → `design_constraints.compliance.value`
   - `preferences.json` → `design_constraints.gcp_monthly_spend.value`
   - `migration-preview.json` → `complexity_tier`
   - `gcp-resource-clusters.json` → cluster count + AI-only flag + prod/nonprod separation
   - `preferences.json` → `design_constraints.availability.value`
   - `migration-preview.json` → `eligible_for_clarify_fast_path`

2. Evaluate the profile assignment algorithm (Profile 3 → Profile 2 → Profile 1 fallthrough)
3. Store the computed `org_recommendation` object (`value`, `confidence`, `reasons[]`)
4. Use the recommendation to pre-select the default option when presenting Q7.5

If any signal source is unavailable, follow the fallback behavior defined in the recommendation engine reference. Never block the clarify flow — always produce a valid recommendation.

---

## Step 2: Q7.5 — Account Structure

**Rationale:** Account structure affects isolation, billing visibility, and compliance posture. Most early-stage startups (~70%) use a single account successfully.

Present the question with the pre-computed recommendation displayed:

> Based on your [signals summary], I recommend: **[Profile Name]**
>
> Reasons:
>
> - [plain-language reason 1 from recommendation engine]
> - [plain-language reason 2 from recommendation engine]
>
> A) Use recommendation ([profile name]) — default
> B) Separate prod and dev accounts _(not shown when recommendation is "defer-multi-account" — see Defer handling below)_
> C) Not sure — stick with single account
>
> _This question is optional. Most early-stage startups use a single account._

**Defer-profile UX rule:** When the recommendation is `"defer-multi-account"`, do NOT present option B. Instead show only:

> A) Use recommendation (single account for now, revisit later) — default
> C) Not sure — stick with single account
>
> _Your workload complexity suggests engaging a platform team before adopting multi-account. We'll include guidance in the migration report._

If the user explicitly asks for multi-account despite the defer recommendation, honor it (set `user_override: true`, proceed to Q7.6). But do not proactively offer B when the recommendation says "you need a platform team."

**Signal summary formatting:** Summarize the key signals that drove the recommendation in a short phrase. Examples:

- "your SOC2 compliance and $8K/mo spend"
- "your simple stack and low spend"
- "your FedRAMP compliance and Large migration complexity"

| Answer                 | Recommendation Impact                                                                       |
| ---------------------- | ------------------------------------------------------------------------------------------- |
| A (Use recommendation) | Accept the computed recommendation as-is; profile maps to `org_structure` per mapping table |
| B (Separate prod/dev)  | Override to multi-account regardless of recommendation; presents Q7.6 follow-up             |
| C (Not sure)           | Default to single-account; no follow-up questions                                           |
| Skip (no selection)    | Default to single-account; no follow-up questions                                           |

Interpret:

```
A -> org_structure = map(recommendation.value), chosen_by = "user", user_override = false
B -> org_structure = "multi-account", chosen_by = "user", user_override = true
C -> org_structure = "single-account", chosen_by = "default", user_override = true
Skip -> org_structure = "single-account", chosen_by = "default", user_override = true
```

**Recommendation value → org_structure mapping:**

| recommendation.value    | org_structure written to preferences                                   |
| ----------------------- | ---------------------------------------------------------------------- |
| `"single-account"`      | `"single-account"`                                                     |
| `"prod-dev-split"`      | `"multi-account"`                                                      |
| `"defer-multi-account"` | `"single-account"` (no Terraform org resources; education-only report) |

Default: A — pre-selected to the computed recommendation (the user confirms with a single selection).

---

## Step 3: Q7.6 — Guardrail Policies (Conditional)

**Fires when:** Q7.5 resolved to `org_structure: "multi-account"` (either via recommendation acceptance when recommendation is `"prod-dev-split"`, or via user selecting option B).

**Does NOT fire when:** Q7.5 resolved to `org_structure: "single-account"` (option A with single-account/defer recommendation, option C, or Skip).

**Rationale:** SCPs provide lightweight account-level guardrails without Control Tower. These are minimal, startup-friendly policies.

> Which guardrail policies would you like applied to your organization?
> _(Multi-select: choose one or more, or E for none)_
>
> A) Deny leaving the organization
> B) Restrict to your target region ([region from Q1])
> C) Deny root user access in member accounts
> D) All of the above — recommended minimal set
> E) None — just the account structure

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

Interpret:

```
A -> guardrail_scps: ["deny-leave-org"]
B -> guardrail_scps: ["region-restrict"]
C -> guardrail_scps: ["deny-root"]
D -> guardrail_scps: ["deny-leave-org", "region-restrict", "deny-root"]
E -> guardrail_scps: []
Multi-select (any combination of A, B, C) -> guardrail_scps: [corresponding values]
```

Default: D — `guardrail_scps: ["deny-leave-org", "region-restrict", "deny-root"]`.

---

## Step 4: Write `org_guardrails` to preferences.json

After Q7.5 (and Q7.6 if applicable), write the `org_guardrails` object as a top-level key in `preferences.json`.

### Schema

```json
{
  "org_guardrails": {
    "org_structure": "<string>",
    "guardrail_scps": ["<string>", ...],
    "chosen_by": "<string>",
    "recommendation": {
      "value": "<string>",
      "confidence": "<string>",
      "reasons": ["<string>", ...]
    },
    "user_override": <boolean>
  }
}
```

### Field Constraints

| Field                       | Type     | Valid Values                                                                  | Default            |
| --------------------------- | -------- | ----------------------------------------------------------------------------- | ------------------ |
| `org_structure`             | string   | `"single-account"`, `"multi-account"`                                         | `"single-account"` |
| `guardrail_scps`            | string[] | subset of `{"deny-leave-org", "region-restrict", "deny-root"}`, no duplicates | `[]`               |
| `chosen_by`                 | string   | `"user"`, `"default"`                                                         | `"default"`        |
| `recommendation.value`      | string   | `"single-account"`, `"prod-dev-split"`, `"defer-multi-account"`               | —                  |
| `recommendation.confidence` | string   | `"high"`, `"medium"`, `"low"`                                                 | —                  |
| `recommendation.reasons`    | string[] | 1+ human-readable strings                                                     | —                  |
| `user_override`             | boolean  | `true`, `false`                                                               | `true`             |

### Invariants (enforce at write time)

1. When `org_structure == "single-account"` → `guardrail_scps` MUST be `[]`
2. When `org_structure == "multi-account"` → `guardrail_scps` contains 0–3 items from the valid set, no duplicates
3. `user_override == false` ONLY when user selected option A (accept recommendation)
4. `recommendation` object MUST always be present with all three fields populated
5. `recommendation.reasons` MUST contain at least one entry

### Validation

**Before writing**, validate the `org_guardrails` object against the constraints above. If any field contains a value outside its defined valid set:

1. **Reject the write** — do not modify `preferences.json`
2. **Surface an error** naming the invalid field and its invalid value
3. **Leave the prior `preferences.json` file unchanged**

### Conflicting State Resolution

If `org_structure == "single-account"` but `guardrail_scps` is non-empty, clear `guardrail_scps` to `[]` and log a warning before writing.
