# Privacy Policy

This document describes how the `bq-assess` CLI and its Claude Code skill handle data.
The tool is maintained by Amazon Web Services and distributed under the Apache-2.0 license.

## What this tool is

`bq-assess` is a read-only command-line tool plus a Claude Code skill that guides its use.
It scans BigQuery **metadata** (schemas, partitioning, view definitions, and — optionally —
query log statistics from `INFORMATION_SCHEMA`) and writes assessment reports (HTML + JSON)
to your local filesystem.

## Data the tool collects

**The tool itself collects no data.** It runs no telemetry, analytics, crash reporting, or
usage tracking. It sends nothing to the tool maintainers or to AWS.

## Data the tool reads and where it goes

- The CLI reads BigQuery metadata using **your** GCP credentials (Application Default
  Credentials or a service account you supply). It never reads table row data.
- All output (reports, optional collection bundles) is written **locally** to paths you
  choose. Nothing is uploaded anywhere by the tool.
- Optional query-log analysis reads anonymized query text from `INFORMATION_SCHEMA.JOBS`
  (literals stripped). You can disable query text collection entirely with
  `--exclude-query-text`.
- The `bq-collect` mode produces a plain-JSON, checksummed bundle designed to be
  **reviewed by you before sharing**. Whether and with whom you share a bundle is
  entirely your decision.

## GCP and AWS API calls

- BigQuery metadata reads are governed by your agreement with Google Cloud.
- Live pricing lookups (optional) query the public AWS Price List API and public GCP
  pricing endpoints; these requests contain no project data — only region/SKU filters.

## Data Claude / Claude Code receives

When you use the Claude Code skill, the content of your conversation — including report
summaries the skill reads and text loaded from skill files — is sent to Anthropic as part
of the normal model inference flow. That data flow is governed by Anthropic's privacy
policy, not this document. See <https://www.anthropic.com/legal/privacy>.

## Sensitive data

The tool never requests secrets or credentials beyond the GCP authentication you already
have configured, and its property-based test suite includes explicit checks that generated
reports contain no credential material.

## Changes

Changes to this policy are tracked in the repository's git history.

## Contact

For questions about this policy, open an issue at
<https://github.com/awslabs/startups/issues>.
