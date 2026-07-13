# Fixture: permission-denied

## Purpose

This fixture simulates the CLI failing with a `bigquery.jobs.listAll` permission error during the Scan phase. It verifies that the skill correctly detects the permission-denied pattern and presents the SA with three remediation options.

## Error Pattern

The Scan phase detects this error by matching two substrings in stderr:

- `AnalyzerError`
- `bigquery.jobs.listAll`

The simulated CLI error output is in `cli-error-output.txt`.

## Expected Skill Behavior

When this error is detected, the skill should present **three options** (documented in `expected-response.md`):

1. **Grant IAM permission** — Show the exact `gcloud projects add-iam-policy-binding` command to grant `roles/bigquery.resourceViewer`
2. **Re-run without query logs** — Re-run the CLI with `--no-query-logs`, warning about LOW confidence
3. **Export logs manually** — The SA exports query logs to a JSON file and passes `--query-logs {path}`

The skill should **not** advance to the Interpret phase. It stays in the Scan phase until the SA chooses an option.

## References

- Scan phase error handling: `references/phases/scan.md` → "Permission Denied" section
- IAM roles: `references/iam-roles.md` → "With Query Log Analysis" section
- Requirement 5.3: Three-option permission error handling
