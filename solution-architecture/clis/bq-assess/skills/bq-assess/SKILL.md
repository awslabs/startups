---
name: bq-assess
description: "Assess BigQuery warehouses for migration to AWS.
  Triggers on: assess BigQuery migration, BigQuery to Redshift,
  BigQuery to AWS lakehouse, estimate migration complexity from BigQuery,
  analyze BigQuery warehouse for migration, migrate BQ to Redshift.
  Runs a 3-phase process: preflight environment check, scan via
  the bq-assess CLI, interpret the JSON assessment report and point
  the user to the generated HTML report.
  Do not use for: general BigQuery query tuning, Redshift administration,
  AWS-to-GCP reverse migrations, non-GCP warehouse assessments, Phase 2
  migration execution (data load DML or Iceberg DDL deployment)."
---

# bq-assess Skill

## Philosophy

- **Read-only.** No AWS commitment required. The assessment scans metadata and query logs; it does not provision resources or modify the BigQuery project.
- **Directional cost numbers.** Savings estimates are conversation starters, not authoritative quotes. Always present them as approximate.
- **Query logs are optional.** When logs are unavailable, confidence drops to LOW. Surface this explicitly — never hide the gap.
- **Defer architectural redesign.** Schema changes, Iceberg partition/sort-order decisions, and migration execution belong to the user and the AWS account team, not this skill.

## Definitions

- **"Load"** = read the file with the Read tool and follow its instructions.
- **`$REPORTS_DIR`** = output directory for CLI run (default `reports/`).

## Prerequisites

Before running, the user must have:

- `bq-assess` on PATH (or be willing to install it)
- `gcloud` on PATH with ADC configured (`gcloud auth application-default login`)

## State Machine

After every phase completion, consult this table to determine the next action. Each row maps to loading exactly one phase file.

| Current state | Condition to leave                              | Next state     | Phase file to load                                       |
| ------------- | ----------------------------------------------- | -------------- | -------------------------------------------------------- |
| `preflight`   | Env checks pass AND `gcp_project` collected     | `scan`         | Load `references/phases/scan.md`                         |
| `scan`        | CLI exits 0 AND landing JSON report exists      | `interpret`    | Load `references/phases/interpret.md`                    |
| `scan`        | CLI exits non-zero                              | stay in `scan` | Follow Error Routing below                               |
| `interpret`   | Summary presented AND HTML report path surfaced | terminal       | Skill complete                                           |
| **any**       | **User says "stop" or "cancel"**                | **terminal**   | **Exit immediately. Do not run the CLI or write files.** |

**Entry points:**

- **Any trigger phrase** → load `references/phases/preflight.md` to begin the `preflight` phase.

**Phase order is monotonic:** phases advance strictly forward (preflight → scan → interpret). The only backward edge is error routing from `scan` back to `preflight` for credential failures. Cancellation exits from any phase.

## Error Routing

When the CLI exits non-zero during the `scan` phase, match stderr against these patterns in order. On the first match, take the listed action.

| Condition                         | Detection                                              | Skill action                                                                                                                                                                                                                               |
| --------------------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Missing `bigquery.jobs.listAll`   | `AnalyzerError` substring `"bigquery.jobs.listAll"`    | Present three options: (1) grant IAM permission — show pre-formatted `gcloud` command from `references/iam-roles.md`, (2) re-run without query logs (omit `--include-query-logs`), (3) export logs manually and pass `--query-logs <path>` |
| Missing `bigquery.metadataViewer` | `ScannerError` from `validate_credentials()`           | Route back to `preflight` auth step. Load `references/phases/preflight.md` and resume at authentication verification.                                                                                                                      |
| ADC expired                       | `google.auth.exceptions.RefreshError` in stderr        | Route back to `preflight`. Show: `gcloud auth application-default login`                                                                                                                                                                   |
| No tables found                   | CLI exits with `"No tables found. Nothing to assess."` | Prompt user to check the `--datasets` filter or verify the project ID is correct.                                                                                                                                                          |
| Unknown fatal                     | Non-zero exit, no pattern match above                  | Show stderr verbatim. Offer two choices: retry or cancel.                                                                                                                                                                                  |
