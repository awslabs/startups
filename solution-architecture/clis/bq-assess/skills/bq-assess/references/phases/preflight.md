# Preflight Phase

## Entry Assertions

This is the first phase of the bq-assess skill. No prior state is required.

- Triggered when the user prompt matches a trigger phrase in SKILL.md (e.g., "assess BigQuery migration").
- No files, credentials, or prior CLI runs are assumed.
- If the user says "stop" or "cancel" at any point during this phase, exit the skill immediately without running any commands or writing any files.

## Step 1: Run Preflight Script

Execute the environment check script from the skill's `scripts/` directory:

```bash
bash scripts/preflight.sh
```

Parse the JSON output. The script returns:

```json
{
  "bq_assess_installed": true | false,
  "gcloud_installed": true | false,
  "adc_present": true | false,
  "adc_path": "/path/to/application_default_credentials.json"
}
```

If the script exits non-zero, do **NOT** advance to the Scan phase. Report the error to the user and offer to retry.

## Step 2: Handle Missing Tools

### If `bq_assess_installed` is `false`

Tell the user that the `bq-assess` CLI is not found on PATH. Provide the exact install commands:

```bash
pip3 install "git+https://github.com/awslabs/startups.git#subdirectory=solution-architecture/clis/bq-assess"
```

Then ask: **"Would you like me to run these commands, or will you handle the installation manually?"**

- If the user asks you to run them, execute the commands.
- If the user prefers to handle it manually, wait for them to confirm the install is complete.
- After installation, re-run `bash scripts/preflight.sh` to verify `bq_assess_installed` is now `true`.

### If `gcloud_installed` is `false`

Tell the user that the `gcloud` CLI is required for GCP authentication. Direct them to install it:

- Installation guide: https://cloud.google.com/sdk/docs/install

Wait for the user to confirm `gcloud` is installed, then re-run `bash scripts/preflight.sh` to verify.

## Step 3: Handle Missing ADC

### If `adc_present` is `false`

Tell the user that Application Default Credentials are not configured. Provide the exact command:

```bash
gcloud auth application-default login
```

Ask the user to run this command and confirm when authentication is complete. Do **NOT** run this command automatically — it requires interactive browser-based login.

After the user confirms, re-run `bash scripts/preflight.sh` to verify `adc_present` is now `true`.

## Step 4: Collect Inputs

Once all preflight checks pass (`bq_assess_installed`, `gcloud_installed`, and `adc_present` are all `true`), collect the following inputs from the user:

### Required

- **`gcp_project`** — Ask: "What is the GCP project ID for this assessment?"
  - This is required. Do not proceed without it.

### Optional

- **`datasets`** — Ask: "Any specific datasets to scope? Leave blank for all."
  - Accepts a comma-separated list of dataset names.
  - If left blank, the CLI scans all datasets in the project.

- **`include_query_logs`** — Ask: "Include query log analysis for higher confidence? (yes/no)"
  - Default: **yes**
  - If the user declines, note that the assessment will run with LOW confidence (heuristic-only scoring).

- **`query_log_days`** — Only ask if `include_query_logs` is yes.
  - Ask: "How many days of query logs to analyze? (default: 30, range: 1–90)"
  - Default: **30**
  - Accepted range: 1 to 90. If the user provides a value outside this range, ask them to correct it.

## Exit Conditions

All of the following must be true before advancing to the Scan phase:

1. `bq_assess_installed` is `true`
2. `gcloud_installed` is `true`
3. `adc_present` is `true`
4. `gcp_project` is non-empty

If any condition is not met, do **NOT** advance. Loop back to the relevant step above and resolve the issue.

When all conditions are satisfied, pass the collected parameters to the Scan phase:

- `gcp_project`
- `datasets` (if provided)
- `include_query_logs`
- `query_log_days` (if applicable)

## Critical Constraints

- Do **NOT** execute `bq-assess` during this phase. The CLI runs only in the Scan phase.
- Do **NOT** install packages without explicit SA confirmation.
- Do **NOT** write files outside the current working directory.
- If the preflight script exits non-zero, do **NOT** advance to the Scan phase.
