# Fixture: minimal-single-dataset

## Purpose

This fixture represents a small BigQuery warehouse with a single dataset containing approximately 10 tables. It exercises the happy-path flow through all four skill phases.

## Expected Phase Flow

1. **Preflight** — All environment checks pass (`bq-assess` installed, `gcloud` installed, ADC present). The SA provides `gcp_project: my-project` and `datasets: sample_dataset`.
2. **Scan** — The CLI executes with `--use-adc --format json,html --output reports/` and exits 0. A JSON report is written to `reports/assessment-*.json`.
3. **Interpret** — The skill reads the JSON report and produces a summary with a mix of AUTO, REVIEW, and MANUAL complexity categories. It highlights the top MANUAL tables by score and the top tables by size, then points the user to the generated HTML report. Because `query_logs_provided` is `false`, the skill calls out LOW confidence and suggests a follow-up run with `--include-query-logs`.

## Reference Dataset

- **GCP Project:** `my-project`
- **Dataset:** `sample_dataset`
- **Table count:** ~10 tables (mix of simple flat tables and complex nested/partitioned tables)

## Expected Outputs

- `reference-report.json` exists and is valid JSON matching the `AssessmentReport` schema
- An HTML report would also be generated in a real run (not included in this fixture)
- The Interpret phase summary includes all required fields:
  - Total tables assessed
  - Total data size (GB)
  - AUTO / REVIEW / MANUAL counts
  - Deployment recommendation (Serverless vs Provisioned)
  - Optimization confidence level
  - Estimated annual savings
  - Top MANUAL tables with complexity flag explanations
  - Top tables by data size

## Usage

This fixture provides a static `reference-report.json` that can be fed directly to the Interpret phase logic for testing, without running the actual CLI against BigQuery.
