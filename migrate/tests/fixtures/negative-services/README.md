# Fixture: negative-services

Tests that forbidden AWS service recommendations never appear in Design output.

## Resources

| Type                                   | Classification | Purpose                                                |
| -------------------------------------- | -------------- | ------------------------------------------------------ |
| `google_cloud_run_v2_service.api`      | PRIMARY        | Should map to Fargate, never Lightsail/Beanstalk       |
| `google_bigquery_dataset.warehouse`    | PRIMARY        | Should map to Deferred, never Redshift/Athena/Glue/EMR |
| `google_identity_platform_config.auth` | EXCLUDED       | Auth resource — should not appear in inventory at all  |
| `google_bigquery_table.users`          | SECONDARY      | BigQuery table                                         |
| `google_service_account.api_sa`        | SECONDARY      | Service account                                        |

## Key invariants tested

- Auth resources excluded from inventory entirely
- No Cognito in Design output
- No Lightsail, Elastic Beanstalk in Design output
- No Redshift, Athena, Glue, EMR for BigQuery resources
- BigQuery maps to "Deferred — specialist engagement"
