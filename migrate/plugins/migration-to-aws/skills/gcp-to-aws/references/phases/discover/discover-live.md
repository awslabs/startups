# Discover Phase: Live Discovery (gcloud CLI)

> Self-contained live-discovery sub-file. Inventories the user's GCP project
> directly through their authenticated `gcloud` CLI — read-only, consent-gated,
> env-var names only. Produces the SAME artifacts as `discover-iac.md`
> (`gcp-resource-inventory.json` + `gcp-resource-clusters.json`, simplified
> clustering mode), so all downstream phases work identically. When IaC discovery
> also ran, merges live findings into the existing inventory and surfaces drift.
> If the user declines consent or `gcloud` is unavailable, exits cleanly with no
> output.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Security Contract (applies to every step)

1. **Exact-command whitelist.** Run ONLY commands that appear in Step 0 (preflight)
   or the Step 2 Capture Command Table. Never any mutating verb (`create`, `update`,
   `delete`, `set`, `add`, `remove`, `deploy`, `apply`, `import`, `patch`), never
   `gcloud auth login` (interactive — hand off to the user), never
   `gcloud auth print-access-token` or `print-identity-token` (prints credentials).
2. **Never capture secret values.** Every capture command uses an explicit
   `--format="json(...)"` field projection. Projections include env var **names**
   but never env var **values**, and never GCE instance `metadata.items` values.
   Additionally, apply `discover-iac.md`'s sensitive-key redaction patterns
   (`password`, `secret`, `api_key`, `access_key`, `private_key`, `client_secret`,
   `token`, `credential`, `auth` — case-insensitive) to any config field before it
   is written into an artifact: replace matched values with `"[REDACTED]"`.
3. **Always explicit scope.** Every command passes `--project="$GCP_PROJECT"`
   explicitly. Never rely on the active gcloud config inside capture commands.
4. **Capture to files, not context.** Redirect stdout to files under
   `$MIGRATION_DIR/live-capture/`. Process any capture file larger than ~100
   resources with a throwaway extraction script (same pattern as `discover.md`'s
   lightweight billing extraction) — do NOT Read large raw captures into context.
5. **Consent first.** No `gcloud` command from the Step 2 table runs before the
   user answers `[A]` in Step 1. Preflight commands in Step 0 are limited to
   version/auth/config checks that touch no project data.

---

## Step 0: Preflight

1. **CLI installed:** run `gcloud --version` (first line only).
   - Missing → tell the user: "The gcloud CLI isn't installed. Install it
     (https://cloud.google.com/sdk/docs/install) and tell me to continue, or skip
     live discovery." Wait. If skipped → exit cleanly.
2. **Authenticated:** run `gcloud auth list --filter=status:ACTIVE --format="value(account)"`.
   - Empty → tell the user: "Your gcloud CLI has no active account. Run
     `gcloud auth login` in your terminal — it needs a browser, so I can't run it
     for you — then tell me to continue." Wait. If declined → exit cleanly.
3. **Project:** run `gcloud config get-value project`.
   - Show the result and ask: "Discover project `[project-id]`? [Y] Yes /
     [N] Use a different project (type its ID)". Set `$GCP_PROJECT` accordingly.
     If the value is empty, ask the user to type the project ID. One project per
     run — for multiple projects, run the migration once per project.

## Step 1: Consent Gate

Output exactly, then wait for the user's choice:

```
─── Live GCP Discovery (read-only) ───

I can inventory project [$GCP_PROJECT] directly using your
authenticated gcloud CLI. This runs LIST/DESCRIBE commands only:

  ✓ Captured: resource names, types, regions, machine/instance
    sizing, container images, network topology, env var NAMES,
    secret NAMES, and labels.
  ✗ Never captured: env var values, secret values, database
    contents, instance metadata values, access tokens, or source
    code. No command that creates, changes, or deletes anything
    will run.

Output is written to .migration/<run>/live-capture/ (gitignored).

[A] Proceed with live discovery
[B] Skip — use workspace files only
```

- **[A]** → continue to Step 2.
- **[B]** → exit cleanly with no output (record the decline for the orchestrator).

## Step 2: Capture

Create `$MIGRATION_DIR/live-capture/`.

**2a. Fast path — Cloud Asset Inventory (one call, whole project):**

```
gcloud asset search-all-resources --project="$GCP_PROJECT" \
  --format=json > $MIGRATION_DIR/live-capture/assets.json
```

- Success → record `method: "asset_search"` in the manifest, then run only the
  **enrichment rows** (marked E) of the table below for asset types that were
  found (asset search returns names/types/locations but thin config).
- Failure (Cloud Asset API not enabled, or permission denied) → record
  `method: "per_service"` and run every applicable table row. Do NOT try to
  enable the API (that would be a mutation).

**2b. Capture Command Table.** Each row redirects to the named file. On
"API not enabled" / permission errors: record the row as `failed` or `skipped`
in the manifest and continue — a missing service is normal, never a halt.

| #  | Command (always with `--project="$GCP_PROJECT"`)                                                                                                                                                                                                                                                                                                                                                                    | Output file            | Mode |
| -- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | ---- |
| 1  | `gcloud run services list --region=- --format="json(metadata.name, metadata.labels, metadata.annotations, spec.template.metadata.annotations, spec.template.spec.serviceAccountName, spec.template.spec.containers[].image, spec.template.spec.containers[].resources.limits, spec.template.spec.containers[].env[].name, spec.template.spec.containerConcurrency, spec.template.spec.timeoutSeconds, status.url)"` | `run.json`             | E    |
| 2  | `gcloud sql instances list --format="json(name, region, databaseVersion, settings.tier, settings.availabilityType, settings.dataDiskSizeGb, settings.ipConfiguration.privateNetwork, settings.ipConfiguration.ipv4Enabled, settings.backupConfiguration.enabled)"`                                                                                                                                                  | `sql.json`             | E    |
| 3  | `gcloud container clusters list --format="json(name, location, currentNodeCount, currentMasterVersion, network, subnetwork, autopilot.enabled, nodePools[].name, nodePools[].config.machineType, nodePools[].initialNodeCount)"`                                                                                                                                                                                    | `gke.json`             | E    |
| 4  | `gcloud functions list --format="json(name, environment, runtime, entryPoint, availableMemoryMb, serviceConfig.availableMemory, serviceConfig.runtime, serviceConfig.timeoutSeconds, eventTrigger.eventType, serviceConfig.serviceAccountEmail)"`                                                                                                                                                                   | `functions.json`       | E    |
| 5  | `gcloud storage buckets list --format="json(name, location, storageClass, timeCreated, iamConfiguration.uniformBucketLevelAccess.enabled, versioning.enabled)"`                                                                                                                                                                                                                                                     | `buckets.json`         | E    |
| 6  | `gcloud pubsub topics list --format="json(name, labels)"`                                                                                                                                                                                                                                                                                                                                                           | `pubsub.json`          |      |
| 7  | `gcloud compute instances list --format="json(name, zone, machineType, status, networkInterfaces[].network, networkInterfaces[].subnetwork, disks[].diskSizeGb, serviceAccounts[].email, labels)"`                                                                                                                                                                                                                  | `gce.json`             | E    |
| 8  | `gcloud compute networks list --format="json(name, autoCreateSubnetworks, subnetworks)"`                                                                                                                                                                                                                                                                                                                            | `networks.json`        |      |
| 9  | `gcloud compute networks subnets list --format="json(name, region, network, ipCidrRange)"`                                                                                                                                                                                                                                                                                                                          | `subnets.json`         |      |
| 10 | `gcloud redis instances list --region=<each region seen in rows 1–9> --format="json(name, tier, memorySizeGb, redisVersion, authorizedNetwork, locationId)"`                                                                                                                                                                                                                                                        | `redis-<region>.json`  | E    |
| 11 | `gcloud secrets list --format="json(name, replication, createTime)"` — secret NAMES only, never `versions access`                                                                                                                                                                                                                                                                                                   | `secrets.json`         |      |
| 12 | `gcloud iam service-accounts list --format="json(email, displayName, disabled)"`                                                                                                                                                                                                                                                                                                                                    | `sa.json`              |      |
| 13 | `gcloud dns managed-zones list --format="json(name, dnsName, visibility)"`                                                                                                                                                                                                                                                                                                                                          | `dns.json`             |      |
| 14 | `gcloud spanner instances list --format="json(name, config, nodeCount, processingUnits)"`                                                                                                                                                                                                                                                                                                                           | `spanner.json`         |      |
| 15 | `gcloud firestore databases list --format="json(name, type, locationId)"`                                                                                                                                                                                                                                                                                                                                           | `firestore.json`       |      |
| 16 | `gcloud ai endpoints list --region=<each region seen> --format="json(name, displayName, deployedModels[].model)"` — only if asset search found `aiplatform.googleapis.com/*` assets or per-service mode                                                                                                                                                                                                             | `vertex-<region>.json` | E    |

**Scale guard:** if `assets.json` (or any capture) exceeds ~100 resources, write a
throwaway extraction script to `$MIGRATION_DIR/_extract_live.py` that projects only
the fields needed by Step 3, run it, write its JSON output next to the raw file
with a `-extracted.json` suffix, and delete the script. Never Read the oversized
raw file directly.

**2c. Write the manifest** — `$MIGRATION_DIR/live-capture/manifest.json`:

```json
{
  "captured_at": "<ISO 8601 UTC>",
  "gcloud_version": "<first line of gcloud --version>",
  "account": "<active account email>",
  "project": "<$GCP_PROJECT>",
  "method": "asset_search|per_service",
  "captures": [
    { "command": "<row command>", "file": "<file>", "status": "ok|failed|skipped", "note": null }
  ]
}
```

Every attempted or deliberately skipped row gets an entry.

## Step 3: Map Captures to Inventory Resources

Synthesize Terraform-style identity so downstream design-refs (keyed on
`google_*` types) work unchanged:

- `address` = `{terraform_type}.{sanitized_resource_name}` (lowercase, `-`→`_`)
- `type` = from the mapping table below
- `name` = sanitized resource name
- `config` = the projected fields from the capture (redaction rules from the
  Security Contract apply)
- `source` = `"live"` on every entry

**Asset/CLI type → Terraform type mapping:**

| Captured type                                  | Terraform `type`                                                                                         |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `run.googleapis.com/Service` / row 1           | `google_cloud_run_v2_service`                                                                            |
| `sqladmin.googleapis.com/Instance` / row 2     | `google_sql_database_instance`                                                                           |
| `container.googleapis.com/Cluster` / row 3     | `google_container_cluster`                                                                               |
| row 4 with `environment: GEN_2`                | `google_cloudfunctions2_function`                                                                        |
| row 4 with `environment: GEN_1` (or unset)     | `google_cloudfunctions_function`                                                                         |
| `storage.googleapis.com/Bucket` / row 5        | `google_storage_bucket`                                                                                  |
| `pubsub.googleapis.com/Topic` / row 6          | `google_pubsub_topic`                                                                                    |
| `compute.googleapis.com/Instance` / row 7      | `google_compute_instance`                                                                                |
| `compute.googleapis.com/Network` / row 8       | `google_compute_network`                                                                                 |
| `compute.googleapis.com/Subnetwork` / row 9    | `google_compute_subnetwork`                                                                              |
| `redis.googleapis.com/Instance` / row 10       | `google_redis_instance`                                                                                  |
| `secretmanager.googleapis.com/Secret` / row 11 | `google_secret_manager_secret`                                                                           |
| `iam.googleapis.com/ServiceAccount` / row 12   | `google_service_account`                                                                                 |
| `dns.googleapis.com/ManagedZone` / row 13      | `google_dns_managed_zone`                                                                                |
| `spanner.googleapis.com/Instance` / row 14     | `google_spanner_instance`                                                                                |
| `firestore.googleapis.com/Database` / row 15   | `google_firestore_database`                                                                              |
| `bigquery.googleapis.com/Dataset`              | `google_bigquery_dataset` (triggers the BigQuery specialist gate downstream — include it)                |
| `aiplatform.googleapis.com/Endpoint` / row 16  | `google_vertex_ai_endpoint`                                                                              |
| `aiplatform.googleapis.com/*` (other)          | `google_vertex_ai_*` (matching suffix)                                                                   |
| Any other asset type                           | Do NOT guess a mapping. Count it in `live_metadata.unmapped_asset_types` and exclude from the inventory. |

**Classification:** apply `discover-iac.md` Step 3S rules — the Priority 1 PRIMARY
types list, everything else SECONDARY with role inferred from type
(`google_service_account` → identity; networks/subnets/DNS → network_path;
secrets → encryption; else configuration). `confidence: 0.99`.

**AI detection:** if any `aiplatform.googleapis.com/*` asset or Vertex endpoint was
captured, populate `ai_detection` exactly as `discover-iac.md` Step 2 would
(signal method `"live_gcloud"`, confidence 95, `ai_services: ["vertex_ai"]`,
`has_ai_workload: true`). Otherwise `has_ai_workload: false`, `confidence: 0`.

## Step 4: Infer Edges from Resolved Config

Live captures contain resolved values, which often beat HCL references. Build
`edges[]` using ONLY these deterministic rules (evidence = the config field path):

| Config field (captured)                                         | Edge                                                                |
| --------------------------------------------------------------- | ------------------------------------------------------------------- |
| Cloud Run annotation `run.googleapis.com/cloudsql-instances`    | run service → SQL instance, `data_dependency`                       |
| Cloud Run annotation `run.googleapis.com/vpc-access-connector`  | run service → network, `network_membership`                         |
| `spec.template.spec.serviceAccountName` / `serviceAccountEmail` | service account → workload, `serves` (populate the SA's `serves[]`) |
| SQL `settings.ipConfiguration.privateNetwork`                   | SQL instance → network, `network_membership`                        |
| GCE `networkInterfaces[].network` / GKE `network`               | instance/cluster → network, `network_membership`                    |
| Subnet `network`                                                | subnet → network, `network_membership`                              |
| Redis `authorizedNetwork`                                       | redis → network, `network_membership`                               |

No other inference — do not guess relationships from names, labels, or env var
names.

## Step 5: Cluster (Simplified Mode)

Apply `discover-iac.md` **Step 3S** clustering rules regardless of resource count
(networking cluster at depth 0; one cluster per PRIMARY plus its `serves`
secondaries at depth 1; same `{category}_{type}_{region}_{sequence}` naming;
region from the captured `region`/`location`/zone-derived-region). Set metadata
`"clustering_mode": "simplified_live"`. If more than 25 PRIMARY resources were
captured, warn the user that clustering is coarse at this scale and suggest
narrowing to specific services or regions — but continue.

**Live-specific clustering rules** (Step 3S assumes files, which don't exist here):

- **Regionless resources** (Pub/Sub topics, global buckets without a single
  region): use `"global"` as the region component of `cluster_id` and
  `gcp_region`.
- **Shared secondaries** (e.g., one service account serving multiple primaries):
  assign the resource to the cluster of the FIRST primary in its `serves[]`
  array; `serves[]` still lists all of them.
- **Evidence-less secondaries** (no Step 4 edge and empty `serves[]`, e.g.,
  secrets): do NOT attach them to an unrelated primary's cluster and do NOT
  fabricate a `serves` relationship. Group them into their own cluster per
  category+region (e.g., `security_secrets_global_001`) at depth 1.

## Step 6: Merge with IaC Discovery (only if `discover-iac.md` produced output)

If `gcp-resource-inventory.json` does NOT already exist, skip to Step 7 (live is
the sole source).

Otherwise the IaC inventory + clusters are the BASE. Match live↔IaC entries by
Terraform `type` + GCP resource name (live `name` vs the IaC resource's
`config.name`, falling back to the address name component). Then:

1. **Matched:** keep the IaC entry (its address, classification, cluster,
   depth). Overwrite `config` sizing/capacity fields with live values (live
   reflects reality). Record every changed field in
   `live_metadata.drift.config_conflicts[]` as
   `{ "address", "field", "terraform_value", "live_value" }`. Set
   `source: "live+terraform"`.
2. **Live-only:** append the entry with `unmanaged_by_terraform: true`. Attach it
   to an existing cluster of the same category+region when one exists; otherwise
   append a new simplified cluster (and add it to `creation_order` at its depth).
3. **IaC-only:** set `source: "terraform"` on every unmatched IaC entry. Set
   `not_found_live: true` ONLY if the capture covering that resource's service
   succeeded (manifest `ok`). If the relevant capture failed or was skipped,
   leave the entry otherwise untouched — absence of evidence is not drift.
4. **Drift summary:** `live_metadata.drift = { "resources_live_only": N,
   "resources_terraform_only": M, "config_conflicts": [...] }`.
   `resources_terraform_only` counts ONLY entries with `not_found_live: true`
   (confirmed absent), never capture-failed unknowns.
5. **Merged metadata:** keep the IaC base's `clustering_mode` (`"simplified"` or
   absent for full clustering) — `"simplified_live"` is for live-only runs. Set
   `metadata.discovery_sources` to include both sources.

Never silently resolve a disagreement — every conflict lands in the drift record.

## Step 7: Write Output Files

Load `references/shared/schema-discover-iac.md` (if not already loaded) and
write/update:

1. `$MIGRATION_DIR/gcp-resource-inventory.json` — exact schema; plus:
   - `metadata.discovery_sources`: `["live"]`, `["terraform", "live"]`, etc.
   - `metadata.clustering_mode`: `"simplified_live"` (live-only runs)
   - top-level `live_metadata`:

   ```json
   {
     "found": true,
     "captured_at": "<from manifest>",
     "project": "<$GCP_PROJECT>",
     "method": "asset_search|per_service",
     "capture_warnings": ["<failed/skipped manifest entries>"],
     "unmapped_asset_types": { "<asset type>": 2 },
     "drift": { "resources_live_only": 0, "resources_terraform_only": 0, "config_conflicts": [] }
   }
   ```

   (`drift` present only when Step 6 merged.)

2. `$MIGRATION_DIR/gcp-resource-clusters.json` — exact schema (merged or fresh).
3. Validate per `discover-iac.md` Step 7c (every resource in exactly one cluster,
   IDs consistent, valid JSON). Report: "Live discovery: X resources captured from
   project [id] (Y unmanaged by Terraform, Z config conflicts)."

The parent `discover.md` owns the phase status update — do not touch
`.phase-status.json` here.

---

## Error Handling

| Error                                              | Behavior                                                                                                                     |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| gcloud missing / no active account / user declines | Exit cleanly with no output (orchestrator falls back to file-based sources)                                                  |
| Asset search fails (API not enabled, 403)          | Fall back to per-service rows; record in manifest                                                                            |
| Individual row fails (API not enabled, 403)        | Record `failed`/`skipped`, continue — never a halt                                                                           |
| Token expired mid-run                              | Stop capturing; hand off ("run `gcloud auth login`, then tell me to continue"); on resume re-run Step 2 (captures overwrite) |
| Capture file unparseable                           | Record warning, skip that file, continue                                                                                     |
| Every capture failed                               | Exit with no output; tell the user which permissions are missing (`roles/viewer` covers all rows)                            |

**Key principle:** partial results are better than no results. Record what failed;
never fabricate what wasn't captured.

## Scope Boundary

**This sub-file covers live GCP discovery ONLY.**

FORBIDDEN — Do NOT include ANY of:

- AWS service names, recommendations, or equivalents
- Migration strategies, phases, timelines, cost estimates, or effort estimates
- Any mutating gcloud command, `auth login`, or token printing
- Env var values, secret values, or unredacted sensitive config anywhere

**Your ONLY job: inventory what exists in GCP. Nothing else.**
