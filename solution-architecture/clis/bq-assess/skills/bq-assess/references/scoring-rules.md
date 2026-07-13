# Scoring Rules

> Source of truth: `src/bq_assess/scoring/effort.py` and `src/bq_assess/scoring/complexity.py`

## Two-Axis Model (ADR-0002)

Every entity is scored on two independent axes:

### Axis 1: Migration Effort (Tables only)

Scores the labor required to move data to S3 Tables (Iceberg).

| Factor              | Condition                                            | Points  |
| ------------------- | ---------------------------------------------------- | ------- |
| Data volume (large) | 1–100 GB                                             | +1      |
| Data volume (huge)  | >100 GB                                              | +2      |
| Lossy casts         | Per lossy type mapping                               | +1 each |
| Ongoing sync        | Ingestion-time partition or `updated_at`-like column | +1      |
| Partition decision  | `partition_decision_required` flag                   | +1      |
| Sort decision       | `sort_decision_required` flag                        | +1      |

**NOT scored:** nesting depth, clean partitioning, clean clustering.

| Score | Category     | Meaning                                 |
| ----- | ------------ | --------------------------------------- |
| 0     | **AUTO**     | Tool's DML moves it with no human input |
| 1–2   | **ASSISTED** | Flagged decisions need sign-off         |
| 3+    | **MANUAL**   | Human must design the load strategy     |

**Confidence:** HIGH when `num_bytes` is known, LOW when `num_bytes` is None.

### Axis 2: Query Complexity (all entities with SQL surface)

Scores the rewrite effort for BigQuery-specific SQL constructs.

| Factor                                      | Points  |
| ------------------------------------------- | ------- |
| JavaScript UDF invocation                   | +4      |
| UNNEST / array unnesting                    | +2      |
| ARRAY_* functions                           | +2      |
| Struct-path navigation                      | +1      |
| Function-name drift (per distinct function) | +1 each |
| Hub entity (≥3 dependents)                  | +1      |

| Score | Category     | Meaning                    |
| ----- | ------------ | -------------------------- |
| 0     | **PORTABLE** | Runs on Redshift as-is     |
| 1–3   | **ADAPT**    | Minor dialect adaptation   |
| 4+    | **REWRITE**  | Full manual rewrite needed |

**Confidence ladder:**

- **LOW:** No SQL surface and no logs
- **MEDIUM:** Auto-captured view/UDF definitions present
- **HIGH:** Query logs add observed workload

## Placement (Views/MVs/UDFs)

- UDF → always Redshift (Iceberg has no function concept)
- View/MV → signal-based (default: Redshift with LOW confidence)
- MV with Iceberg placement → `refresh_unverified=True`
