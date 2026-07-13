# bq-assess CLI Reference

For the guided experience, see the [main README](../README.md).

## Install

```bash
git clone <repo-url>
cd bigqueryToRedshift
pip install -e .
```

## Usage

```bash
# Minimal
bq-assess --gcp-project my-project --use-adc

# With query logs (higher confidence)
bq-assess --gcp-project my-project --use-adc --include-query-logs

# With exported query logs (no bigquery.jobs.listAll needed)
bq-assess --gcp-project my-project --use-adc --query-logs path/to/logs.json

# Full options
bq-assess \
  --gcp-project my-project \
  --use-adc \
  --datasets "prod_data,analytics" \
  --include-query-logs \
  --query-log-days 60 \
  --format json,html,csv \
  --output reports/

# Interactive mode
bq-assess --interactive

# From config file
bq-assess --config assessment-config.yaml
```

## Options

| Flag                      | Description                                               | Default      |
| ------------------------- | --------------------------------------------------------- | ------------ |
| `--gcp-project`           | GCP project ID                                            | required     |
| `--credentials`           | Path to service account JSON                              | —            |
| `--use-adc`               | Use Application Default Credentials                       | false        |
| `--datasets`              | Comma-separated dataset filter                            | all datasets |
| `--include-query-logs`    | Analyze INFORMATION_SCHEMA.JOBS                           | false        |
| `--query-logs`            | Path to exported query logs JSON                          | —            |
| `--query-log-days`        | Query log lookback window in days (1-90)                  | 30           |
| `--redshift-type`         | Target Redshift node type (overrides auto-recommendation) | auto         |
| `--bigquery-monthly-cost` | Monthly BigQuery spend override                           | estimated    |
| `--output`                | Output directory                                          | reports/     |
| `--format`                | Output formats (json, html, csv)                          | json,html    |
| `--interactive`           | Interactive prompt mode                                   | false        |
| `--config`                | Path to YAML config file                                  | —            |

Note: `--query-log-days` implies `--include-query-logs` automatically.

## Output

- `assessment-<id>.json` — full assessment with per-table details
- `assessment-<id>.html` — visual report for customer walkthroughs
- `tables-auto.csv` — tables safe for automated migration
- `tables-review.csv` — tables needing review
- `tables-manual.csv` — tables requiring manual effort

## Query Logs

Without query logs, the tool uses heuristics for DISTKEY/SORTKEY recommendations (LOW confidence).

With `--include-query-logs`, it analyzes `INFORMATION_SCHEMA.JOBS` for JOIN patterns and hub tables (HIGH confidence). Requires `roles/bigquery.resourceViewer`.

Alternatively, `--query-logs <path>` accepts an exported JSON file — a JSON array of objects with at least a `"query"` field. This bypasses the API entirely.
