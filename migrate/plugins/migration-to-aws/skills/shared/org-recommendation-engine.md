# Organization Recommendation Engine

This reference defines how to compute a tailored organization structure recommendation from existing discover and clarify signals. The agent evaluates this decision table BEFORE presenting Q7.5 to the user.

The output is an `org_recommendation` object containing a profile value, confidence level, and one or more plain-language reasons.

---

## Signal Sources

Read the following signals from existing artifacts. If a signal is unavailable, mark it as `unknown`.

| Signal                         | Artifact                     | Key Path                                     | Example Values                                                |
| ------------------------------ | ---------------------------- | -------------------------------------------- | ------------------------------------------------------------- |
| Compliance                     | `preferences.json`           | `design_constraints.compliance.value`        | `"none"`, `"gdpr"`, `"soc2"`, `"pci"`, `"hipaa"`, `"fedramp"` |
| GCP monthly spend              | `preferences.json`           | `design_constraints.gcp_monthly_spend.value` | `"<$1K"`, `"$1K-$5K"`, `"$5K-$20K"`, `"$20K+"`                |
| Migration complexity           | `migration-preview.json`     | `complexity_tier`                            | `"Small"`, `"Medium"`, `"Large"`                              |
| Workload shape — cluster count | `gcp-resource-clusters.json` | count of top-level cluster entries           | integer                                                       |
| Workload shape — AI-only flag  | `gcp-resource-clusters.json` | all clusters are AI/ML type with no infra    | `true` / `false`                                              |
| Availability                   | `preferences.json`           | `design_constraints.availability.value`      | `"single-az"`, `"multi-az"`, `"multi-az-ha"`                  |
| Fast-path eligibility          | `migration-preview.json`     | `eligible_for_clarify_fast_path`             | `true` / `false`                                              |

### Reading Cluster Shape

To determine `has_distinct_prod_nonprod_clusters`:

- Inspect `gcp-resource-clusters.json` cluster names and labels
- If clusters contain clear prod/nonprod separation (e.g., `prod-api`, `dev-api` or labels like `env: production`, `env: development`), set to `true`
- Otherwise set to `false`

To determine `cluster_count`:

- Count the number of top-level cluster entries in `gcp-resource-clusters.json`

---

## Three Profiles

| Profile   | Value                 | Description                                                                                     | Artifact Output                                                    |
| --------- | --------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Profile 1 | `single-account`      | Default for ~70% of startups. Single AWS account, no org structure. Permission boundaries only. | Permission boundary in `baseline.tf`                               |
| Profile 2 | `prod-dev-split`      | Two-account structure with Production and Development OUs. Lightweight SCPs.                    | `organizations.tf` with OUs, accounts, and optional SCPs           |
| Profile 3 | `defer-multi-account` | Complex case requiring platform team. Education-only — no Terraform generated.                  | Report section explaining multi-account benefits and prerequisites |

---

## Profile Assignment Algorithm

Evaluate the following decision table top-to-bottom. The FIRST matching profile wins. If no explicit match is found, fall through to Profile 1 (default).

### Step 1: Check for Profile 3 (Defer Multi-Account)

Profile 3 triggers when the startup needs complexity beyond what this plugin generates.

| Condition                                                                         | Confidence | Reason                                                                                                                              |
| --------------------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `complexity == "Large"` AND `compliance` includes `"fedramp"`                     | high       | "FedRAMP compliance combined with Large migration complexity requires a dedicated platform team — deferring to specialist guidance" |
| `cluster_count > 6` AND `compliance` includes any of `"soc2"`, `"pci"`, `"hipaa"` | medium     | "Many workload clusters ({count}) combined with {compliance} compliance suggest a full multi-account structure beyond plugin scope" |

If either condition matches → return Profile 3 with the stated confidence and reason. **Stop here.**

### Step 2: Check for Profile 2 (Prod/Dev Split)

Evaluate ALL of the following conditions. Collect matching reasons. If at least one reason is collected, assign Profile 2.

| Condition                                                                | Reason to collect                                                                              | Confidence contribution |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- | ----------------------- |
| `compliance` includes any of `"soc2"`, `"pci"`, `"hipaa"`                | "Your {value} compliance benefits from account-level isolation for audit clarity"              | high                    |
| `spend` is `"$5K-$20K"` AND `has_distinct_prod_nonprod_clusters == true` | "Your spend level ({value}/mo) and distinct prod/nonprod workloads warrant account separation" | medium                  |
| `complexity` is `"Medium"` or `"Large"`                                  | "Migration complexity ({tier}) warrants separating production from development environments"   | medium                  |
| `availability == "multi-az-ha"` AND `cluster_count >= 2`                 | "Mission-critical availability with multiple workloads supports prod/dev isolation"            | medium                  |

**Confidence resolution for Profile 2:**

- If any condition contributed `high` → final confidence = `high`
- Else if any condition contributed `medium` → final confidence = `medium`
- Else → final confidence = `low`

If one or more reasons were collected → return Profile 2 with resolved confidence and all collected reasons. **Stop here.**

### Step 3: Assign Profile 1 (Single Account — Default)

If neither Profile 3 nor Profile 2 matched, assign Profile 1. Collect applicable reasons:

| Condition                                | Reason                                                                  |
| ---------------------------------------- | ----------------------------------------------------------------------- |
| `complexity == "Small"`                  | "Simple migration complexity — single account is sufficient"            |
| `spend` is `"<$1K"` or `"$1K-$5K"`       | "Low monthly spend ({value}) — multi-account overhead is not justified" |
| AI-only flag is `true`                   | "AI-only workloads don't require account-level isolation"               |
| `eligible_for_clarify_fast_path == true` | "Fast-path eligible — straightforward migration suits single account"   |
| `compliance` is `"none"` or `"gdpr"`     | "No compliance requirements that demand account separation"             |

**Confidence for Profile 1:**

- If 2+ reasons collected → `high`
- If 1 reason collected → `high`
- If 0 reasons collected (no signals matched) → `low` (use fallback reason)

**Fallback reason** (when no specific signals matched): "No signals indicate multi-account complexity is needed — defaulting to single account"

---

## Confidence Levels

| Level    | Meaning                                                                 | When it applies                                                                                           |
| -------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `high`   | Strong signal alignment — recommendation is clear-cut                   | Multiple signals agree, or a single strong signal (compliance, FedRAMP) drives the decision unambiguously |
| `medium` | Mixed signals — recommendation is reasonable but user input is valuable | Signals partially support the recommendation; some contradict or are absent                               |
| `low`    | Weak signals — defaulting to simpler option, user judgment preferred    | Most signals are unavailable, or no clear pattern emerges from available data                             |

---

## Fallback Behavior (Missing Signals)

When signals are unavailable or cannot be read:

| Scenario                                                         | Behavior                                                                                                                          |
| ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `preferences.json` is missing or unreadable                      | Default to Profile 1, confidence `low`, reason: "Unable to read preferences — defaulting to single account"                       |
| `migration-preview.json` is missing                              | Treat `complexity_tier` as `unknown` and `eligible_for_clarify_fast_path` as `false`; continue evaluation with available signals  |
| `gcp-resource-clusters.json` is missing                          | Treat `cluster_count` as `unknown` and `ai_only` as `false`; continue evaluation with available signals                           |
| All signals are unavailable                                      | Return `{value: "single-account", confidence: "low", reasons: ["Insufficient signals available — defaulting to single account"]}` |
| A specific field is null or absent in an otherwise readable file | Treat that individual signal as `unknown` and skip conditions that depend on it                                                   |

**Rule:** Never fail or block the clarify flow due to missing signals. Always produce a valid recommendation. When uncertain, default to Profile 1 with `low` confidence.

---

## Output Format

The recommendation engine produces the following object, which is stored in `preferences.json` under `org_guardrails.recommendation`:

```json
{
  "value": "single-account" | "prod-dev-split" | "defer-multi-account",
  "confidence": "high" | "medium" | "low",
  "reasons": [
    "Plain-language explanation string 1",
    "Plain-language explanation string 2"
  ]
}
```

### Constraints

- `value` MUST be one of: `"single-account"`, `"prod-dev-split"`, `"defer-multi-account"`
- `confidence` MUST be one of: `"high"`, `"medium"`, `"low"`
- `reasons` MUST contain at least one entry
- Reason strings should be human-readable and reference the specific signals that drove the recommendation (e.g., mention the compliance type, spend bracket, or complexity tier)

---

## Mapping: Recommendation Value → org_structure

When the user accepts the recommendation (option A at Q7.5), map the recommendation value to `org_structure`:

| recommendation.value    | org_structure written to preferences                                   |
| ----------------------- | ---------------------------------------------------------------------- |
| `"single-account"`      | `"single-account"`                                                     |
| `"prod-dev-split"`      | `"multi-account"`                                                      |
| `"defer-multi-account"` | `"single-account"` (no Terraform org resources; education-only report) |

Note: Profile 3 ("defer") maps to `org_structure: "single-account"` because no organization Terraform is generated. The distinction is preserved in `recommendation.value` for report generation.

---

## Example Evaluations

### Example 1: Simple startup, no compliance

**Signals:** complexity = Small, compliance = none, spend = $1K-$5K, cluster_count = 2, ai_only = false, availability = single-az, fast_path = true

**Evaluation:**

- Step 1 (Profile 3): No match — complexity is not Large, cluster_count ≤ 6
- Step 2 (Profile 2): No match — no compliance, spend < $5K-$20K, availability not multi-az-ha
- Step 3 (Profile 1): Reasons collected: "Simple migration complexity", "Low monthly spend ($1K-$5K)", "Fast-path eligible"

**Result:** `{value: "single-account", confidence: "high", reasons: [...]}`

### Example 2: SOC2 startup with medium spend

**Signals:** complexity = Medium, compliance = soc2, spend = $5K-$20K, cluster_count = 3, ai_only = false, has_distinct_prod_nonprod = true, availability = multi-az, fast_path = false

**Evaluation:**

- Step 1 (Profile 3): No match — compliance is soc2 not fedramp, cluster_count ≤ 6 with soc2 doesn't hit >6 threshold
- Step 2 (Profile 2): Compliance SOC2 → reason collected (confidence high). Spend $5K-$20K + distinct clusters → reason collected (confidence medium). Complexity Medium → reason collected (confidence medium).

**Result:** `{value: "prod-dev-split", confidence: "high", reasons: ["Your SOC2 compliance benefits from account-level isolation for audit clarity", "Your spend level ($5K-$20K/mo) and distinct prod/nonprod workloads warrant account separation", "Migration complexity (Medium) warrants separating production from development environments"]}`

### Example 3: FedRAMP + Large complexity

**Signals:** complexity = Large, compliance = fedramp, spend = $20K+, cluster_count = 4

**Evaluation:**

- Step 1 (Profile 3): First condition matches — complexity Large AND compliance includes fedramp

**Result:** `{value: "defer-multi-account", confidence: "high", reasons: ["FedRAMP compliance combined with Large migration complexity requires a dedicated platform team — deferring to specialist guidance"]}`

### Example 4: Missing signals

**Signals:** preferences.json readable but migration-preview.json missing, compliance = none, spend = <$1K

**Evaluation:**

- Treat complexity as unknown, fast_path as false
- Step 1 (Profile 3): Cannot match — complexity unknown (not "Large")
- Step 2 (Profile 2): No compliance, spend too low, no cluster data
- Step 3 (Profile 1): Reasons: "Low monthly spend (<$1K)", "No compliance requirements that demand account separation"

**Result:** `{value: "single-account", confidence: "high", reasons: [...]}`

---

## org_guardrails Schema (preferences.json)

The `org_guardrails` object is a **top-level key** in `preferences.json`, written during the Clarify phase and consumed by downstream Design and Generate phases to deterministically produce the correct artifacts.

### Complete Schema Definition

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

### Field Specifications

| Field                       | Type     | Valid Values                                                                              | Required | Default            |
| --------------------------- | -------- | ----------------------------------------------------------------------------------------- | -------- | ------------------ |
| `org_structure`             | string   | `"single-account"`, `"multi-account"`                                                     | Yes      | `"single-account"` |
| `guardrail_scps`            | string[] | Zero or more from: `"deny-leave-org"`, `"region-restrict"`, `"deny-root"` — no duplicates | Yes      | `[]`               |
| `chosen_by`                 | string   | `"user"`, `"default"`                                                                     | Yes      | `"default"`        |
| `recommendation`            | object   | See sub-fields below                                                                      | Yes      | —                  |
| `recommendation.value`      | string   | `"single-account"`, `"prod-dev-split"`, `"defer-multi-account"`                           | Yes      | —                  |
| `recommendation.confidence` | string   | `"high"`, `"medium"`, `"low"`                                                             | Yes      | —                  |
| `recommendation.reasons`    | string[] | One or more human-readable explanation strings                                            | Yes      | —                  |
| `user_override`             | boolean  | `true`, `false`                                                                           | Yes      | `true`             |

### Valid Value Enumerations

```
org_structure       ∈ {"single-account", "multi-account"}
guardrail_scps[]    ⊆ {"deny-leave-org", "region-restrict", "deny-root"}  (max 3, no duplicates)
chosen_by           ∈ {"user", "default"}
recommendation.value      ∈ {"single-account", "prod-dev-split", "defer-multi-account"}
recommendation.confidence ∈ {"high", "medium", "low"}
recommendation.reasons    : non-empty array of strings (≥1 entry)
user_override       ∈ {true, false}
```

### Invariants

The agent MUST enforce the following invariants at all times:

1. **Single-account → empty guardrail_scps**: When `org_structure == "single-account"`, the `guardrail_scps` array MUST be `[]`. If a conflicting state is detected (single-account with non-empty SCPs), clear `guardrail_scps` to `[]` and log a warning.

2. **Recommendation always present**: The `recommendation` object MUST always be present and fully populated (`value`, `confidence`, and `reasons`) — it is computed before Q7.5 is presented. If the engine cannot compute (missing signals), use the fallback: `{value: "single-account", confidence: "low", reasons: ["Insufficient signals available — defaulting to single account"]}`.

3. **Reasons non-empty**: `recommendation.reasons` MUST contain at least one entry. An empty reasons array is invalid.

4. **No invalid values**: Every field MUST contain a value from its defined valid set. No field may hold `null`, `undefined`, or a value outside the enumeration.

5. **No duplicate SCPs**: The `guardrail_scps` array MUST NOT contain duplicate entries.

6. **Multi-account SCP bounds**: When `org_structure == "multi-account"`, the `guardrail_scps` array contains 0–3 items drawn from the valid set.

7. **user_override semantics**: `user_override == false` ONLY when the user selected option A (accept recommendation). All other paths (option B, option C, skip, default) set `user_override = true`.

### Validation Rules (Enforced at Write Time)

Before writing `org_guardrails` to `preferences.json`, the agent MUST validate:

1. **Type checks**: `org_structure` is a string, `guardrail_scps` is an array of strings, `chosen_by` is a string, `recommendation` is an object with three fields, `user_override` is a boolean.

2. **Enum validation**: Each field value belongs to its defined valid set (see enumerations above).

3. **Invariant enforcement**:
   - If `org_structure == "single-account"` and `guardrail_scps` is non-empty → reject OR clear to `[]` with warning.
   - If `recommendation.reasons` is empty or missing → reject.
   - If any field is null/undefined/missing → reject.

4. **Duplicate check**: Verify `guardrail_scps` contains no duplicate entries.

5. **Structural completeness**: All five top-level fields (`org_structure`, `guardrail_scps`, `chosen_by`, `recommendation`, `user_override`) must be present. The `recommendation` object must contain all three sub-fields (`value`, `confidence`, `reasons`).

### Error Handling

| Scenario                                                              | Behavior                                                                                                                                     |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Any field contains a value outside its valid set                      | **Reject the write.** Surface an error naming the invalid field and its invalid value. Leave any prior `preferences.json` file unchanged.    |
| `org_structure` is "single-account" but `guardrail_scps` is non-empty | **Reject the write** (or auto-correct to `[]` with logged warning, then re-validate). Leave prior file unchanged if rejected.                |
| `recommendation` object is missing or incomplete                      | **Reject the write.** Surface error: "recommendation object must contain value, confidence, and reasons fields". Leave prior file unchanged. |
| `recommendation.reasons` is an empty array                            | **Reject the write.** Surface error: "recommendation.reasons must contain at least one entry". Leave prior file unchanged.                   |
| `guardrail_scps` contains duplicates                                  | **Reject the write.** Surface error: "guardrail_scps contains duplicate value: {value}". Leave prior file unchanged.                         |
| `guardrail_scps` contains a value not in the valid set                | **Reject the write.** Surface error: "guardrail_scps contains invalid value: {value}". Leave prior file unchanged.                           |
| Write to `preferences.json` fails for filesystem reasons              | Surface the filesystem error. Do not silently discard the data.                                                                              |

**Key principle:** On any validation failure, the prior `preferences.json` file MUST remain unchanged. The agent should surface a clear error message identifying which field failed and why, then allow the user to correct the input.

### Examples

#### Example 1: Single-Account Profile (Profile 1 — ~70% of startups)

```json
{
  "org_guardrails": {
    "org_structure": "single-account",
    "guardrail_scps": [],
    "chosen_by": "user",
    "recommendation": {
      "value": "single-account",
      "confidence": "high",
      "reasons": [
        "Simple migration complexity — single account is sufficient",
        "Low monthly spend ($1K-$5K) — multi-account overhead is not justified",
        "Fast-path eligible — straightforward migration suits single account"
      ]
    },
    "user_override": false
  }
}
```

#### Example 2: Multi-Account with SCPs (Profile 2 — prod/dev split)

```json
{
  "org_guardrails": {
    "org_structure": "multi-account",
    "guardrail_scps": ["deny-leave-org", "region-restrict", "deny-root"],
    "chosen_by": "user",
    "recommendation": {
      "value": "prod-dev-split",
      "confidence": "high",
      "reasons": [
        "Your SOC2 compliance benefits from account-level isolation for audit clarity",
        "Your spend level ($5K-$20K/mo) and distinct prod/nonprod workloads warrant account separation",
        "Migration complexity (Medium) further supports the isolation narrative"
      ]
    },
    "user_override": false
  }
}
```

#### Example 3: Defer Multi-Account (Profile 3 — education only, no Terraform)

```json
{
  "org_guardrails": {
    "org_structure": "single-account",
    "guardrail_scps": [],
    "chosen_by": "user",
    "recommendation": {
      "value": "defer-multi-account",
      "confidence": "high",
      "reasons": [
        "FedRAMP compliance combined with Large migration complexity requires a dedicated platform team — deferring to specialist guidance"
      ]
    },
    "user_override": false
  }
}
```

Note: Profile 3 maps `org_structure` to `"single-account"` because no Terraform organization resources are generated. The distinction is preserved in `recommendation.value` so the Generate phase produces the education-only report section instead of organization Terraform.

#### Example 4: User Overrides Recommendation (chose multi-account when single-account was recommended)

```json
{
  "org_guardrails": {
    "org_structure": "multi-account",
    "guardrail_scps": ["deny-leave-org"],
    "chosen_by": "user",
    "recommendation": {
      "value": "single-account",
      "confidence": "high",
      "reasons": [
        "Simple migration complexity — single account is sufficient",
        "No compliance requirements that demand account separation"
      ]
    },
    "user_override": true
  }
}
```

#### Example 5: Default Applied (user skipped question or fast-path)

```json
{
  "org_guardrails": {
    "org_structure": "single-account",
    "guardrail_scps": [],
    "chosen_by": "default",
    "recommendation": {
      "value": "single-account",
      "confidence": "low",
      "reasons": [
        "Insufficient signals available — defaulting to single account"
      ]
    },
    "user_override": true
  }
}
```
