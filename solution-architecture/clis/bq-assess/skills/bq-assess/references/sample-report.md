# Sample Assessment Report

> Annotated excerpt from a `bq-assess` JSON report (lakehouse target, two-axis model).
> Use this reference to explain report fields without re-running the CLI.
> Field names match what the Interpret phase reads — keep the two in sync.

## Output File Structure

A run with `--format json,html` writes **three mirrored JSON files** plus the HTML report:

| File                        | Top-level keys                                                               | Holds                                                      |
| --------------------------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `assessment-landing-*.json` | `assessment_id`, `generated_at`, `project_id`, `summary`, `cost`, `failures` | Headline summary + cost comparison                         |
| `assessment-effort-*.json`  | `assessment_id`, `entities[]`                                                | Per-**table** Migration Effort, Iceberg DDL, load/sync DML |
| `assessment-query-*.json`   | `assessment_id`, `entities[]`                                                | Per-entity Query Complexity + rewrite guidance             |

The Interpret phase reads `summary` and `cost` from the **landing** file, and per-entity detail from the **effort** / **query** files.

A raw metadata export is also written under `<output>/metadata/` (`tables.json`, `routines.json`, `jobs.jsonl`, `workload_summary.json`, `pricing_detection.json`) for verification.

---

## Landing File — Annotated

```jsonc
{
  "assessment_id": "assess-20260626-16ba999b",
  "generated_at": "2026-06-26T...+00:00",
  "project_id": "my-project",

  // ── SUMMARY ──────────────────────────────────────────────────
  "summary": {
    "total_entities": 13, // tables + views + MVs + routines scanned
    "total_tables": 10, // tables only (Migration Effort is tables-only)
    "total_size_gb": 0.0264, // combined data size

    // Axis 1 — Migration Effort (how hard the DATA is to move)
    "effort_counts": { "AUTO": 8, "ASSISTED": 2, "MANUAL": 0 },

    // Axis 2 — Query Complexity (how much the SQL must change)
    "complexity_counts": { "PORTABLE": 7, "ADAPT": 6, "REWRITE": 0 },

    "sql_surface_confidence": "HIGH" // HIGH/MEDIUM/LOW — drives the LOW-confidence callout
  },

  // ── COST ─────────────────────────────────────────────────────
  // AWS run-rate is a RANGE (low/high). Negative delta = AWS costs more
  // (common for tiny datasets). Recommendation picks the best-fit scenario.
  "cost": {
    "bq_pricing_model": "ON_DEMAND", // ON_DEMAND | CAPACITY (detected)
    "bigquery_monthly": 0.0151, // BQ run-rate (computed list-price unless overridden)
    "bigquery_breakdown": [/* storage + bytes-scanned lines */],
    "aws_lines": [/* lines of the recommended scenario */],
    "aws_monthly_low": 0.1151,
    "aws_monthly_high": 0.1151,
    "monthly_delta_low": -0.10, // bigquery_monthly - aws_monthly_high
    "monthly_delta_high": -0.10,
    "annual_savings_low": -1.20,
    "annual_savings_high": -1.20,
    "migration_onetime": 0.0, // from aggregate Migration Effort (not shown in HTML)
    "breakeven_months_low": 9999.0, // 9999 = "never recoups"
    "breakeven_months_high": 9999.0,
    "compute_confidence": "HIGH", // HIGH/MEDIUM/LOW for the compute line
    "aws_scenarios": [ // all six evaluated options
      {
        "label": "Redshift Serverless",
        "category": "SERVERLESS",
        "monthly_total": 0.1151,
        "confidence": "HIGH",
        "is_recommended": true,
        "lines": [/* S3 Tables storage + Serverless compute */]
      }
      // + Serverless Reserved 1yr/3yr, Provisioned RG On-Demand/1yr/3yr.
      // All scenarios share the userME S3 Tables storage basis (decoupled lakehouse).
    ],
    "recommendation": {
      "recommended_scenario": "Redshift Serverless",
      "reasoning": "Serverless at $0.12/month beats Provisioned 1yr RI ...",
      "alternatives_considered": [/* other scenario labels */]
    }
  },

  "failures": [] // entities that failed to process (empty when all succeed)
}
```

---

## Entity (effort / query files) — Annotated

```jsonc
{
  "full_name": "sample_dataset.analytics_summary",
  "entity_type": "TABLE", // TABLE | VIEW | MATERIALIZED_VIEW | ROUTINE
  "population": "TABLE", // TABLE (migrate data) | REBUILT (views/MVs/UDFs)
  "rows": 10000,
  "size_gb": 0.0047,
  "depends_on": [],

  // Axis 1 — Migration Effort (tables only)
  "effort": {
    "category": "AUTO", // AUTO | ASSISTED | MANUAL
    "score": 0,
    "flags": [], // e.g. lossy_casts, partition_decision_required, ongoing_sync
    "reasoning": "No effort factors detected — fully automatable.",
    "confidence": "HIGH"
  },

  // Iceberg conversion (NOT Redshift-native DDL — no DISTKEY/SORTKEY)
  "conversion": {
    "ddl": "CREATE TABLE ... PARTITION BY (day(summary_date)) SORT BY (region);",
    "partition_mapping": {
      "iceberg_transforms": ["day(summary_date)"],
      "sort_order": ["region"],
      "auto_derived": true,
      "decision_flags": []
    },
    "lossy_casts": [], // never silent — each lossy type is recorded
    "warnings": [],
    "success": true
  },
  "load_sync_dml": "INSERT INTO ...", // load/sync SQL (null for REBUILT entities)

  // Axis 2 — Query Complexity (any entity with SQL surface)
  "complexity": {
    "category": "PORTABLE", // PORTABLE | ADAPT | REWRITE
    "score": 0,
    "constructs": [], // detected BQ-specific constructs (UNNEST, JS_UDF, ...)
    "flags": [],
    "reasoning": "...",
    "confidence": "HIGH"
  },
  "rewrite_guidance": [/* per-construct, human-readable change notes */]
}
```

---

## How the Interpret Phase Uses Each Field

| Field                                                            | Source file  | Interpret usage                     |
| ---------------------------------------------------------------- | ------------ | ----------------------------------- |
| `summary.total_entities` / `total_tables` / `total_size_gb`      | landing      | Scope headline                      |
| `summary.effort_counts.{AUTO,ASSISTED,MANUAL}`                   | landing      | Migration Effort breakdown          |
| `summary.complexity_counts.{PORTABLE,ADAPT,REWRITE}`             | landing      | Query Complexity breakdown          |
| `summary.sql_surface_confidence`                                 | landing      | LOW-confidence callout              |
| `cost.bigquery_monthly` / `aws_monthly_low` / `aws_monthly_high` | landing      | Cost comparison                     |
| `cost.monthly_delta_*` / `annual_savings_*`                      | landing      | Business-case framing (directional) |
| `cost.compute_confidence`                                        | landing      | Qualifies the AWS compute estimate  |
| `cost.recommendation.recommended_scenario` / `reasoning`         | landing      | Recommended engine + why            |
| `entities[].full_name` / `entity_type`                           | effort/query | Identifies entities in top lists    |
| `entities[].effort.{category,score,flags}`                       | effort       | MANUAL filtering + sizing           |
| `entities[].complexity.{category,score,flags}`                   | query        | REWRITE filtering + rewrite notes   |
| `entities[].conversion.ddl`                                      | effort       | Generated Iceberg DDL               |

> **Grounding:** every value presented to a customer must come directly from these JSON fields — never estimated or inferred.
