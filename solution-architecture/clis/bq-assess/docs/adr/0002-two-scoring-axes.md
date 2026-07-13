# Two independent scoring axes, not one complexity score

The assessment scores every entity on **two orthogonal axes** — **Migration Effort** (how
hard to _move_ data into Iceberg) and **Query Complexity** (how hard to keep the existing
query workload _running_ on Redshift over Iceberg) — instead of the original single
AUTO/REVIEW/MANUAL score. We did this because the Iceberg pivot (ADR-0001) decoupled the
two concerns: a flat table fed by an `UNNEST`-heavy view is now _trivial to move_ but
_hard to keep queryable_. Collapsing those into one number hides exactly the signal a
migration team needs. The axes use distinct label vocabularies (Effort: AUTO/ASSISTED/
MANUAL; Query: PORTABLE/ADAPT/REWRITE) so "AUTO" can't be mistaken for "PORTABLE".

## Consequences

- The JSON and HTML are split into two interfaces; a table appears on both, a view/UDF
  only on Query Complexity (see ADR-0004).
- Query Complexity depends on capturing view/UDF SQL — a new scanner responsibility.
- The old single-score scorer and its 24-property spec content are rewritten (the
  property-based _form_ is kept).
- Nesting (STRUCT depth, array-of-struct), formerly the two largest score drivers, drops
  to ~0 on Effort and moves to Query Complexity as a query-ergonomics hint.
