# BigQuery → S3 Tables + Redshift Serverless Migration Guide

Understanding the two-axis scoring model: Migration Effort (data movement) and Query Complexity (SQL rewrite).

---

## Overview

This tool uses a two-axis scoring model to capture different migration concerns:

- **Axis 1: Migration Effort** — How hard is it to move data to S3 Tables (Apache Iceberg)?
- **Axis 2: Query Complexity** — How hard is it to rewrite SQL for Redshift Serverless?

These axes are independent. A table can be AUTO effort (small, clean schema) but REWRITE complexity (queries use JavaScript UDFs). Both scores matter, for different reasons.

---

## Part 1: Migration Effort (Data Movement)

Scores difficulty of moving BigQuery data to S3 Tables (Iceberg). Categories: AUTO (0 points), ASSISTED (1-2 points), MANUAL (3+ points).

### Volume (0, +1, or +2 points)

**What it affects:**
Time and cost to extract and load data.

**Scoring:**

- 0-1 GB: 0 points (trivial)
- 1-100 GB: +1 point (manageable, but needs monitoring)
- 100+ GB: +2 points (multi-hour exports, risk of timeout)

**Example:**

```
clickstream_events: 2.5 TB → +2 points
user_profiles: 50 GB → +1 point
lookup_country_codes: 100 MB → 0 points
```

### Lossy Type Casts (+2 points each)

**What it is:**
BigQuery types that don't map cleanly to Iceberg/Redshift.

**Common cases:**

- `NUMERIC(38,9)` → Iceberg `decimal(18,2)` (precision loss)
- `BIGNUMERIC` → no Iceberg equivalent (must pick a narrower decimal)
- `GEOGRAPHY` → requires custom serialization (WKT/WKB)

**Example:**

```sql
-- BigQuery
CREATE TABLE financial_ledger (
  transaction_id STRING,
  amount NUMERIC(38, 9)  -- High precision for micro-transactions
)

-- Iceberg (lossy)
CREATE TABLE financial_ledger (
  transaction_id STRING,
  amount DECIMAL(18, 2)  -- Lost 7 digits of precision + scale reduced
)
-- Score: +2 (requires validation that precision loss is acceptable)
```

### Ongoing Sync Signals (+1 point)

**What it is:**
Indicators that the table receives continuous updates (not one-time load).

**Signals:**

- Ingestion-time partitioning (`_PARTITIONTIME`, `_PARTITIONDATE`)
- `updated_at`, `modified_at`, `last_synced_at` columns
- Streaming buffer presence (data arriving continuously)

**Why it matters:**
One-time migration is different from setting up ongoing CDC/replication.

**Example:**

```sql
-- BigQuery table with ongoing writes
CREATE TABLE user_events
PARTITION BY _PARTITIONDATE  -- New partitions added daily
```

Score: +1 (requires sync strategy, not just export-once)

### Partition/Sort Decision Required (+1 point)

**What it is:**
BigQuery partitioning or clustering that needs mapping to Iceberg partition transforms.

**Why it's not AUTO:**
Iceberg supports partitioning (day, month, year, bucket, truncate), but the choice affects query performance. Requires understanding query patterns.

**Example:**

```sql
-- BigQuery
CREATE TABLE orders
PARTITION BY DATE(order_timestamp)
CLUSTER BY customer_id
```

**Iceberg options:**

```sql
-- Option 1: Partition by day (matches BigQuery)
PARTITIONED BY (day(order_timestamp))

-- Option 2: Partition by month (less granular, fewer files)
PARTITIONED BY (month(order_timestamp))
```

Score: +1 (decision required based on query patterns)

### Migration Effort Categories

| Score | Category | Meaning                                                                                  |
| ----- | -------- | ---------------------------------------------------------------------------------------- |
| 0     | AUTO     | Small table, clean types, no sync needed. Export and load.                               |
| 1-2   | ASSISTED | Moderate volume OR ongoing sync OR partition decision. Mostly automated with validation. |
| 3+    | MANUAL   | Large volume + lossy casts + sync. Requires careful planning and monitoring.             |

---

## Part 2: Query Complexity (SQL Rewrite)

Scores difficulty of adapting BigQuery SQL to Redshift Serverless. Categories: PORTABLE (0 points), ADAPT (1-3 points), REWRITE (4+ points).

### JavaScript UDFs (+4 points)

**What it is:**
User-defined functions written in JavaScript.

**BigQuery example:**

```sql
CREATE TEMP FUNCTION parse_user_agent(ua STRING)
RETURNS STRUCT<browser STRING, os STRING>
LANGUAGE js AS '''
  const parsed = uaParser(ua);
  return {browser: parsed.browser, os: parsed.os};
''';

SELECT parse_user_agent(user_agent) FROM events;
```

**Redshift:**
No JavaScript UDF support. Must rewrite in Python UDF (slower, different runtime) or pre-process data.

**Why +4:**
High rewrite cost. JS UDFs often contain complex business logic that's hard to port.

### UNNEST / Array Unnesting (+2 points)

**What it is:**
Flattening arrays into rows.

**BigQuery example:**

```sql
SELECT order_id, item
FROM orders, UNNEST(items) AS item
```

**Redshift:**
Requires different syntax and performs worse:

```sql
SELECT order_id, item
FROM orders o, o.items AS item  -- Partiql syntax, slower on SUPER type
```

**Why +2:**
Syntax conversion required + potential performance degradation.

### ARRAY_* Functions (+2 points)

**What it is:**
BigQuery array manipulation functions.

**Examples:**

```sql
-- BigQuery
ARRAY_LENGTH(items)
ARRAY_AGG(product_id ORDER BY price DESC LIMIT 5)
ARRAY_CONCAT(tags1, tags2)

-- Redshift equivalents vary:
JSON_ARRAY_LENGTH(items)  -- Only for SUPER type
LISTAGG(product_id, ',') WITHIN GROUP (...)  -- Different aggregation
-- ARRAY_CONCAT: no direct equivalent
```

**Why +2:**
Function incompatibilities. Requires lookup + rewrite + testing.

### Struct-Path Navigation (+1 point)

**What it is:**
Accessing nested fields in STRUCTs.

**BigQuery example:**

```sql
SELECT user.profile.country, user.profile.tier
FROM events
```

**Redshift:**
Struct access exists but is less optimized:

```sql
SELECT user.profile.country::STRING, user.profile.tier::STRING
FROM events
-- Requires casting, slower than BigQuery's native columnar access
```

**Why +1:**
Syntax adjustment + potential performance check.

### Function-Name Drift (+1 point per distinct function)

**What it is:**
Functions with different names or argument order between BigQuery and Redshift.

**Examples:**

| BigQuery                            | Redshift                         | Issue                                     |
| ----------------------------------- | -------------------------------- | ----------------------------------------- |
| `DATE_DIFF(date1, date2, DAY)`      | `DATEDIFF(day, date2, date1)`    | Arguments reversed                        |
| `TIMESTAMP_ADD(ts, INTERVAL 1 DAY)` | `ts + INTERVAL '1 day'`          | Different syntax                          |
| `SAFE_CAST(x AS INT64)`             | `TRY_CAST(x AS INTEGER)`         | Different function name                   |
| `REGEXP_CONTAINS(str, pattern)`     | `REGEXP_INSTR(str, pattern) > 0` | Different function, different return type |

**Why +1 per function:**
Each requires manual find-and-replace + validation.

### Hub Entity Bonus (+1 point)

**What it is:**
Tables or views referenced by many other views (central in the dependency graph).

**Why it matters:**
Changes to hub entities propagate. A rewrite that breaks the hub schema impacts 10+ downstream views.

**Example:**

```
user_facts → referenced by 15 views
orders_enriched → referenced by 22 views
```

Score: +1 (extra caution required, high blast radius)

### Query Complexity Categories

| Score | Category | Meaning                                                                                     |
| ----- | -------- | ------------------------------------------------------------------------------------------- |
| 0     | PORTABLE | Standard SQL, minimal BigQuery-specific functions. Runs on Redshift with minor adjustments. |
| 1-3   | ADAPT    | Function drift, struct access, array functions. Requires targeted rewrites and testing.     |
| 4+    | REWRITE  | JavaScript UDFs, heavy UNNEST usage, complex array logic. Significant rewrite effort.       |

---

## Part 3: How the Two Axes Combine

The axes address different concerns:

- **Migration Effort** → "How hard is it to get the data into S3 Tables?"
- **Query Complexity** → "How hard is it to rewrite the queries that use this table?"

### Example Combinations

**1. AUTO Effort + PORTABLE Complexity**

```
lookup_country_codes: 500 rows, no casts, no partitioning
No views reference it
Score: AUTO (0) / PORTABLE (0)
```

Low-touch migration. Export and load, queries work as-is.

**2. AUTO Effort + REWRITE Complexity**

```
user_profiles: 10 GB, clean schema
Referenced by view user_segments that uses JS UDF for geohashing
Score: AUTO (0) / REWRITE (4)
```

Data migration is easy, but the view needs a major rewrite (port JS logic).

**3. MANUAL Effort + PORTABLE Complexity**

```
clickstream_events: 2 TB, NUMERIC(38,9) columns, ingestion-time partitioning
Queries are simple aggregations (COUNT, SUM)
Score: MANUAL (5) / PORTABLE (0)
```

Hard to move (volume + casts + sync), but queries are straightforward.

**4. ASSISTED Effort + ADAPT Complexity**

```
order_facts: 50 GB, partitioned by date
Referenced by 5 views using DATE_DIFF and UNNEST
Score: ASSISTED (2) / ADAPT (3)
```

Moderate effort both ways. Manageable with planning.

---

## Summary: Two-Axis Decision Matrix

| Migration Effort | Query Complexity | Action                                         |
| ---------------- | ---------------- | ---------------------------------------------- |
| AUTO             | PORTABLE         | Low-touch: export, load, deploy                |
| AUTO             | ADAPT/REWRITE    | Focus on SQL rewrite, data movement is trivial |
| ASSISTED/MANUAL  | PORTABLE         | Focus on data pipeline, queries are fine       |
| ASSISTED/MANUAL  | ADAPT/REWRITE    | Plan both: data movement + query rewrite       |

---

## The Core Principle

**BigQuery** optimizes for: Nested, denormalized, schema-flexible analytics with rich SQL functions.

**S3 Tables + Redshift Serverless** optimizes for: Open-format lakehouse storage (Iceberg) + ANSI-SQL compute with strong performance on flat/semi-structured data.

**Migration requires mapping BigQuery's strengths to the lakehouse model's trade-offs.**

The two-axis model makes those trade-offs explicit: you see both the data movement cost and the query rewrite cost, independently scored.
