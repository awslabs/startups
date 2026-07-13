# Scan Phase

## Entry Assertions

The Preflight phase has completed successfully. All of the following are true:

- `gcp_project` is set and non-empty.
- GCP authentication is confirmed (`adc_present` was `true` in preflight).
- `bq-assess` CLI is installed and on PATH.
- Optional parameters may also be present: `datasets`, `include_query_logs`, `query_log_days`.
- If the user says "stop" or "cancel" at any point during this phase, exit the skill immediately without running any further commands.

## Step 1: Construct CLI Command

Build the `bq-assess` command from the parameters collected during Preflight.

**Base command:**

```
bq-assess --gcp-project {gcp_project} --use-adc --format json,html --output reports/
```

**Append optional flags based on Preflight output:**

- If `datasets` was provided:

  ```
  --datasets {datasets}
  ```

- If `include_query_logs` is `false`: do NOT append any query-log flag. The CLI defaults to not analyzing query logs when `--include-query-logs` is absent. (The CLI does NOT have a `--no-query-logs` flag — do not invent one.)

- If `include_query_logs` is `true`:

  ```
  --include-query-logs
  ```

- If `include_query_logs` is `true` AND `query_log_days` was provided:

  ```
  --query-log-days {query_log_days}
  ```

**Example — full command with all options:**

```bash
bq-assess --gcp-project my-project --use-adc --format json,html --output reports/ --datasets prod_data,analytics --include-query-logs --query-log-days 60
```

**Example — minimal command (no query logs, no dataset filter):**

```bash
bq-assess --gcp-project my-project --use-adc --format json,html --output reports/
```

Show the constructed command to the user before executing so they can confirm or adjust.

## Step 2: Execute CLI

Run the constructed command using the Bash tool.

**Critical: Display the CLI's Rich progress output directly to the user.** The CLI uses Rich to render stage-by-stage progress (scanning metadata, analyzing query logs, scoring complexity, generating reports). Do **NOT** suppress, parse, or reformat these progress messages. Let them stream through as-is so the user can follow along and explain progress if a customer is watching.

## Step 3: Handle Results

After the CLI exits, inspect the exit code and output to determine the next action.

---

### Success (exit code 0)

The CLI has completed successfully and written reports to the output directory. The run produces **three mirrored JSON files** (not one) — capture all three:

1. Locate the three report files in the output directory:
   - `landing_json` — matches `reports/assessment-landing-*.json` (holds `summary` + `cost`)
   - `effort_json` — matches `reports/assessment-effort-*.json` (holds Migration Effort `entities[]` + Iceberg DDL)
   - `query_json` — matches `reports/assessment-query-*.json` (holds Query Complexity `entities[]`)
2. Verify each file exists and is non-empty. If `landing_json` is missing or empty, treat this as a generic fatal error (see below). If only `effort_json`/`query_json` is missing, note it and continue with what is present.
3. Tell the user the assessment completed successfully and show the output directory path.
4. Advance to the **Interpret phase**, passing `landing_json`, `effort_json`, and `query_json`.

---

### Permission Denied — Missing `bigquery.jobs.listAll`

**Detection:** stderr contains `AnalyzerError` AND the string `bigquery.jobs.listAll`.

This means the authenticated account lacks the IAM permission needed to read query logs from `INFORMATION_SCHEMA.JOBS`.

Present the user with **three options:**

#### Option 1: Grant the IAM permission and retry

Show the user the exact command to grant the required role:

```bash
gcloud projects add-iam-policy-binding {gcp_project} \
  --member="user:{sa_email}" \
  --role="roles/bigquery.resourceViewer"
```

> Replace `{sa_email}` with the user's GCP identity. They can find it with `gcloud auth list`.

Ask the user to run this command, then **retry the same `bq-assess` command** from Step 2.

#### Option 2: Re-run without query logs

Re-run the CLI without the `--include-query-logs` flag (simply omit it from the original command). This skips query log analysis entirely — the CLI defaults to metadata-only when the flag is absent.

Warn the user: "The assessment will still run, but the **cost comparison drops to a LOW-confidence range** (no observed slot usage), and Query Complexity confidence is lower without query history. Iceberg partition/sort-order and placement hints will be heuristic-only."

#### Option 3: Export logs manually and pass them to the CLI

The user can export query logs to a JSON file themselves and provide the path. Steps:

1. The user exports query logs from BigQuery (e.g., via `bq query` or the BigQuery console) to a local JSON file.
2. Re-run the CLI with `--query-logs {path_to_exported_logs}` instead of relying on the API.

Ask: **"Which option would you like? (1) Grant the permission, (2) Re-run without query logs, or (3) Export logs manually?"**

---

### Credential Error

**Detection:** stderr contains `ScannerError` from `validate_credentials()` **OR** stderr contains `google.auth.exceptions.RefreshError`.

The GCP credentials are invalid, expired, or not properly configured.

Tell the user: "Your GCP credentials appear to be invalid or expired. Let's go back to the authentication step."

Route back to the **Preflight phase** — specifically, load `references/phases/preflight.md` and resume at **Step 3: Handle Missing ADC**. The user will need to re-run:

```bash
gcloud auth application-default login
```

After re-authentication, return to this Scan phase and retry the CLI command.

---

### No Tables Found

**Detection:** CLI output contains `"No tables found. Nothing to assess."`.

The CLI found no BigQuery tables to assess in the specified project/datasets.

Tell the user: "The CLI found no tables to assess. This usually means the `--datasets` filter is too narrow or the project ID is incorrect."

Prompt the user to:

1. Double-check the `gcp_project` value.
2. If `datasets` was specified, verify the dataset names exist in the project.
3. Try running without the `--datasets` filter to scan all datasets.

Do **NOT** advance to the Interpret phase. Offer to re-run with corrected parameters.

---

### Generic Fatal Error

**Detection:** Non-zero exit code AND none of the specific patterns above matched.

Display the error message **verbatim** to the user. Do not summarize, truncate, or reformat it — the user may need the full output for debugging or to share with the tool maintainer.

Then ask: **"Would you like to retry the assessment, or cancel?"**

- If **retry**: re-run the same command from Step 2.
- If **cancel**: exit the skill.

## Cancellation

If the user says "stop" or "cancel" at any point during this phase — including while the CLI is running, while reviewing error options, or after seeing results — exit the skill immediately. Do not run additional commands or write files.

## Exit Conditions

The Scan phase is complete when **all** of the following are true:

1. The CLI exited with code 0.
2. `landing_json` is set to a valid file path that exists and is non-empty.
3. `effort_json` and `query_json` are captured if present (note any that are missing).

Pass `landing_json`, `effort_json`, and `query_json` to the **Interpret phase**.
