# bq-assess — BigQuery Migration Assessment

Scan a BigQuery warehouse and get a migration assessment report with two-axis scoring
(data movement effort + query rewrite complexity), S3 Tables DDL, and a cost comparison.
Targets S3 Tables (Apache Iceberg) storage + Amazon Redshift (Serverless or Provisioned)
compute. Read-only — no AWS account needed to run an assessment.

## Quick Start (Claude Code)

The fastest way to run an assessment. The skill handles setup, execution, and report
interpretation for you.

```
/plugin marketplace add awslabs/startups
/plugin install bq-assess@startups-for-aws
```

Then ask:

> "Assess BigQuery migration for project my-project"

## Prerequisites

- [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed
- GCP authentication configured:

  ```bash
  gcloud auth application-default login
  ```

- IAM role on the target project: `roles/bigquery.metadataViewer`
- For query log analysis (optional, higher confidence): `roles/bigquery.resourceViewer`

The skill checks your environment, runs the scan, summarizes the report in plain
English, and points you to the generated HTML report.

## What You Get

The tool scans BigQuery metadata and produces:

- Two-axis scoring per entity:
  - **Migration Effort** (AUTO / ASSISTED / MANUAL) — data movement difficulty to S3 Tables
  - **Query Complexity** (PORTABLE / ADAPT / REWRITE) — SQL rewrite difficulty for Redshift
- S3 Tables (Iceberg) DDL for every table
- Cost comparison (BigQuery vs AWS)
- HTML report (3 pages: landing summary, effort breakdown, query detail)
- JSON output for downstream automation

## How It Works

```
Preflight → Scan → Interpret
```

1. **Preflight** — checks tools and credentials, collects your project ID
2. **Scan** — runs the assessment CLI, streams progress
3. **Interpret** — reads the JSON report, highlights top effort/complexity entities and
   cost findings, points to the HTML report

Say "stop" or "cancel" at any point to exit.

## CLI Usage

Prefer the command line? Install directly:

```bash
pip3 install "git+https://github.com/awslabs/startups.git#subdirectory=solution-architecture/clis/bq-assess"
```

Then:

```bash
bq-assess --gcp-project my-project --use-adc --format html,json --output reports/
```

For accurate cost estimates, add reservation details:

```bash
bq-assess --gcp-project my-project --use-adc \
  --reservation-config my-reservation-config.json \
  --format html,json --output reports/
```

See the [CLI Reference](docs/CLI_REFERENCE.md) for all flags and options.

## Two Ways to Run

- **Direct** (`bq-assess`) — scan and generate the report in one step, inside the
  environment that has BigQuery access.
- **Collect, then report** (`bq-collect` + `bq-assess report`) — run the lightweight
  collector where the BigQuery credentials live; it writes a plain-JSON, checksummed
  bundle you can review before sharing. Generate the report later, anywhere, fully
  offline: `bq-assess report --bundle <dir-or-zip>`. Useful when the person running
  the scan and the person analyzing the results are not the same.

## Documentation

- [CLI Reference](docs/CLI_REFERENCE.md) — all flags, options, and examples
- [Migration Complexity Guide](docs/MIGRATION_COMPLEXITY_GUIDE.md) — two-axis scoring rules explained
- [CONTEXT.md](CONTEXT.md) — project vocabulary and target architecture
- [Architecture Decision Records](docs/adr/) — why Iceberg storage + Redshift engine, two scoring axes, partition mapping, per-entity placement

## Development

```bash
pip3 install -e ".[dev]"
pytest                           # 300+ tests (unit + property-based)
bash tests/plugin/structure.sh   # plugin structural checks
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
