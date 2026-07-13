# Expected Response: Permission Denied — Missing `bigquery.jobs.listAll`

When the CLI fails with the `bigquery.jobs.listAll` permission error, the skill presents the SA with three options:

---

## Option 1: Grant IAM Permission and Retry

Grant the `roles/bigquery.resourceViewer` role, which includes the `bigquery.jobs.listAll` permission:

```bash
gcloud projects add-iam-policy-binding my-project \
  --member="user:{sa_email}" \
  --role="roles/bigquery.resourceViewer"
```

> Replace `{sa_email}` with the SA's GCP identity (find it with `gcloud auth list`).

After granting the role, the skill retries the same `bq-assess` command.

---

## Option 2: Re-run Without Query Logs

Re-run the CLI with the `--no-query-logs` flag appended to the original command. This skips query log analysis entirely.

**Warning the skill should surface:** The assessment will run with LOW confidence (heuristic-only scoring). Recommendations for DISTKEY, SORTKEY, and deployment mode will be less accurate without query log data.

---

## Option 3: Export Logs Manually

The SA exports query logs from BigQuery to a local JSON file (via `bq query` or the BigQuery console), then re-runs the CLI with:

```bash
--query-logs {path_to_exported_logs}
```

This bypasses the `INFORMATION_SCHEMA.JOBS` API call that requires the missing permission.

---

## Skill Behavior Invariants

- The skill does **not** advance to the Interpret phase after this error.
- The skill stays in the Scan phase until the SA selects an option.
- The skill asks: "Which option would you like? (1) Grant the permission, (2) Re-run without query logs, or (3) Export logs manually?"
