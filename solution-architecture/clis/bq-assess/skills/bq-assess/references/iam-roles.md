# IAM Roles for bq-assess

This document lists the minimum GCP IAM roles required for each assessment mode and the exact commands to grant them.

## Finding Your User Email

To find the email associated with your active `gcloud` account:

```bash
gcloud auth list
```

Use the email shown as the `ACTIVE ACCOUNT` in the commands below.

---

## Metadata-Only Assessment (no query logs)

Use this mode when you want a quick structural assessment without analyzing query patterns.

### Required Role

| Role                            | Purpose                                                               |
| ------------------------------- | --------------------------------------------------------------------- |
| `roles/bigquery.metadataViewer` | Read table schemas, row counts, partitioning, and clustering metadata |

### Grant Command

```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:USER_EMAIL" \
  --role="roles/bigquery.metadataViewer"
```

Replace `PROJECT_ID` with the customer's GCP project ID and `USER_EMAIL` with the email from `gcloud auth list`.

---

## With Query Log Analysis

Use this mode for higher-confidence scoring. Query logs enable detection of join patterns, hub tables, and query frequency — which feed into the `many_join_partners` and `hub_table` complexity flags.

### Required Roles

| Role                            | Purpose                                                                                                 |
| ------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `roles/bigquery.metadataViewer` | Read table schemas, row counts, partitioning, and clustering metadata                                   |
| `roles/bigquery.resourceViewer` | Read query job history from `INFORMATION_SCHEMA.JOBS` (includes the `bigquery.jobs.listAll` permission) |

### Grant Commands

```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:USER_EMAIL" \
  --role="roles/bigquery.metadataViewer"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:USER_EMAIL" \
  --role="roles/bigquery.resourceViewer"
```

Replace `PROJECT_ID` with the customer's GCP project ID and `USER_EMAIL` with the email from `gcloud auth list`.

---

## Notes

- The `bigquery.resourceViewer` role includes the `bigquery.jobs.listAll` permission, which is specifically needed to read `INFORMATION_SCHEMA.JOBS` across all users in the project.
- If the `bigquery.jobs.listAll` permission is missing during a scan with query logs enabled, the CLI will return a permission error. The Scan phase presents three options: grant the role, re-run without query logs, or export logs manually.
- These are the **minimum** roles. Broader roles like `roles/bigquery.dataViewer` or `roles/bigquery.admin` also work but grant more access than necessary.
