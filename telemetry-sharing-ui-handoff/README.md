# Migration Telemetry Sharing — UI Designer Handoff

## TL;DR

We're adding a "Share Your Migration Plan" feature to the GCP-to-AWS migration plugin. After the user completes their cost estimate (or final migration plan), they can opt in to generate a shareable URL that encodes their migration profile. The AWS Startups landing page decodes this client-side to match them with migration partners.

---

## What We Collect

The payload is assembled from data the plugin already gathered during earlier phases:

| Data                      | Source                        | Purpose                                                      |
| ------------------------- | ----------------------------- | ------------------------------------------------------------ |
| Clarification Q&A answers | `preferences.json`            | Understand the user's migration goals, constraints, timeline |
| Cost estimates            | `estimation-*.json`           | Current GCP spend vs projected AWS spend                     |
| Recommendation path       | Estimation phase              | "migrate optimized", "migrate phased", or "stay"             |
| Detected GCP services     | `gcp-resource-inventory.json` | What infrastructure they're running                          |
| Resource names            | Same                          | Specific resource identifiers (e.g., "prod-db")              |
| Workload types            | Phase artifacts               | infra, AI, billing-only                                      |
| Spend band                | Derived from costs            | under-10k, 10k-50k, 50k-100k, over-100k                      |

**Explicitly excluded:** source code, file paths, credentials, .tfstate, environment secrets.

---

## How It Works

1. Data is assembled into a JSON object
2. Secrets are redacted (AWS keys, passwords, tokens → `[REDACTED]`)
3. JSON is compressed (gzip) and encoded as Base64URL
4. The encoded string becomes a URL fragment: `https://aws.amazon.com/startups/migrate/connect#<payload>`
5. **No server receives the data during navigation** — the `#fragment` is decoded entirely client-side by the landing page

---

## User Flow — Two Checkpoints

### Checkpoint 1: After Cost Estimate

```
─── Share Your Migration Plan ───

This link encodes your migration profile for partner matching:
✓ Included: Clarify answers, estimated costs, recommendation path,
  detected GCP services, resource names, and workload types.
✗ Excluded: Source code, local file paths, credentials, .tfstate
  contents, and environment secrets.

The link uses a URL fragment (#) — no data is sent to any server
when you click it. The landing page decodes everything client-side.

[A] Send feedback & share plan
[B] Send feedback only
[C] No thanks, continue to Generate
```

### Checkpoint 2: After Migration Plan Generated

```
─── Share Your Completed Plan ───

(Same disclosure text)

[A] Share completed plan
[B] No thanks, finish
```

### Output When User Shares

```
Share link generated:
https://aws.amazon.com/startups/migrate/connect#eJyNVE2P2z...

Copy-paste URL (if the above is not clickable):
https://aws.amazon.com/startups/migrate/connect#eJyNVE2P2z...
```

The URL is duplicated for terminal environments where link detection varies.

---

## Landing Page Requirements (for UI)

The landing page at `aws.amazon.com/startups/migrate/connect` needs to:

1. Read `window.location.hash` (strip the leading `#`)
2. Base64URL-decode the string
3. Gunzip the result
4. Parse the JSON payload (schema below)
5. Render partner matching based on the migration profile

---

## Payload JSON Schema (v1.0)

```json
{
  "schema_version": "1.0",
  "plugin_version": "0.4.2",
  "generated_at": "2026-06-14T18:30:00Z",

  "clarify_answers": {
    "migration_timeline": { "value": "3-6 months", "source": "user" },
    "team_size": { "value": "5-10", "source": "user" },
    "compliance_requirements": { "value": "SOC2, HIPAA", "source": "inferred" }
  },

  "recommendation": {
    "path": "migrate_optimized",
    "rationale": "Your workload is primarily compute+database with no vendor lock-in..."
  },

  "cost_summary": {
    "current_gcp_monthly": 12500,
    "projected_aws_monthly": 10800,
    "delta": -1700,
    "currency": "USD"
  },

  "detected_services": [
    "google_compute_instance",
    "google_sql_database_instance",
    "google_storage_bucket",
    "google_container_cluster"
  ],

  "resource_names": [
    { "type": "google_sql_database_instance", "name": "prod-db" },
    { "type": "google_compute_instance", "name": "api-server-1" },
    { "type": "google_container_cluster", "name": "app-cluster" }
  ],

  "workload_types": ["infra", "ai"],

  "spend_band": "10k-50k"
}
```

---

## Key Design Constraints

- **8,192 char max** for the Base64URL payload (URL length limits)
- If the payload is too large, fields are truncated in priority order (resource names first, then inferred answers, then defaults, then rationale text)
- These fields are **never removed**: `schema_version`, `plugin_version`, `generated_at`, `recommendation.path`, `cost_summary`, `workload_types`, `spend_band`
- **Spend band values**: `"under-10k"`, `"10k-50k"`, `"50k-100k"`, `"over-100k"`, `"unknown"`
- **Recommendation paths**: `"migrate_optimized"`, `"migrate_phased"`, `"stay"`

---

## Questions for UI Design

- How should partner matching results be displayed based on spend band + workload type?
- Should the page show a decoded summary of the user's profile before matching?
- Error state: what does the page show if the hash is missing, malformed, or uses an unsupported schema version?
- Mobile consideration: these URLs will be shared via clipboard — does the page need responsive handling?
