# bq-assess — BigQuery → AWS Lakehouse Migration Assessment

A read-only tool that profiles an existing BigQuery warehouse and produces a migration
assessment: a cost comparison against AWS and DDL/DML migration instructions for moving
to an open lakehouse on AWS. It assesses; it does not execute the migration.

## Language

**Source**:
The existing BigQuery warehouse being assessed. The tool reads only its metadata
(and optionally its query logs) — never its data rows.
_Avoid_: origin, legacy, source-of-truth

**Storage Target**:
Amazon S3 Tables — managed Apache Iceberg tables — where migrated data will live.
The destination that schema conversion (DDL) targets. Iceberg natively supports
nested types (struct/list/map), so nesting is not a storage obstacle.
_Avoid_: destination, sink, "the Redshift tables" (Redshift is the engine, not the store)

**Query Engine**:
Amazon Redshift Serverless — the decoupled compute that queries and writes the
Storage Target. Sized by compute (RPU), independent of stored data volume. This
project targets Serverless only; provisioned Redshift is out of scope.
_Avoid_: cluster, warehouse, database, "Redshift" unqualified

**Assessment**:
The tool's output for a Source: a [[cost-comparison]] and per-entity [[migration-instructions]]
scored on two independent axes ([[migration-effort]] and [[query-complexity]]). Delivered
as three paired HTML+JSON artifacts sharing one design language:

- **Landing** — executive entry point: cost-comparison hero + headline counts, links onward.
- **Migration Effort** — [[table]]s ranked by move-effort.
- **Query Complexity** — [[table]]s + [[view-/-materialized-view-/-udf]]s ranked by rewrite effort.
  JSON is split to mirror the three HTML files (one source per file, cross-referenced by
  entity name); no CSV. HTML must be professional-grade (built via the `frontend-design` skill).
  _Avoid_: report (that names the file, not the content), scan (that names one input step)

**Migration Instructions**:
The per-table guidance the tool emits, in three layers. Guidance for a human or a
later phase to run — the tool itself never writes to the Storage Target.
_Avoid_: migration script, ETL job, pipeline

- **DDL** — Iceberg `CREATE TABLE` for the Storage Target. Always emitted (metadata only).
- **Load/Sync DML** — Redshift SQL that loads BigQuery data into the Storage Target
  (initial load) and keeps it current (ongoing upsert via `MERGE` on Iceberg).
  Always emitted (metadata only). _Avoid_: ETL, COPY job.
- **Query-Rewrite Guidance** — flags BigQuery-specific constructs in the [[query-workload]]
  that won't run on the Query Engine and estimates rewrite effort. Only emitted when
  query logs or view SQL are provided (the high-confidence upgrade).

**Query Workload**:
The set of `SELECT`/view/transform SQL the Source actually runs, observed via query
logs or view definitions. Distinct from [[migration-instructions]] Load/Sync DML —
this is the customer's existing read workload, the input to Query-Rewrite Guidance.
_Avoid_: queries (ambiguous), DML (that's the load/sync SQL we emit)

## Entities

The [[assessment]] distinguishes two entity populations by what migrating them means:
data that **moves** vs. SQL behavior that gets **rebuilt**. Tables appear in both
interfaces; views/MVs/UDFs appear only in the [[query-complexity]] one.

**Table**:
A base table — state at rest. Moves into the Storage Target (Iceberg). The only entity
with [[migration-effort]]. Also carries [[query-complexity]] when queried directly.
_Avoid_: relation, dataset (that's the BQ container)

**View / Materialized View / UDF**:
SQL _behavior_, not state — rebuilt in the engine layer, never "moved." Zero
[[migration-effort]] (nothing physical to relocate); scored only on [[query-complexity]].
Each links to the [[table]]s it depends on.

- **UDFs always land in the Query Engine** — Iceberg has no function concept. BigQuery
  **JavaScript** UDFs are the hardest case (no Redshift equivalent → Python/Lambda UDF
  rewrite); SQL UDFs port more directly.
- **Views/MVs have a [[placement]] choice** — Redshift-local or Iceberg-catalog object.

**Placement**:
The per-entity recommended home for a view/MV: **Redshift** (full dialect, simplest,
auto-refresh; engine-local) or **Iceberg catalog** (open, multi-engine queryable; stays
in the lakehouse). Recommended per entity from signals (multi-engine consumption, refresh
needs) — never a blanket default. Iceberg-MV _refresh_ mechanics are unverified and must
be confirmed before appearing in [[migration-instructions]].
_Avoid_: location, target (overloaded with Storage Target)

## Cost

**Cost Comparison**:
The Source's current BigQuery run-rate vs the projected AWS run-rate (Storage Target +
Query Engine). Headline metric is the **monthly run-rate delta**; annual savings and
break-even are supporting detail (break-even depends on one-time migration cost, which
derives from [[migration-effort]], not a flat per-table fee). Always shown; compute side
degrades by confidence — no [[query-workload]] data → LOW, shown as an estimated _range_,
clearly labelled an estimate, never a false point value.
_Avoid_: TCO, savings (name the specific metric), ROI

**BQ Pricing Model**:
Which way the Source is billed — must be detected, not assumed. **On-demand** bills
bytes scanned ($/TB); **Capacity (Editions)** bills [[slot-time]] via reservations
(baseline/max/commitments). The current code assumes on-demand only; a capacity-billed
Source needs slot-based costing or its baseline is fiction.
_Avoid_: flat-rate, pricing tier

**Slot Time**:
BigQuery compute consumed, measured in slot-ms (`total_slot_ms` per job in
`INFORMATION_SCHEMA.JOBS`). The utilization curve (avg / P50 / P99 / peak / idle
fraction) is the bridge to Query Engine RPU-hours — both meter compute-time, so workload
_shape_ maps across directly. Auto-captured with the existing `jobs.listAll` permission.
Reservation _config_ (edition rate, commitment discounts) often needs manual entry from
the customer's slot estimator or bill — the top confidence rung.
_Avoid_: slots (ambiguous: capacity vs consumption), CPU

## Scoring Axes

The [[assessment]] scores every table on two independent axes. A table can be low on
one and high on the other; they are never combined into a single number.

**Migration Effort**:
How hard it is to _move_ a table into the Storage Target. Measures data-movement
reality, not schema shape (Iceberg stores nesting/partitioning natively). Driven by:
data volume tiers (load mechanics), [[lossy-cast]] count, ongoing-sync need (`MERGE`
vs one-shot load), and _non-clean_ partition/sort mappings. Clean time-partition and
sort-order mappings are zero-effort annotations the tool derives for you; ingestion-time,
range, and multi-column mappings are scored effort + flagged for review. Always scored.
Surfaced in its own HTML interface. Categories: **AUTO** (tool's load/sync DML moves it,
no human) / **ASSISTED** (moves it, but a flagged decision needs sign-off) / **MANUAL**
(human designs the load).
_Avoid_: complexity (reserved for the other axis), difficulty; REVIEW (that's the old
single-axis label)

**Lossy Cast**:
A BigQuery type with no clean Iceberg equivalent, requiring a human-reviewed casting
decision: `GEOGRAPHY`, `INTERVAL`, `TIME`, and `BIGNUMERIC` beyond Iceberg decimal
precision. A first-class scored [[migration-effort]] factor surfaced with a visible
"lossy cast — review" flag — never a silent fallback.
_Avoid_: unknown type, unmapped type, fallback

**Query Complexity**:
How hard it is to keep the existing [[query-workload]] _running_ on the Query Engine
over the Storage Target after migration. Driven by BigQuery-specific SQL constructs
(`UNNEST`, function drift, `ARRAY_*`, struct navigation, UDFs, complex views). Surfaced
in its own HTML interface. Always scored, never fails when logs are absent; degrades by
confidence over the [[sql-surface]]:

- No views/UDFs/logs → LOW ("no read workload visible").
- Views + persistent UDFs auto-captured → MEDIUM (the defined SQL surface).
-
  - Query logs → HIGH (actual observed workload, weighted by run frequency).
    Categories: **PORTABLE** (runs on the Query Engine as-is) / **ADAPT** (minor dialect
    adaptation) / **REWRITE** (full manual rewrite — JS UDFs, `UNNEST`-heavy views).
    _Avoid_: rewrite score, portability score; AUTO/REVIEW/MANUAL (those are the Effort axis)

**SQL Surface**:
Every piece of Source SQL the [[query-complexity]] axis scores. Captured automatically
within the existing read-only `metadataViewer` role (definitions are metadata, not data):
view SQL (`view_query`), materialized-view SQL (`mview_query`), and persistent UDFs /
stored procedures (`list_routines` → `body`/`language`/`arguments`). Inline UDFs
(`CREATE TEMP FUNCTION` in a query body) are the one part NOT auto-captured — they appear
only when query logs are provided. No user-supplied SQL is required.
_Avoid_: DDL (that's the table schema), source code
