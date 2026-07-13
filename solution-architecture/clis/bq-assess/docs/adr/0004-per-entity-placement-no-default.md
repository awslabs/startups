# Views/MVs/UDFs are first-class entities; placement is recommended per-entity

Views, materialized views, and UDFs are assessed as a **distinct entity type** from tables
— scored only on Query Complexity (they are SQL behavior, rebuilt in the engine layer, not
data that moves), with zero Migration Effort. **UDFs always land in Redshift** (Iceberg has
no function concept; BigQuery JavaScript UDFs have no Redshift equivalent and are the
hardest rewrite). For **views/MVs, the tool recommends a home per entity** — Redshift-local
vs Iceberg-catalog object — from signals like multi-engine consumption and refresh needs,
rather than applying a blanket default.

We chose per-entity recommendation because a view consumed only by a Redshift dashboard and
one consumed by Athena+Spark+Redshift genuinely want different homes; a blanket default
would be wrong for half of them. We rejected keeping everything table-keyed because it
causes attribution collisions (which of a 5-table view's tables "owns" its complexity?) and
produces nonsensical `CREATE TABLE` DDL for views.

## Consequences

- The JSON schema carries an `entity_type`; the two interfaces list different populations
  (Effort = tables; Query Complexity = tables + views + MVs + UDFs).
- The scanner must read `table_type`, `view_query`, `mview_query`, and routines — today it
  treats views as tables and would emit rows=0 `CREATE TABLE` DDL for them.
- Iceberg materialized-view _refresh_ mechanics are unverified and must be confirmed before
  appearing in migration instructions.
