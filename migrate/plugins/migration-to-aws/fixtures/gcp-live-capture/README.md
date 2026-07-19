# GCP live-discovery fixtures (replay mode)

Canned `gcloud` CLI outputs for testing the `gcp-to-aws` live-discovery path
(`references/phases/discover/discover-live.md`) without a GCP project. The
synthetic project `acme-prod` uses **per-service fallback mode** (the manifest
records the Cloud Asset API fast path as `failed` — the common startup case
after the user declines the enable soft-ask, or a permission error skips it)
and exercises the designed-for behaviors:

- **orders-api** (Cloud Run) — carries the `run.googleapis.com/cloudsql-instances`
  annotation and a service account, driving the Step 4 edge-inference rules; its
  env list has NAMES ONLY (including secret-looking names like
  `STRIPE_SECRET_KEY` — if a value ever appears in output, the projection rule
  broke). Terraform declares it as the LEGACY `google_cloud_run_service` (v1)
  type while live maps to v2 — locking the Step 6 type-alias rule (one merged
  resource, never a false not_found_live/unmanaged pair).
- **orders-db** (Cloud SQL) — live tier `db-custom-2-8192` vs Terraform's
  `db-f1-micro`: the classic console-resize drift (Step 6 rule 1).
- **cache** (Memorystore Redis), **web-frontend** (Cloud Run), two secrets, and
  the `acme-prod-uploads` bucket — all absent from Terraform → click-ops drift
  (`unmanaged_by_terraform`, Step 6 rule 2).
- **acme-prod-assets** bucket — in Terraform, absent live, buckets capture `ok`
  → `not_found_live` (Step 6 rule 3).
- **events** (Pub/Sub topic) — in Terraform, and the pubsub capture FAILED →
  must NOT be marked `not_found_live` (rule 3's "absence of evidence is not
  drift" negative case).
- Empty `gke.json` / `functions.json` / `gce.json` — services with nothing
  deployed produce no entries and no errors.

## How to replay

**Scenario A — live-only (no Terraform):**

1. Create a scratch directory with NO `.tf` files, app code, or billing exports.
2. Create `.migration/0720-1820/` and copy `live-capture/` into it.
3. Invoke the gcp-to-aws skill ("migrate my GCP infrastructure to AWS").
4. Discover should treat live as the primary source (Step 1d), the sub-file
   parses captures instead of re-running gcloud, and the output is a
   schema-valid `gcp-resource-inventory.json` + `gcp-resource-clusters.json`
   with `clustering_mode: "simplified_live"`, `discovery_sources: ["live"]`,
   and no `drift` key.

**Scenario B — live + Terraform (drift exercise):**

1. As above, but also copy `workspace-terraform/main.tf` into the scratch root.
2. `main.tf` is deliberately stale — each divergence is commented with the
   Step 6 merge rule it exercises.
3. Check outputs against `expected-drift.json` — machine-checkable via
   `python3 check_expected_drift.py <run-dir>` (exits non-zero on any failed
   assertion).

**What a run must never produce** (either scenario): env var or secret values
anywhere; any mutating `gcloud` command (including `gcloud services enable`);
AWS service names in discover artifacts; a halt caused by the failed
asset-search/pubsub captures.

**Soft-ask note:** live capture (Step 2a) may offer user-driven remediation when
CAI fails — enable `cloudasset.googleapis.com` and/or grant
`roles/cloudasset.viewer` (see https://docs.cloud.google.com/asset-inventory/docs/view-assets).
Replay skips Step 2 entirely (`manifest.json` already present), so the soft-ask
does not fire here — the fixture models the post-decline / per-service outcome.

## Regenerating / extending

Captures follow the exact projections in `discover-live.md` Step 2 (same
filenames). If you add a capture type: whitelist row first, then fixture, then
extend `expected-drift.json`. All project IDs, names, emails, and account
numbers are synthetic.
