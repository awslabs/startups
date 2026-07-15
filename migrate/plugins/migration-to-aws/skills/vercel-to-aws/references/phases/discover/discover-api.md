---
_fragment: vercel-api
_of_phase: discover
_contributes:
  - discovery.json (deployments, env_var_names, domains, storage_integrations, usage_metrics, peripherals, api_routes, backend_service_detected sections)
---

# Discover Phase: Vercel REST API Enumeration (Always Runs)

> Self-contained fragment. Always runs using the token validated in
> `prescan-collect.md`. Enumerates everything the API surface exposes: projects,
> deployments, env var NAMES (never values), domains, cron jobs, Edge Config,
> KV/Postgres/Blob store integrations, and coarse usage metrics.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Enumerate Deployments

For each in-scope project (`tier1-signals.json.project_list`), list recent
deployments: production vs. preview, timestamps, status.

---

## Step 2: Enumerate Env Var Names (Never Values)

List environment variable KEYS only. Per Requirement 1.6, NEVER fetch, log, or
persist a value — not even for the "infrastructure-pointing env var hostnames"
Tier 3 input, which is scoped to hostnames extracted from values the FOUNDER
explicitly shares out-of-band, not something this fragment fetches directly via
the API.

---

## Step 3: Enumerate Domains and Crons

List custom domains and any Vercel Cron job configurations (supplementing what
`vercel.json` already declared in `discover-configs.md` — the API may show
crons configured outside `vercel.json` too).

---

## Step 4: Enumerate Storage Integrations

List Vercel KV, Postgres, Blob, and Edge Config integrations attached to the
project(s). For each, record the integration type and any AWS-relevant metadata
(e.g. approximate size, region) the API exposes without requiring secret access.

Contribute these to `peripherals[]` — this feeds the Recommendation Engine's
separability check (Requirement 7.1 rule 1) and the Scaffold phase's
peripheral-mapping lookup (`knowledge/peripheral-mappings.json`).

---

## Step 5: Detect a Separate Backend/API Service

Inspect the project structure and API route enumeration for signs of API routes
that could stand alone as a separable backend (e.g. a `pages/api/` or `app/api/`
tree substantial enough to be its own service, or an explicitly separate Vercel
project already serving as a backend API). Contribute `api_routes[]` and a
`backend_service_detected: true|false` flag — both feed the Recommendation
Engine's separability check directly.

---

## Step 6: Coarse Usage Metrics

Pull whatever usage aggregates the API exposes (invocation counts, bandwidth) at
whatever granularity is available. Per Requirement 4.4, a finding resting SOLELY
on this coarse usage data (with no log-drain backing) is LOW confidence — record
it as such, with `upgrade_input: "7-14 day log drain/observability export"`.

---

## Step 7: Output Contribution for Parent Orchestrator

```json
{
  "deployments": [...],
  "env_var_names": ["DATABASE_URL", "REDIS_URL", ...],
  "domains": ["<hostname>", ...],
  "crons": [...],
  "storage_integrations": [{ "type": "kv" | "postgres" | "blob" | "edge_config", "metadata": {...} }],
  "peripherals": [{ "type": "...", "source": "vercel_api" }, ...],
  "api_routes": ["<route>", ...],
  "backend_service_detected": false,
  "usage_metrics": { "confidence": "LOW", "invocation_counts": {...} }
}
```

Findings sourced purely from the Vercel API (no log drain) carry
`computed_from_inputs: ["vercel_api_token"]`. Usage-metric findings additionally
list `"log_drain_export"` in `computed_from_inputs` even though log drain data
was NOT used this run — this is intentional: it means a future re-invocation with
a log drain export newly present will correctly trigger recomputation of this
specific finding (per the recompute short-circuit mechanism in
`discover-coupling.md`/`discover-preflight.md`, and analogously here).

---

## Error Handling

| Error Category                                                        | Behavior                                                                                               |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| API rate-limited mid-enumeration                                      | Record what succeeded, mark remaining sections `"unavailable: rate_limited"`, retry once after backoff |
| Token lacks scope for a specific endpoint (e.g. storage integrations) | Record that section as `"unavailable: insufficient_token_scope"`, continue with the rest               |
| Zero deployments found for an in-scope project                        | Record as a LOW-confidence finding, note the project may be dormant/unused                             |

---

## Scope Boundary

**This fragment covers Vercel REST API enumeration ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Fetching or persisting env var VALUES (names only, ever)
- Header probing (that is `discover-probe.md`'s job)
- Computing the Recommendation Engine's separability verdict (this fragment
  contributes the raw signals; `recommend-rules.md` makes the decision)
- AWS service names or recommendations

**Your ONLY job: enumerate the Vercel API surface and record raw facts. Nothing
else.**
