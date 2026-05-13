# Fixture: bigquery-specialist-gate

Tests the BigQuery specialist gate — the rule that `google_bigquery_*` resources must never be mapped to a specific AWS analytics service. Instead they map to "Deferred — specialist engagement" and are excluded from numeric cost totals.

## Resources

| Type                                     | Classification | Purpose                                           |
| ---------------------------------------- | -------------- | ------------------------------------------------- |
| `google_bigquery_dataset.analytics`      | PRIMARY        | BigQuery dataset — triggers specialist gate       |
| `google_bigquery_table.events`           | SECONDARY      | Partitioned table                                 |
| `google_bigquery_table.aggregates`       | SECONDARY      | View                                              |
| `google_cloud_run_v2_service.ingest_api` | PRIMARY        | Non-BigQuery resource — should get normal mapping |
| `google_service_account.ingest_sa`       | SECONDARY      | Service account                                   |

## Key invariants tested

- H25: BigQuery maps to "Deferred — specialist engagement"
- H36: BigQuery excluded from numeric cost totals
- Clarify surfaces specialist advisory before Design
- Design does NOT recommend Redshift, Athena, Glue, or EMR
