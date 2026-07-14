---
_assemble: assemble-inventory
_of_phase: discover
_reads:
  - terraform (fragment contribution)
  - billing (fragment contribution)
_produces:
  - heroku-resource-inventory.json
---

# Discover — Assemble Inventory

> **Assembler unit.** Runs after the discover fragments (`discover-terraform.md`,
> `discover-billing.md`) have produced their contributions. It combines them into
> the single `heroku-resource-inventory.json` artifact and owns that artifact's
> final contract. See `discover.md` for how this unit is composed into the phase.

After all sub-discoveries complete, assemble `heroku-resource-inventory.json` in `$MIGRATION_DIR/`.

**Schema reference**: `shared/schema-discover-heroku.md` — consult for complete field definitions, per-type config schemas, and validation checklist.

## Assembly Rules

1. Merge all discovered resources into a flat array (no clustering, no dependency graphs).
2. Each resource entry MUST have: `resource_id`, `resource_type`, `heroku_app`, `config`.
3. Resources grouped by `heroku_app` field. Unassociable resources (spaces, pipelines) get `heroku_app: "unassociated"`.
4. Include `metadata` section: `discovery_timestamp`, `total_apps_discovered`, `discovery_sources`, `confidence`.
5. Include `apps[]` section with per-app entries containing:
   - `app_name`, `app_id`, `discovery_status` (success/discovery_failed), `failure_reason`
   - `heroku_generation` (cedar/fir/unknown), `generation_action` (always `detect_only`), `generation_diagnostics` (array of diagnostic reasons)
   - `space` (Private Space name or null)
   - `procfile_parse_warning`, `app_json_parse_warning` (per-app parse warnings or null)
6. Include `billing_profile` section (if billing data available, with `available`, `total_monthly_cost`, `currency`, `billing_period`, `line_items`).
7. Include `terraform_metadata` section (if Terraform discovery ran, with `found`, `tf_files_scanned`, `resource_types_extracted`, `parse_warnings`).

**If assembly fails** (no valid resources from any source after sub-discoveries ran):
this is an unrecoverable error (`INTERPRETER.md` § `_on_error` — `_unrecoverable`).
STOP and output: "Discovery ran but produced no valid resources. Check that your
input files contain valid Heroku resources and try again."

(The phase's `_postconditions` separately enforce that no forbidden clustering
fields — `cluster_id`, `creation_order_depth`, `edges`, `dependencies`,
`must_migrate_together` — appear in the assembled artifact.)
