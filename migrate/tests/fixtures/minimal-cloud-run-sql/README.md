# Fixture: minimal-cloud-run-sql

A minimal GCP Terraform project with 5 resources (2 PRIMARY, 3 SECONDARY) that exercises the infrastructure route through all 5 core phases.

## Resources

| Resource                                         | Classification            | Rationale                                            |
| ------------------------------------------------ | ------------------------- | ---------------------------------------------------- |
| `google_cloud_run_v2_service.api`                | PRIMARY (compute)         | Tests fast-path mapping to Fargate                   |
| `google_sql_database_instance.db`                | PRIMARY (database)        | Tests fast-path mapping to Aurora PostgreSQL         |
| `google_service_account.api_sa`                  | SECONDARY (identity)      | Tests identity classification and cluster attachment |
| `google_secret_manager_secret.db_url`            | SECONDARY (configuration) | Tests secret mapping to Secrets Manager              |
| `google_secret_manager_secret_version.db_url_v1` | SECONDARY (configuration) | Tests version resource grouping                      |

## Pre-seeded Files

- `.migration/0101-0000/.phase-status.json` — Initial phase status with fixed migration ID
- `.migration/0101-0000/preferences.json` — Pre-seeded preferences to bypass Clarify interactive prompts

## Behaviors Exercised

- Terraform discovery and resource classification (simplified path, <= 8 primaries)
- PRIMARY/SECONDARY classification per `classification-rules.md`
- Cluster formation per `clustering-algorithm.md`
- Dependency depth calculation per `depth-calculation.md`
- Fast-path deterministic mapping (Cloud Run -> Fargate, Cloud SQL -> Aurora PostgreSQL)
- Infrastructure design with rubric
- Cost estimation with pricing cache
- Terraform generation
- Migration script generation
- No AI path (no AI imports detected)
- No BigQuery specialist gate (no BigQuery resources)

## Usage

```bash
# Run migration skill in Claude Code from this directory
# Trigger: "migrate from GCP to AWS"
# Then run eval skill: "evaluate migration results"
```
