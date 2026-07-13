# bq-collect (beta)

Read-only BigQuery metadata collector. Runs in your GCP environment and produces an
auditable **bundle** — a directory of plain JSON files — that an AWS migration
specialist turns into a full lakehouse-migration assessment report on your behalf.

## What it does

- Scans BigQuery **metadata only** (schemas, partitioning, view/routine definitions,
  table sizes from `INFORMATION_SCHEMA`). It never reads table data contents.
- Aggregates workload statistics (slot utilization, query counts) from
  `INFORMATION_SCHEMA.JOBS_BY_PROJECT`.
- Collects **anonymized** query statements (all string and numeric literals are
  stripped and replaced with `?` before anything is written to disk). Disable
  entirely with `--exclude-query-text`.
- Snapshots public AWS/GCP pricing rates so the assessment is priced for your region.

## Usage

```bash
pip install bq-collect

# With Application Default Credentials:
bq-collect --gcp-project my-project --use-adc --output bundle-out/

# Or with a service-account key:
bq-collect --gcp-project my-project --credentials sa.json --output bundle-out/

# Privacy opt-out (no query text at all, only aggregated statistics):
bq-collect --gcp-project my-project --use-adc --exclude-query-text
```

Then review the JSON files in `bundle-out/bundle/` — everything is plain text — zip
the directory, and send it to your AWS contact:

```bash
zip -r bundle.zip bundle-out/bundle/
```

## Required permissions

- `roles/bigquery.metadataViewer` (or equivalent) on the project — metadata scan.
- `bigquery.jobs.listAll` — workload statistics and query statements (optional;
  collection degrades gracefully without it).

## Disclaimer

This tool is in **beta**. It performs read-only operations. All downstream cost
figures are directional estimates, not a quote, offer, or commitment from Amazon Web
Services or Google. The software is provided "AS IS" per the Apache License 2.0. You
are responsible for reviewing bundle contents before transmitting them outside your
environment.
