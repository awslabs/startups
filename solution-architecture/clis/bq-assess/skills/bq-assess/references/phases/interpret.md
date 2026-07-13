# Interpret Phase

## Entry Assertions

The Scan (or Demo) phase has completed successfully. All of the following are true:

- `landing_json` is set and points to a valid, non-empty `assessment-landing-*.json` file (holds `summary` + `cost`).
- `effort_json` (`assessment-effort-*.json`) and `query_json` (`assessment-query-*.json`) are set if present — they hold per-entity `entities[]`.
- The JSON files were produced by the `bq-assess` CLI during the Scan phase.
- If the user says "stop" or "cancel" at any point during this phase, exit the skill immediately without producing further output.

## Step 1: Read the JSON Reports

The report is split across **three mirrored files** — read each with the Read tool:

- **`landing_json`** → parse `summary` and `cost`. Required. If it cannot be read or is not valid JSON, tell the user: "The assessment summary could not be read. The file may be corrupted or incomplete." Offer to re-run the Scan phase.
- **`effort_json`** → parse `entities[]` (each carries `effort`, `conversion`, `load_sync_dml`). Tables only.
- **`query_json`** → parse `entities[]` (each carries `complexity`, `rewrite_guidance`). All entities with SQL surface.

To build a per-entity view, **merge effort and query entities by `full_name`** — an entity's Migration Effort comes from `effort_json`, its Query Complexity from `query_json`. If `effort_json` or `query_json` is missing, present the headline (Step 3) from `landing_json` and note that per-entity detail for the missing axis is unavailable.

## Step 2: Extract Key Metrics

Extract the following fields from **`landing_json`** (`summary.*` and `cost.*`). Use **exactly** these paths — do not guess or infer values from other fields:

| Metric                 | JSON path                            | Description                         |
| ---------------------- | ------------------------------------ | ----------------------------------- |
| Total entities         | `summary.total_entities`             | Number of BigQuery entities scanned |
| Total tables           | `summary.total_tables`               | Tables (vs views/routines)          |
| Total data size        | `summary.total_size_gb`              | Combined size in GB                 |
| Effort: AUTO           | `summary.effort_counts.AUTO`         | Tables migrated automatically       |
| Effort: ASSISTED       | `summary.effort_counts.ASSISTED`     | Tables needing sign-off             |
| Effort: MANUAL         | `summary.effort_counts.MANUAL`       | Tables needing manual design        |
| Complexity: PORTABLE   | `summary.complexity_counts.PORTABLE` | Queries running as-is               |
| Complexity: ADAPT      | `summary.complexity_counts.ADAPT`    | Queries needing minor adaptation    |
| Complexity: REWRITE    | `summary.complexity_counts.REWRITE`  | Queries needing full rewrite        |
| SQL surface confidence | `summary.sql_surface_confidence`     | HIGH/MEDIUM/LOW                     |
| BQ monthly cost        | `cost.bigquery_monthly`              | Current BigQuery run-rate           |
| AWS monthly (low)      | `cost.aws_monthly_low`               | Estimated AWS cost (low end)        |
| AWS monthly (high)     | `cost.aws_monthly_high`              | Estimated AWS cost (high end)       |
| Monthly savings (low)  | `cost.monthly_delta_low`             | Savings delta (low end)             |
| Monthly savings (high) | `cost.monthly_delta_high`            | Savings delta (high end)            |
| Annual savings (low)   | `cost.annual_savings_low`            | Annual projection (low)             |
| Annual savings (high)  | `cost.annual_savings_high`           | Annual projection (high)            |
| Breakeven (low)        | `cost.breakeven_months_low`          | Months to recoup (low)              |
| Breakeven (high)       | `cost.breakeven_months_high`         | Months to recoup (high)             |
| Compute confidence     | `cost.compute_confidence`            | HIGH/MEDIUM/LOW                     |

If any field is missing from the JSON, note it as "not available in this report" when presenting the summary. Do **NOT** estimate or fill in missing values.

## Step 3: Present Summary

Present a plain-English summary to the user covering the extracted metrics. Structure it as follows:

1. **Scope:** "Assessed {total_entities} entities ({total_tables} tables) totaling {total_size_gb} GB in project {project_id}."
2. **Migration Effort:** "{AUTO} tables auto-migrate, {ASSISTED} need sign-off, {MANUAL} need manual design."
3. **Query Complexity:** "{PORTABLE} portable, {ADAPT} need adaptation, {REWRITE} need full rewrite."
4. **Cost:** "Monthly savings: ${monthly_delta_low}–${monthly_delta_high}. Annual: ${annual_savings_low}–${annual_savings_high}." Add the caveat: "These are directional estimates based on current usage patterns, not a pricing commitment."
5. **Confidence:** "SQL surface: {sql_surface_confidence}. Compute: {compute_confidence}."

Every number and label in this summary **must** come directly from the JSON fields extracted in Step 2.

## Step 4: High-Effort Entities

Identify the entities that require the most migration effort:

1. Build the merged entity set by joining `effort_json.entities[]` and `query_json.entities[]` on `full_name` (effort fields from the effort file, complexity fields from the query file).
2. Filter to entries where `effort.category` equals `"MANUAL"` OR `complexity.category` equals `"REWRITE"`.
3. Sort by `effort.score + complexity.score` (combined) in **descending** order.
4. Take the **top 5** results (or fewer if less than 5 exist).

For each entity, present:

- **Entity name** — from `full_name`
- **Entity type** — from `entity_type` (TABLE, VIEW, MATERIALIZED_VIEW, ROUTINE)
- **Effort** — `effort.category` (score: `effort.score`) with flags from `effort.flags[]`
- **Complexity** — `complexity.category` (score: `complexity.score`) with flags from `complexity.flags[]`

Plain-language explanations for common flags:

- `JS_UDF` — "Uses JavaScript UDF that has no Redshift equivalent — requires full rewrite"
- `UNNEST` — "Uses UNNEST/array unnesting that needs Redshift SUPER type handling"
- `ARRAY_FUNCTIONS` — "Uses ARRAY_* functions that differ between BigQuery and Redshift"
- `STRUCT_NAVIGATION` — "Uses struct-path navigation (dot notation) that maps to SUPER extraction"
- `FUNCTION_DRIFT` — "Uses function names that exist in both dialects but behave differently"
- `partition_decision_required` — "Partition scheme needs human design for Iceberg"
- `sort_decision_required` — "Sort order needs human design for Iceberg"
- `lossy_cast` — "Type mapping loses precision (e.g., NUMERIC → DECIMAL)"

If the user asks follow-up questions about scoring, load `references/scoring-rules.md` for the full factor-to-point-value mapping.

If no entities match, say: "No entities scored as MANUAL effort or REWRITE complexity — all entities are low-effort and portable."

## Step 5: Top Tables by Size

Identify the largest tables regardless of effort/complexity:

1. Sort `effort_json.entities[]` (tables) by size (use `size_gb`, or `num_bytes` if present) in **descending** order.
2. Take the **top 3** results.

For each table, present:

- **Table name** — from `full_name`
- **Size** — formatted in GB
- **Effort category** — from `effort.category`
- **Complexity category** — from `complexity.category`

Add context: "These are the largest tables by data volume. They drive customer attention during migration planning because data transfer time and storage costs scale with size."

## Step 6: LOW Confidence Callout

Check the `summary.sql_surface_confidence` and `cost.compute_confidence` fields.

**If `sql_surface_confidence` is `LOW`:**

> ⚠️ **LOW SQL Confidence:** This assessment ran **without query logs or view definitions**. Complexity scoring is based on metadata heuristics only.
>
> For higher-confidence complexity scoring, re-run with query logs:
>
> ```
> bq-assess --gcp-project {project_id} --use-adc --format json,html --output reports/
> ```

**If `compute_confidence` is `LOW`:**

> ⚠️ **LOW Compute Confidence:** The cost comparison uses default assumptions for compute sizing. Provide a `--reservation-config` file with actual slot usage for higher-confidence estimates.

## Step 7: HTML Report Path

The HTML report is generated alongside the JSON report in the same output directory. The output includes multiple HTML files (landing page, effort detail, query detail).

Derive the HTML directory from `landing_json` by looking at the same output directory.

Tell the user:

> "The full HTML report is available in the same output directory. Open the landing page in a browser to see the visual effort/complexity breakdown, per-entity details, and cost comparison."

---

> **🔒 GROUNDING RULE — Do Not Fabricate**
>
> Every number, entity name, flag, cost estimate, and confidence level in this summary **MUST** come directly from the JSON assessment reports (`landing_json` / `effort_json` / `query_json`). Do **NOT**:
>
> - Fabricate or invent entity names, scores, or flags
> - Estimate values that are not present in the report
> - Infer recommendations beyond what the JSON contains
> - Round or adjust numbers unless explicitly formatting for display
>
> If a field is missing from the JSON, say **"not available in this report"** rather than guessing. The user is presenting these numbers to a customer — accuracy is non-negotiable.

---

## Cancellation

If the user says "stop" or "cancel" at any point during this phase — while reading the report, during the summary, or after presenting findings — exit the skill immediately. Do not produce further output.

## Exit Conditions

The Interpret phase is complete when:

1. The plain-English summary has been presented (Step 3).
2. High-effort entities have been shown, or noted as absent (Step 4).
3. Top tables by size have been shown (Step 5).
4. The LOW confidence callout has been shown if applicable (Step 6).
5. The HTML report path has been provided (Step 7).

This is the **terminal phase**. The skill is complete after the summary has been presented. No further phases follow.
